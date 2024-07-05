import datetime
import logging
from time import sleep

from django.db.models import Q

from dateutil.relativedelta import relativedelta
from operator import itemgetter

from bot.models import Bot, BotCollection
from bot.rag_service import Conversations as RagConversation
from chat.models import Conversation, Question, ConversationShare
from chat.serializers import ConversationCreateSerializer, ConversationDetailSerializer, ConversationListSerializer, \
    QuestionListSerializer, ConversationShareCreateQuerySerializer
from collection.base_service import update_conversation_by_collection
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer
from collection.service import create_collection_by_documents
from core.utils.common import cmp_ignore_order
from document.models import DocumentLibrary, Document
from document.service import document_update_from_rag
from document.tasks import async_update_conversation_share_content

logger = logging.getLogger(__name__)


def conversation_create(user_id, validated_data, openapi_kay_id=None):
    vd = validated_data
    title = vd['content'][:128] if vd.get('content') else None
    # 判断 chat类型
    chat_type = ConversationCreateSerializer.get_chat_type(validated_data)
    papers_info = ConversationCreateSerializer.get_papers_info(
        user_id, vd.get('bot_id'), vd.get('collections'), vd['all_document_ids']
    )
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
        document_titles = Document.objects.filter(
            id__in=vd['documents'], del_flag=False).values_list('title', flat=True).all()
        if document_titles and len(document_titles) == 1 and document_titles[0]:
            title = document_titles[0]
        # auto create collection.
        collection_title = RagConversation.generate_favorite_title(list(document_titles))
        collection_title = collection_title[:255]
        collection = None
        if len(vd['documents']) > 1:
            collection = Collection.objects.create(
                user_id=user_id,
                title=collection_title,
                type=Collection.TypeChoices.PERSONAL,
                total_personal=len(vd['documents']),
                updated_at=datetime.datetime.now(),
            )
            c_doc_objs = []
            d_lib = DocumentLibrary.objects.filter(
                user_id=user_id, del_flag=False, document_id__in=vd['documents']
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
    rag_conv_create_data = {
        'conversation_id': vd.get('conversation_id'),
        'user_id': user_id,
        'agent_id': agent_id,
        'paper_ids': paper_ids,
        'public_collection_ids': public_collection_ids,
        'llm_name': vd['model'],
    }
    conv = RagConversation.create(**rag_conv_create_data)
    conversation = Conversation.objects.create(
        id=conv['id'],
        title="未命名-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") if title is None else title,
        user_id=conv['user_id'],
        agent_id=conv['agent_id'],
        documents=documents,
        model=vd['model'] if vd['model'] else 'gpt-4o',
        collections=collections,
        public_collection_ids=conv['public_collection_ids'],
        paper_ids=papers_info,
        type=chat_type,
        is_named=title is not None,
        bot_id=vd.get('bot_id'),
        is_api=True if openapi_kay_id else False,
    )
    # 返回 Conversation id
    return conversation


def conversation_create_by_share(user_id, conversation_share: ConversationShare, validated_data, openapi_kay_id=None):
    vd = validated_data
    chat_type = ConversationCreateSerializer.get_chat_type(validated_data)
    papers_info = ConversationCreateSerializer.get_papers_info(
        user_id, vd.get('bot_id'), vd.get('collections'), vd['all_document_ids']
    )
    title = conversation_share.title
    public_collection_ids = vd.get('public_collection_ids')
    documents = None
    collections = vd.get('collections')
    if chat_type == Conversation.TypeChoices.BOT_COV:
        bot_id = validated_data.get('bot_id')
        bot = Bot.objects.get(pk=bot_id)
        agent_id = bot.agent_id
    else:
        agent_id = None
    # 创建 Conversation
    all_document_ids = []
    paper_ids = []
    for p in papers_info:
        all_document_ids.append(p['document_id'])
        paper_ids.append({
            'collection_id': p['collection_id'],
            'collection_type': p['collection_type'],
            'doc_id': p['doc_id'],
            'full_text_accessible': p['full_text_accessible']
        })
    if not vd.get('bot_id') and not vd.get('collections'):
        documents = all_document_ids
    # 收藏夹对话分享，在收藏夹中自动创建一个自建收藏夹，收录该对话对应文献内容，默认不下载全文，在收藏夹下拉菜单中选中该收藏夹
    if not vd.get('bot_id') and vd.get('collections') and user_id != conversation_share.user_id:
        if all_document_ids:
            collection = create_collection_by_documents(user_id, all_document_ids, conversation_share.title)
            collections = [str(collection.id)]
        else:
            collections = []

    history_messages = []
    for q in conversation_share.content.get('questions'):
        if q['content']:
            history_messages.append({
                'role': 'user',
                'content': q['content'],
            })
        if q['answer']:
            history_messages.append({
                'role': 'assistant',
                'content': q['answer'],
            })
    rag_conv_create_data = {
        'conversation_id': vd.get('conversation_id'),
        'user_id': user_id,
        'agent_id': agent_id,
        'paper_ids': paper_ids,
        'public_collection_ids': public_collection_ids,
        'llm_name': vd['model'],
    }
    if history_messages:
        rag_conv_create_data['history_messages'] = history_messages
    conv = RagConversation.create(**rag_conv_create_data)
    conversation = Conversation.objects.create(
        id=conv['id'],
        title=title,
        user_id=conv['user_id'],
        share_id=conversation_share.id,
        agent_id=conv['agent_id'],
        documents=documents,
        model=vd['model'] if vd['model'] else 'gpt-4o',
        collections=collections,
        public_collection_ids=conv['public_collection_ids'],
        paper_ids=papers_info,
        type=chat_type,
        is_named=title is not None,
        bot_id=vd.get('bot_id'),
        is_api=True if openapi_kay_id else False,
    )
    # add questions to conversation
    questions, times = conversation_share.content.get('questions'), 0
    while not questions and times < 3:
        sleep(2)
        conversation_share = ConversationShare.objects.get(pk=conversation_share.id)
        questions = conversation_share.content.get('questions')
        times += 1
    if not questions:
        logger.warning(f'conversation_share {conversation_share.id} questions is None')
    else:
        conv_questions = []
        for q in questions:
            q['references'] = update_share_chat_references(user_id, q['references'])
            conv_questions.append(Question(
                conversation=conversation,
                content=q['content'],
                answer=q['answer'],
                stream={'output': q['references']},
                model=q['model'],
                input_tokens=q['input_tokens'],
                output_tokens=q['output_tokens'],
                source='share',
            ))
        question_objs = Question.objects.bulk_create(conv_questions)
        logger.debug(f'conversation {conversation.id} add {len(question_objs)} questions')
    # 返回 Conversation id
    return conversation


def conversation_update(user_id, conversation_id, validated_data):
    vd = validated_data
    conversation = Conversation.objects.get(pk=conversation_id, user_id=user_id)

    if vd.get('collections') is not None or vd.get('model'):
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
    if not conversation or (not conversation.documents and not conversation.bot_id and not conversation.collections):
        return conversation
    elif conversation.documents:
        doc_libs = DocumentLibrary.objects.filter(
            user_id=conversation.user_id,
            document_id__in=conversation.documents,
            del_flag=False,
            task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
        ).values_list('document_id', flat=True).all()
        documents = Document.objects.filter(id__in=conversation.documents, del_flag=False).all()
        new_paper_ids = [{
            'collection_id': d.collection_id,
            'collection_type': d.collection_type,
            'doc_id': d.doc_id,
            'full_text_accessible': d.id in doc_libs,
        } for d in documents] if documents else []
        new_papers_info = [{
            'collection_id': d.collection_id,
            'collection_type': d.collection_type,
            'doc_id': d.doc_id,
            'document_id': d.id,
            'full_text_accessible': d.id in doc_libs,
        } for d in documents] if documents else []

        if not cmp_ignore_order(conversation.paper_ids, new_papers_info, sort_fun=itemgetter('collection_id', 'doc_id')):
            update_data = {
                'conversation_id': conversation.id,
                'agent_id': conversation.agent_id,
                'paper_ids': new_paper_ids,
            }
            RagConversation.update(**update_data)
            conversation.documents = [d.id for d in documents] if documents else []
            conversation.paper_ids = new_papers_info
            conversation.save()
    elif conversation.bot_id or conversation.collections:
        if conversation.bot_id:
            all_collections = BotCollection.objects.filter(bot_id=conversation.bot_id, del_flag=False).values_list(
                'collection_id', flat=True).all()
        else:
            all_collections = list(
                set(conversation.collections if conversation.collections else [])
                | set(conversation.public_collection_ids if conversation.public_collection_ids else []))
        conversation = update_conversation_by_collection(conversation.user_id, conversation, all_collections)

    return conversation


def conversation_detail(conversation_id):
    conversation = Conversation.objects.get(pk=conversation_id)
    conversation = update_simple_conversation(conversation)
    public_collection_ids = conversation.public_collection_ids if conversation.public_collection_ids else []
    all_collection_ids = (conversation.collections if conversation.collections else []) + public_collection_ids
    collections = (
        Collection.objects.filter(id__in=all_collection_ids, del_flag=False).values('id', 'type', 'total_public').all()
        if all_collection_ids else []
    )
    collection_ids = [c['id'] for c in collections]
    public_collection_papers_num = sum([c['total_public'] for c in collections if c['type'] == Collection.TypeChoices.PUBLIC])
    conversation.collections = list(set(collection_ids))
    detail = ConversationDetailSerializer(conversation).data
    detail['papers_total'] = public_collection_papers_num + (
        len(conversation.paper_ids) if conversation.paper_ids else 0)
    return detail


def question_list(conversation, page_num, page_size):
    conversation_id = conversation.id
    filter_query = (
        Q(conversation_id=conversation_id, del_flag=False)
        & (((~Q(answer='')) & Q(answer__isnull=False)) | Q(source='share'))
    )
    query_set = Question.objects.filter(filter_query).order_by('-updated_at')
    total = query_set.count()
    questions = query_set[(page_num - 1) * page_size: page_num * page_size]
    questions_data = QuestionListSerializer(questions, many=True).data[::-1]
    for i,q in enumerate(questions_data):
        if q['references']:
            questions_data[i]['references'] = _update_chat_references(conversation, q['references'])
    return {
        'list': questions_data,
        'total': total,
    }


def _update_chat_references(conversation, references):
    papers = {f"{p['collection_id']}--{p['doc_id']}": p for p in conversation.paper_ids}
    for i,r in enumerate(references):
        if r.get('collection_id') and r.get('doc_id') and (
            f"{r['collection_id']}--{r['doc_id']}" in papers or r['collection_id'] == 'arxiv'
        ):
            references[i]['in_conversation'] = True
        else:
            references[i]['in_conversation'] = False
    return references


def conversation_list(validated_data):
    user_id = validated_data['user_id']
    page_num = validated_data['page_num']
    page_size = validated_data['page_size']
    query_set = Conversation.objects.filter(user_id=user_id, del_flag=False, is_api=False).values_list(
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
        query_set = Conversation.objects.filter(user_id=user_id, del_flag=False, is_api=False).values_list(
            'id', 'title', 'last_used_at', 'bot_id', named=True).order_by('-last_used_at')
    else:  # list_type == 'no_bot'
        query_set = Conversation.objects.filter(
            user_id=user_id, del_flag=False, bot_id__isnull=True, is_api=False).values_list(
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


def conversation_share_create(user_id,
                              validated_data: ConversationShareCreateQuerySerializer.data,
                              conversation: Conversation):
    vd = validated_data
    content = None
    if not vd['is_all']:
        question_ids = [q['id'] for q in vd['selected_questions']]
        selected_questions_dict = {
            q['id']: {'has_answer': q['has_answer'], 'has_question': q['has_question']}
            for q in vd['selected_questions']
        }
        questions = Question.objects.filter(id__in=question_ids).all()
        questions_data = QuestionListSerializer(questions, many=True).data
        for index,v in enumerate(questions_data):
            selected_question = selected_questions_dict[v['id']]
            questions_data[index].update(selected_question)
            if not selected_question.get('has_answer'):
                questions_data[index]['answer'] = None
                questions_data[index]['references'] = None
            if not selected_question.get('has_question'):
                questions_data[index]['content'] = None
        content = {'questions': questions_data}

    all_collections = list(
        set(conversation.collections if conversation.collections else [])
        | set(conversation.public_collection_ids if conversation.public_collection_ids else []))
    share_data = {
        'user_id': user_id,
        'conversation_id': vd['conversation_id'],
        'bot_id': conversation.bot_id,
        'title': conversation.title,
        'collections': all_collections,
        'documents': conversation.documents,
        'model': conversation.model,
        'content': content,
        'num': len(content['questions']) if content else 0,
    }
    if not conversation.bot_id and not all_collections:
        share_data['documents'] = conversation.documents
    conversation_share = ConversationShare.objects.create(**share_data)
    if vd['is_all']:
        # 异步获取所以问题列表
        async_update_conversation_share_content.apply_async(
            args=[conversation_share.id, vd['conversation_id'], vd['selected_questions']]
        )
    return {'share_id': conversation_share.id}


def chat_query(user_id, validated_data, openapi_key_id=None):
    if not validated_data.get('has_conversation'):
        conversation_id = conversation_create(user_id, validated_data, openapi_key_id)
    else:
        conversation_id = validated_data['conversation_id']
    return RagConversation.query(
        user_id, conversation_id, validated_data['content'], validated_data.get('question_id'), openapi_key_id)


def chat_papers_total(user_id, bot_id=None, collection_ids=None):
    if bot_id:
        collection_ids = BotCollection.objects.filter(
            bot_id=bot_id, del_flag=False).values_list('collection_id',flat=True).all()
    collections = Collection.objects.filter(
        id__in=collection_ids, del_flag=False).values('id', 'type', 'total_public').all()
    pub_coll_papers_total = sum([c['total_public'] for c in collections if c['type'] == Collection.TypeChoices.PUBLIC])
    bot = Bot.objects.filter(id=bot_id).first()
    query_set, d1, d2, ref_ds = CollectionDocumentListSerializer.get_collection_documents(
        user_id, collection_ids, 'all', bot=bot)
    doc_total = query_set.count() + len(ref_ds)
    return pub_coll_papers_total + doc_total


def update_share_chat_references(user_id, references):
    """
    分享的关联文献如果是个人上传文献 转为公共文献的信息
    :param user_id:
    :param references:g
    :return:
    """
    data_dict = {
        f"{o['collection_id']}__{o['doc_id']}": o
        for o in references if o.get('doc_id') and o.get('collection_id')
    }
    docs = []
    for d, ref in data_dict.items():
        collection_id, doc_id = d.split('__')
        if collection_id != user_id and collection_id not in ['s2', 'arxiv']:
            docs.append({'doc_id': doc_id, 'collection_id': collection_id})
    documents = Document.raw_by_docs(docs, where="ref_collection_id != '' and ref_doc_id >0") if docs else []
    tobe_update_docs = {f"{d.collection_id}__{d.doc_id}": d for d in documents}
    doc_apas, doc_titles = {}, {}
    for d in documents:
        doc_apas[f"{d.collection_id}__{d.doc_id}"] = d.get_csl_formate('apa')
        doc_titles[f"{d.collection_id}__{d.doc_id}"] = d.title
    for i, d in enumerate(references):
        if to_be_update_doc := tobe_update_docs.get(f"{d['collection_id']}__{d['doc_id']}"):
            ref_docs = [{'doc_id': to_be_update_doc.ref_doc_id, 'collection_id': to_be_update_doc.ref_collection_id}]
            if ref_doc := Document.raw_by_docs(ref_docs):
                ref_document = ref_doc[0]
            else:
                ref_document = document_update_from_rag(None, d['collection_id'], d['doc_id'])
            references[i]['collection type'] = ref_document.collection_type
            references[i]['collection_id'] = ref_document.collection_id
            references[i]['doc_id'] = ref_document.doc_id
            references[i]['id'] = ref_document.id
            references[i]['title'] = ref_document.title
    return references