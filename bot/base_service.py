import logging
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bot.models import Bot, BotCollection, BotSubscribe
from bot.rag_service import Bot as RagBot
from bot.serializers import BotDetailSerializer
from chat.serializers import ConversationCreateBaseSerializer
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer
from core.utils.exceptions import InternalServerError
from document.models import Document, DocumentLibrary
from document.serializers import DocumentApaListSerializer, CollectionDocumentListCollectionSerializer

logger = logging.getLogger(__name__)


# 专题详情
def bot_detail(user_id, bot):
    # bot = Bot.objects.get(pk=bot_id)
    bot_data = BotDetailSerializer(bot).data
    if bot_data['collections']:
        collections = Collection.objects.filter(id__in=bot_data['collections']).all()
        for collection in collections:
            if collection.id in ['s2', 'arxiv']:
                continue
            coll_doc_total = CollectionDocument.objects.filter(collection_id=collection.id, del_flag=False).count()
            if collection.total_personal != coll_doc_total:
                collection.total_personal = coll_doc_total
                collection.save()
    if is_subscribed(user_id, bot):
        bot_data['subscribed'] = True
    else:
        bot_data['subscribed'] = False
    return bot_data


def is_subscribed(user_id, bot: Bot):
    if bot.user_id == user_id:
        return True
    if BotSubscribe.objects.filter(user_id=user_id, bot=bot, del_flag=False).exists():
        return True
    return False


def bot_documents(user_id, bot, list_type, page_size=10, page_num=1, keyword=None):
    """
    专题文献列表
    """
    bot_id = bot.id
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections]
    bot_is_subscribed = is_subscribed(user_id, bot)
    public_count, need_public, need_public_count, personal_count, public_collections = 0, False, 0, 0, []
    all_public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    if page_num == 1:
        if list_type in ['all', 'all_documents']:
            need_public = True
            need_public_count = len(all_public_collections)
            public_collections = all_public_collections
        elif list_type in ['arxiv', 's2']:
            need_public = True
            public_collections = [c for c in all_public_collections if c.id == list_type]
            need_public_count = len(public_collections)
    public_count = len(public_collections)

    query_set, d1, d2, ref_ds = CollectionDocumentListSerializer.get_collection_documents(
        user_id, collection_ids, list_type, bot)
    start_num = page_size * (page_num - 1)
    # 个人上传文件库 关联的文献
    # 未发布专题 显示未公共库文献， 专题广场专题显示为订阅全文
    ref_doc_lib_ids = (
        set(ref_ds if ref_ds else []) & set(CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id))
    )
    if ref_ds:
        if list_type in ['personal']:
            ref_ds = list(ref_doc_lib_ids)
        elif list_type in ['s2', 'arxiv']:
            if bot.type == Collection.TypeChoices.PUBLIC or bot.advance_share:
                ref_ds = Document.objects.filter(
                    id__in=ref_ds, full_text_accessible=False, del_flag=False, collection_id=list_type
                ).values_list('id', flat=True)
            else:
                ref_ds = Document.objects.filter(
                    id__in=ref_ds, del_flag=False, collection_id=list_type
                ).values_list('id', flat=True)
            ref_ds = list(set(ref_ds) - set(ref_doc_lib_ids))
        elif list_type in ['subscribe_full_text']:
            if bot.type == Collection.TypeChoices.PUBLIC or bot.advance_share:
                ref_ds = list(Document.objects.filter(
                    id__in=ref_ds, full_text_accessible=True, del_flag=False).values_list('id', flat=True).all())
                ref_ds = list(set(ref_ds) - set(ref_doc_lib_ids))
            else:
                ref_ds = []

    all_c_docs = query_set.all()
    start = start_num - (public_count % page_size if not need_public_count and start_num else 0)
    document_ids = [cd['document_id'] for cd in all_c_docs]
    if ref_ds:
        document_ids += ref_ds
    filter_query = Q(id__in=document_ids)
    if keyword:
        filter_query &= Q(title__icontains=keyword)
    doc_query_set = Document.objects.filter(filter_query).order_by('title')
    docs = doc_query_set[start:(page_size * page_num - need_public_count)]
    query_total = doc_query_set.count()
    total = query_total + public_count
    show_total = query_total

    res_data = []
    if list_type in ['all', 'all_documents', 'arxiv', 's2'] and public_collections:
        for p_c in public_collections:
            if (
                (list_type in ['s2', 'arxiv'] and p_c.id != list_type and not need_public)
                or (list_type in ['all', 'all_documents'] and not need_public)
            ):
                continue
            res_data.append({
                'id': None,
                'collection_id': p_c.id,
                'doc_id': None,
                'doc_apa': f"{_('公共库')}: {p_c.title}",
                'title': f"{_('公共库')}: {p_c.title}",
                'has_full_text': False,
                'type': p_c.id,
            })
    if list_type == 'all':
        docs_data = DocumentApaListSerializer(docs, many=True).data
        data_dict = {d['id']: d for d in docs_data}
        # todo has_full_text
        query_set, d1, d2, ref_ds = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'personal&subscribe_full_text', bot)
        if bot_is_subscribed:
            all_full_text_docs = [d['document_id'] for d in query_set.all()]
        else:
            all_full_text_docs = d1
        # 个人关联文献是否有全文
        if ref_ds:
            full_text_ref_documents = Document.objects.filter(
                id__in=ref_ds, full_text_accessible=True, del_flag=False).values_list('id', flat=True).all()
            if (bot.type == Bot.TypeChoices.PERSONAL and not bot.advance_share) or not bot_is_subscribed:
                full_text_ref_documents = DocumentLibrary.objects.filter(
                    user_id=user_id, document_id__in=list(full_text_ref_documents), del_flag=False,
                    task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
                ).values_list('document_id', flat=True).all()
            all_full_text_docs += list(full_text_ref_documents)
        for doc in docs:
            has_full_text = (
                True if doc.id in all_full_text_docs or (
                    doc.id in ref_ds and doc.object_path and (bot.type == Bot.TypeChoices.PUBLIC or bot.advance_share))
                else False
            )
            res_data.append({
                'id': doc.id,
                'collection_id': doc.collection_id,
                'doc_id': doc.doc_id,
                'doc_apa': data_dict[doc.id]['doc_apa'],
                'title': data_dict[doc.id]['title'],
                'has_full_text': has_full_text,
            })
    else:
        if list_type == 'all_documents':
            res_data += CollectionDocumentListCollectionSerializer(docs, many=True).data
            query_set, doc_lib_document_ids, sub_bot_document_ids, ref_documents = \
                CollectionDocumentListSerializer.get_collection_documents(
                    user_id, collection_ids, 'personal&subscribe_full_text', bot)
            # document_ids = [cd['document_id'] for cd in query_set.all()]
            for index, d_id in enumerate(res_data):
                if not d_id['id']:
                    continue
                full_text_ref_documents = []
                if ref_ds:
                    full_text_ref_documents = Document.objects.filter(
                        id__in=ref_ds, full_text_accessible=True, del_flag=False).values_list('id', flat=True)
                if d_id['id'] in doc_lib_document_ids:
                    res_data[index]['type'] = 'personal'
                elif d_id['id'] in sub_bot_document_ids:
                    res_data[index]['type'] = 'subscribe_full_text'
                elif (
                    bot.type == Bot.TypeChoices.PUBLIC or bot.advance_share
                ) and d_id['id'] in full_text_ref_documents:
                    res_data[index]['type'] = 'subscribe_full_text'
        else:
            res_data += CollectionDocumentListCollectionSerializer(docs, many=True).data
            for index, d_id in enumerate(res_data):
                res_data[index]['type'] = list_type
    return {
        'list': res_data,
        # 个人库库文献 不能在添加到个人库
        'is_all_in_document_library': True if list_type == 'personal' else False,
        'total': total,
        'show_total': show_total,
    }


def recreate_bot(bot: Bot, collections):
    RagBot.delete(bot.agent_id)
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    papers_info = ConversationCreateBaseSerializer.get_papers_info(
        user_id=bot.user_id, bot_id=bot.id, collection_ids=[c.id for c in collections], document_ids=[]
    )
    paper_ids = []
    for p in papers_info:
        paper_ids.append({
            'collection_id': p['collection_id'],
            'collection_type': p['collection_type'],
            'doc_id': p['doc_id'],
            'full_text_accessible': p['full_text_accessible']
        })
    rag_ret = RagBot.create(
        bot.user_id,
        bot.prompt,
        bot.questions,
        tools=bot.tools,
        paper_ids=collections_doc_ids(collections),
        public_collection_ids=public_collection_ids,
    )
    if rag_ret.get('id'):
        bot.extension = rag_ret
        bot.agent_id = rag_ret['id']
        BotCollection.objects.filter(bot_id=bot.id).update(del_flag=True)
        # save BotCollection
        for c in collections:
            bc_data = {
                'bot_id': bot.id,
                'collection_id': c.id,
                'collection_type': c.type,
                'del_flag': False,
            }
            BotCollection.objects.update_or_create(
                bc_data, bot_id=bc_data['bot_id'], collection_id=bc_data['collection_id'])
    else:
        raise InternalServerError('RAG create bot failed')


def collections_doc_ids(collections: list[Collection]):
    _cids = [c.id for c in collections if c.type == c.TypeChoices.PERSONAL]
    c_docs = CollectionDocument.objects.filter(collection_id__in=_cids).all()
    return [{
        'collection_id': c_doc.document.collection_id,
        'collection_type': c_doc.document.collection_type,
        'doc_id': c_doc.document.doc_id} for c_doc in c_docs
    ]


def mine_bot_document_ids(bot_id):
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
    collection_ids = [bc.collection_id for bc in bot_collections if bc.collection_id not in ['s2', 'arxiv']]
    c_docs = CollectionDocument.objects.filter(
        collection_id__in=collection_ids, del_flag=False).values_list('document_id', flat=True).all()
    return list(c_docs)
