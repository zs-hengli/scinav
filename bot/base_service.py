import logging
from django.utils.translation import gettext_lazy as _

from bot.models import Bot, BotCollection, BotSubscribe
from bot.rag_service import Bot as RagBot
from bot.serializers import BotDetailSerializer
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer
from core.utils.exceptions import InternalServerError
from document.models import Document
from document.serializers import DocumentApaListSerializer, CollectionDocumentListCollectionSerializer

logger = logging.Logger(__name__)


# 专题详情
def bot_detail(user_id, bot):
    # bot = Bot.objects.get(pk=bot_id)
    bot_data = BotDetailSerializer(bot).data
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


def bot_documents(user_id, bot, list_type, page_size=10, page_num=1):
    """
    专题文献列表
    """
    bot_id = bot.id
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections]
    # query_set = CollectionDocument.objects.filter(
    #     collection_id__in=collection_ids).distinct().values('document_id').order_by('document_id')
    public_count, need_public, need_public_count, personal_count, public_collections = 0, False, 0, 0, []
    all_public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    all_public_collection_ids = [c.id for c in all_public_collections]
    if page_num == 1 and list_type in ['all', 'all_documents']:
        need_public_count = len(all_public_collections)
        public_collections = all_public_collections
    elif page_num == 1 and list_type == 's2':
        if 's2' in all_public_collection_ids:
            need_public_count = 1
            public_collections = [pc for pc in all_public_collections if pc.id == 's2']
    elif page_num == 1 and list_type == 'arxiv':
        if 'arxiv' in all_public_collection_ids:
            need_public_count = 1
            public_collections = [pc for pc in all_public_collections if pc.id == 'arxiv']
    if page_num == 1 and list_type in ['all', 'all_documents', 's2', 'arxiv']:
        need_public = True
    public_count = len(public_collections)

    query_set, d1, d2, ref_ds = CollectionDocumentListSerializer.get_collection_documents(
        user_id, collection_ids, list_type, bot)
    start_num = page_size * (page_num - 1)
    doc_ids = []
    show_total = 0
    # 个人上传文件库 关联的文献
    # 未发布专题 显示未公共库文献， 专题广场专题显示为订阅全文
    ref_doc_lib_ids = (
        set(ref_ds if ref_ds else []) & set(CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id))
    )
    if ref_ds and (
        list_type in ['all', 'all_documents']
        or (list_type in ['s2', 'arxiv'] and bot.type == Collection.TypeChoices.PERSONAL)
        or (list_type in ['subscribe_full_text'] and bot.type == Collection.TypeChoices.PUBLIC)
        or (list_type in ['personal'] and ref_doc_lib_ids)
    ):
        if list_type in ['personal']:
            ref_ds = list(ref_doc_lib_ids)
        elif list_type in ['s2', 'arxiv']:
            ref_ds = list(set(ref_ds) - set(ref_doc_lib_ids))
        doc_ids = ref_ds[start_num:(page_size * page_num - need_public_count)]
        need_public_count += len(doc_ids)
        public_count += len(ref_ds)
        show_total += len(ref_ds)
    personal_count = query_set.count()
    total = public_count + personal_count
    show_total += personal_count
    logger.info(f"limit: [{start_num}:{page_size * page_num}], personal_count: {personal_count}")
    if page_size * page_num > public_count:
        start = start_num - (public_count % page_size if not need_public_count and start_num else 0)
        c_docs = query_set[start:(page_size * page_num - need_public_count)] if total > start_num else []
        doc_ids += [cd['document_id'] for cd in c_docs]
    docs = Document.objects.filter(id__in=doc_ids).all()
    # docs = [cd.document for cd in c_docs]
    res_data = []
    if list_type in ['all', 'all_documents', 's2', 'arxiv'] and public_collections and need_public:
        for p_c in public_collections:
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
        query_set, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'personal&subscribe_full_text', bot)
        all_full_text_docs = [d['document_id'] for d in query_set.all()]

        for doc in docs:
            has_full_text = (
                True
                if doc.id in all_full_text_docs or (
                    doc.id in d3 and doc.object_path and bot.type == Bot.TypeChoices.PUBLIC)
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
                if d_id['id'] in doc_lib_document_ids:
                    res_data[index]['type'] = 'personal'
                elif d_id['id'] in sub_bot_document_ids:
                    res_data[index]['type'] = 'subscribe_full_text'
                elif bot.type == Bot.TypeChoices.PUBLIC and d_id['id'] in ref_documents:
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
    rag_ret = RagBot.create(
        bot.user_id,
        bot.prompt,
        bot.questions,
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