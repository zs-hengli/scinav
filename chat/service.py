import datetime
import logging

from dateutil.relativedelta import relativedelta

from bot.models import Bot
from bot.rag_service import Conversations as RagConversation
from chat.models import Conversation
from chat.serializers import ConversationCreateSerializer, ConversationDetailSerializer, ConversationListSerializer
from collection.models import Collection, CollectionDocument

logger = logging.getLogger(__name__)


def conversation_create(validated_data):
    vd = validated_data
    # 判断 chat类型
    chat_type = ConversationCreateSerializer.get_chat_type(validated_data)
    if chat_type == Conversation.TypeChoices.BOT_COV:
        bot_id = validated_data.get('bot_id')
        bot = Bot.objects.get(pk=bot_id, del_flag=False)
        agent_id = bot.agent_id
        paper_ids = bot.extension['paper_ids']
        public_collection_ids = bot.extension['public_collection_ids']
        documents = None
        collections = None
    elif vd.get('documents'):
        # auto create collection.
        collection_title = RagConversation.generate_favorite_title(vd['document_tiles'])
        collection = Collection.objects.create(
            user_id=vd['user_id'],
            title=collection_title,
            type=Collection.TypeChoices.PERSONAL,
            total=len(vd['documents']),
        )
        c_doc_objs = []
        for document_id in vd['documents']:
            c_doc_objs.append(CollectionDocument(
                collection=collection,
                document_id=document_id,
            ))
        CollectionDocument.objects.bulk_create(c_doc_objs)
        agent_id = None
        paper_ids = vd.get('paper_ids')
        public_collection_ids = vd.get('public_collection_ids')
        documents = vd.get('documents')
        collections = vd.get('collections', []) + [collection.id]
    else:
        agent_id = None
        paper_ids = vd.get('paper_ids')
        public_collection_ids = vd.get('public_collection_ids')
        documents = vd.get('documents')
        collections = vd.get('collections')

    # 创建 Conversation
    conv = RagConversation.create(
        user_id=vd['user_id'],
        agent_id=agent_id,
        paper_ids=paper_ids,
        public_collection_ids=public_collection_ids,
    )
    conversation = Conversation.objects.create(
        id=conv['id'],
        title="未命名-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        user_id=conv['user_id'],
        agent_id=conv['agent_id'],
        documents=documents,
        collections=collections,
        public_collection_ids=conv['public_collection_ids'],
        paper_ids=conv['paper_ids'],
        type=chat_type,
    )
    # 返回 Conversation id
    return str(conversation.id)


def conversation_update(conversation_id, validated_data):
    conversation = Conversation.objects.get(pk=conversation_id, user_id=validated_data['user_id'])

    if validated_data.get('title'):
        conversation.title = validated_data['title']
    if validated_data.get('del_flag'):
        conversation.del_flag = validated_data['del_flag']
    # conversation.last_used_at = datetime.datetime.now()
    conversation.save()
    return ConversationListSerializer(conversation).data


def conversation_detail(conversation_id):
    conversation = Conversation.objects.get(pk=conversation_id)
    return ConversationDetailSerializer(conversation).data


def conversation_list(validated_data):
    user_id = validated_data['user_id']
    page_num = validated_data['page_num']
    page_size = validated_data['page_size']
    query_set = Conversation.objects.filter(user_id=user_id, del_flag=False).values_list(
        'id', 'title', 'last_used_at', named=True).order_by('-last_used_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    conversations = query_set[start_num:(page_size * page_num)]
    list_data = ConversationListSerializer(conversations, many=True).data
    return {
        'list': list_data,
        'total': filter_count
    }


def conversation_menu_list(validated_data):
    user_id = validated_data['user_id']
    query_set = Conversation.objects.filter(user_id=user_id, del_flag=False).values_list(
        'id', 'title', 'last_used_at', named=True).order_by('-last_used_at')
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
        validated_data['user_id'], conversation_id, validated_data['content'])
