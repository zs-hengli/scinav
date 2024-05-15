import datetime
import logging

from dateutil.relativedelta import relativedelta

from bot.models import Bot
from bot.rag_service import Conversations as RagConversation
from chat.models import Conversation
from chat.serializers import ConversationCreateSerializer, ConversationDetailSerializer, ConversationListSerializer
from collection.base_service import update_conversation_by_collection
from collection.models import Collection, CollectionDocument
from document.models import DocumentLibrary, Document

logger = logging.getLogger(__name__)


def conversation_create(validated_data):
    vd = validated_data
    title = vd['content'][:128] if vd.get('content') else None
    # 判断 chat类型
    chat_type = ConversationCreateSerializer.get_chat_type(validated_data)
    papers_info = vd['papers_info']
    if chat_type == Conversation.TypeChoices.BOT_COV:
        bot_id = validated_data.get('bot_id')
        bot = Bot.objects.get(pk=bot_id, del_flag=False)
        agent_id = bot.agent_id
        # paper_ids = bot.extension['paper_ids']
        public_collection_ids = bot.extension['public_collection_ids']
        documents = None
        collections = vd.get('collections')
        title = bot.title
    elif vd.get('documents'):
        if vd.get('document_titles') and len(vd['document_titles']) == 1:
            title = vd['document_titles'][0]
        # auto create collection.
        collection_title = RagConversation.generate_favorite_title(vd['document_titles'])
        collection_title = collection_title[:255]
        collection = None
        if len(vd['documents']) > 1:
            collection = Collection.objects.create(
                user_id=vd['user_id'],
                title=collection_title,
                type=Collection.TypeChoices.PERSONAL,
                total_personal=len(vd['documents']),
                updated_at=datetime.datetime.now(),
            )
            c_doc_objs = []
            d_lib = DocumentLibrary.objects.filter(
                user_id=vd['user_id'], del_flag=False, document_id__in=vd['documents']
            ).values_list('document_id', flat=True)
            for document_id in vd['documents']:
                c_doc_objs.append(CollectionDocument(
                    collection=collection,
                    document_id=document_id,
                    full_text_accessible=document_id in d_lib,  # todo v1.0 默认都有全文 v2.0需要考虑策略
                ))
            CollectionDocument.objects.bulk_create(c_doc_objs)
        agent_id = None
        # paper_ids = vd.get('paper_ids')
        public_collection_ids = vd.get('public_collection_ids')
        documents = vd.get('documents')
        collections = vd.get('collections', []) + ([str(collection.id)] if collection else [])
    else:
        agent_id = None
        # paper_ids = vd.get('paper_ids')
        public_collection_ids = vd.get('public_collection_ids')
        documents = vd.get('documents')
        collections = vd.get('collections')

    # 创建 Conversation
    paper_ids = []
    for p in papers_info:
        paper_ids.append({
            'collection_id': p['collection_id'],
            'collection_type': p['collection_type'],
            'doc_id': p['doc_id'],
            'full_text_accessible': p['full_text_accessible']
        })
    conv = RagConversation.create(
        user_id=vd['user_id'],
        agent_id=agent_id,
        paper_ids=paper_ids,
        public_collection_ids=public_collection_ids,
        llm_name=vd['model'],
    )
    conversation = Conversation.objects.create(
        id=conv['id'],
        title="未命名-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") if title is None else title,
        user_id=conv['user_id'],
        agent_id=conv['agent_id'],
        documents=documents,
        model=vd['model'] if vd['model'] else 'gpt-3.5-turbo',
        collections=collections,
        public_collection_ids=conv['public_collection_ids'],
        paper_ids=papers_info,
        type=chat_type,
        is_named=title is not None,
        bot_id=vd.get('bot_id'),
    )
    # 返回 Conversation id
    return str(conversation.id)


def conversation_update(user_id, conversation_id, validated_data):
    vd = validated_data
    conversation = Conversation.objects.get(pk=conversation_id, user_id=user_id)

    if vd.get('collections') or vd.get('model'):
        # update conversation
        conversation = update_conversation_by_collection(user_id, conversation, vd.get('collections'), vd.get('model'))
    if vd.get('title'):
        conversation.title = vd['title']
    if vd.get('del_flag'):
        conversation.del_flag = vd['del_flag']

    conversation.save()
    return ConversationListSerializer(conversation).data


def update_simple_conversation(conversation: Conversation):
    """
    单文献问答，考虑文献被删情况
    """
    if not conversation or not conversation.documents:
        return conversation
    doc_libs = DocumentLibrary.objects.filter(
        user_id=conversation.user_id, document_id__in=conversation.documents, del_flag=False)
    if doc_libs.count() != len(conversation.documents):
        paper_ids, new_document_ids = None, None
        if doc_libs:
            new_document_ids = [dl.document_id for dl in doc_libs]
            documents = Document.objects.filter(id__in=new_document_ids)
            paper_ids = [
                {'collection_id': d['collection_id'], 'collection_type': d['collection_type'], 'doc_id': d['doc_id']}
                for d in documents
            ]
        update_data = {
            'conversation_id': conversation.id,
            'agent_id': conversation.agent_id,
            'paper_ids': paper_ids,
        }
        RagConversation.update(**update_data)
        conversation.documents = new_document_ids
        conversation.save()
    return conversation


def conversation_detail(conversation_id):
    conversation = Conversation.objects.get(pk=conversation_id)
    conversation = update_simple_conversation(conversation)
    collections = (
        Collection.objects.filter(id__in=conversation.collections, del_flag=False).values('id').all()
        if conversation.collections else []
    )
    collections = [c['id'] for c in collections]
    conversation.collections = collections
    return ConversationDetailSerializer(conversation).data


def conversation_list(validated_data):
    user_id = validated_data['user_id']
    page_num = validated_data['page_num']
    page_size = validated_data['page_size']
    query_set = Conversation.objects.filter(user_id=user_id, del_flag=False).values_list(
        'id', 'title', 'last_used_at', named=True).order_by('-last_used_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    conversations = query_set[start_num:(page_size * page_num)]
    list_data = ConversationListSerializer(conversations, many=True).data
    return {
        'list': list_data,
        'total': filter_count
    }


def conversation_menu_list(user_id, list_type='all'):
    if list_type == 'all':
        query_set = Conversation.objects.filter(user_id=user_id, del_flag=False).values_list(
            'id', 'title', 'last_used_at', 'bot_id', named=True).order_by('-last_used_at')
    else:  # list_type == 'no_bot'
        query_set = Conversation.objects.filter(
            user_id=user_id, del_flag=False, bot_id__isnull=True).values_list(
            'id', 'title', 'last_used_at', 'bot_id', named=True).order_by('-last_used_at')

    list_data = ConversationListSerializer(query_set.all(), many=True).data
    data = {
        # 'today': [],
        # 'yesterday': [],
        # 'within_7_days': [],
        # 'within_30_days': [],
        # 'this_year': [],
    }
    today = datetime.datetime.strptime(datetime.datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d')
    for conv in list_data:
        last_used_at = datetime.datetime.strptime(conv['last_used_at'][:10], '%Y-%m-%d')
        if today <= last_used_at:
            if data.get('today', None) is None:
                data['today'] = []
            data['today'].append(conv)
        elif today <= last_used_at + relativedelta(days=1):
            if data.get('yesterday', None) is None:
                data['yesterday'] = []
            data['yesterday'].append(conv)
        elif today <= last_used_at + relativedelta(days=7):
            if data.get('within_7_days', None) is None:
                data['within_7_days'] = []
            data['within_7_days'].append(conv)
        elif today <= last_used_at + relativedelta(days=30):
            if data.get('within_30_days', None) is None:
                data['within_30_days'] = []
            data['within_30_days'].append(conv)
        elif today.year == last_used_at.year:
            if data.get('this_year', None) is None:
                data['this_year'] = []
            data['this_year'].append(conv)
        else:
            if not data.get(last_used_at.year):
                data[last_used_at.year] = []
            data[last_used_at.year].append(conv)

    return {
        'data': data,
        'keys': list(data.keys()),
    }


def chat_query(validated_data):
    if not validated_data.get('conversation_id'):
        conversation_id = conversation_create(validated_data)
    else:
        conversation_id = validated_data['conversation_id']
    return RagConversation.query(
        validated_data['user_id'], conversation_id, validated_data['content'], validated_data.get('question_id'))
