import datetime
import logging

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bot.models import BotCollection, BotSubscribe, Bot
from bot.rag_service import Collection as RagCollection, Conversations as RagConversations
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionPublicSerializer, CollectionListSerializer, \
    CollectionRagPublicListSerializer, \
    CollectionSubscribeSerializer, CollectionDocumentListSerializer, bot_subscribe_personal_document_num
from document.models import Document, DocumentLibrary
from document.serializers import DocumentApaListSerializer, CollectionDocumentListCollectionSerializer
from document.service import search_result_from_cache

logger = logging.getLogger(__name__)


def collection_list(user_id, list_type, page_size, page_num):
    coll_list = []
    start_num = page_size * (page_num - 1)
    # 1 public collections
    public_total, subscribe_total, sub_add_list, my_total = 0, 0, [], 0
    if 'public' in list_type:
        # todo /api/v1/public-collections 接口超时暂时跳过
        # saved_colls = Collection.objects.filter(type=Collection.TypeChoices.PUBLIC, del_flag=False)
        # public_total = saved_colls.count()
        # for coll in saved_colls:
        #     coll_list.append({
        #         'id': coll.id,
        #         'name': coll.title,
        #         'updated_at': coll.updated_at,
        #         'total': coll.total_public,
        #         'type': coll.type,
        #     })
        public_collections = RagCollection.list()
        public_collections = [pc | {'updated_at': pc['update_time']} for pc in public_collections]
        pub_serial = CollectionRagPublicListSerializer(data=public_collections, many=True)
        pub_serial.is_valid(raise_exception=True)
        public_total = len(pub_serial.data)
        if start_num == 0:
            coll_list = pub_serial.data
            ids = [c['id'] for c in public_collections]
            _save_public_collection(Collection.objects.filter(id__in=ids).all(), public_collections)
    # 2 submit bot collections
    if 'subscribe' in list_type:
        sub_serial = CollectionSubscribeSerializer(data=_bot_subscribe_collection_list(user_id), many=True)
        sub_serial.is_valid()
        subscribe_total = len(sub_serial.data)
        # coll_list += sub_serial.data
        sub_add_list = list(sub_serial.data)[start_num:start_num + page_size - len(coll_list)]
        if sub_add_list: coll_list += sub_add_list

    # 3 user collections
    if 'my' in list_type:
        collections = Collection.objects.filter(user_id=user_id, del_flag=False).order_by('-updated_at')
        my_total = collections.count()
        if len(coll_list) < page_size:
            my_start_num = 0 if coll_list else max(start_num - subscribe_total - public_total, 0)
            my_end_num = my_start_num + page_size - len(coll_list)
            query_set = collections[my_start_num:my_end_num]
            coll_list += list(CollectionListSerializer(query_set, many=True).data)
    if set(list_type) == {'public', 'subscribe', 'my'}:
        for coll in coll_list:
            if coll['type'] in [Collection.TypeChoices.SUBSCRIBE, Collection.TypeChoices.PUBLIC]:
                coll['is_all_in_document_library'] = True
            else:
                coll['is_all_in_document_library'] = _is_collection_docs_all_in_document_library(coll['id'], user_id)
            coll['has_ref_bots'], coll['bot_titles'] = _collection_ref_bots(user_id, [coll['id']])
            coll['is_in_published_bot'] = coll['has_ref_bots']
    return {
        'list': coll_list,
        'total': my_total + subscribe_total + public_total,
        'show_total': my_total + public_total,
    }


def _collection_ref_bots(user_id, collection_ids):
    filter_query = (
        Q(collection_id__in=collection_ids, del_flag=False, bot__type=Bot.TypeChoices.PUBLIC)
        | Q(collection_id__in=collection_ids, del_flag=False, collection__user_id=user_id)
    )
    bot_colls = BotCollection.objects.filter(filter_query).values('bot__title').distinct('bot__title').all()
    has_ref_bots, bot_titles = False, None
    if bot_colls:
        has_ref_bots = True
        bot_titles = [b['bot__title'] for b in bot_colls]
    return has_ref_bots, bot_titles


def _is_collection_in_published_bot(collection_ids):
    is_in_published_bot = BotCollection.objects.filter(
        collection_id__in=collection_ids, del_flag=False, bot__type=Bot.TypeChoices.PUBLIC).exists()
    bot_titles = None
    if is_in_published_bot:
        bots = BotCollection.objects.filter(
            collection_id__in=collection_ids, del_flag=False, bot__type=Bot.TypeChoices.PUBLIC).values('bot__title').all()
        bot_titles = [b['bot__title'] for b in bots]
    return is_in_published_bot, bot_titles


def _is_collection_docs_all_in_document_library(collection_id, user_id):
    doc_libs = CollectionDocument.objects.filter(collection_id=collection_id, del_flag=False).values(
        'document_id').distinct('document_id').all()
    doc_ids = [d['document_id'] for d in doc_libs]
    coll_document_libs = DocumentLibrary.objects.filter(
        del_flag=False, user_id=user_id, document_id__in=doc_ids,
        task_status__in=[
            DocumentLibrary.TaskStatusChoices.COMPLETED,
            DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
            DocumentLibrary.TaskStatusChoices.PENDING,
        ]
    ).values('document_id').distinct('document_id')
    coll_documents = [d['document_id'] for d in coll_document_libs]
    dif_docs = set(doc_ids) - set(coll_documents)
    if dif_docs:
        d_dif_count = Document.objects.filter(id__in=dif_docs, collection_id=user_id).count()
        return len(dif_docs) == d_dif_count
    else:
        return True


def _bot_subscribe_collection_list(user_id):
    bot_sub = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bot_ids = [bc.bot_id for bc in bot_sub]
    bots = Bot.objects.filter(id__in=bot_ids)
    bots_dict = {b.id: b for b in bots}
    bot_collections = BotCollection.objects.filter(
        bot_id__in=bot_ids, del_flag=False).order_by('bot_id', '-updated_at').all()
    bot_sub_collect = {}
    for bc in bot_collections:
        bot = bots_dict[bc.bot_id]
        if bc.bot_id not in bot_sub_collect:
            bot_sub_collect[bc.bot_id] = {
                'id': None,
                'bot_id': bc.bot_id,
                'name': bot.title,
                'bot_user_id': bot.user_id,
                'type': Collection.TypeChoices.SUBSCRIBE,
                'collection_ids': [],
                'updated_at': bc.updated_at,
                'total': 0,
            }
        # 本人专题
        bot_sub_collect[bc.bot_id]['total'] += bc.collection.total_public + bc.collection.total_personal
        bot_sub_collect[bc.bot_id]['updated_at'] = max(
            bot_sub_collect[bc.bot_id]['updated_at'], bc.collection.updated_at)
        bot_sub_collect[bc.bot_id]['collection_ids'].append(bc.collection_id)
    for bot_id, coll in bot_sub_collect.items():
        if user_id != coll['bot_user_id']:
            personal_documents, ref_documents = bot_subscribe_personal_document_num(coll['bot_user_id'], bot_id=bot_id)
            bot_sub_collect[bot_id]['total'] -= len(personal_documents) - len(ref_documents)
    # 排序 updated_at 倒序
    list_data = sorted(bot_sub_collect.values(), key=lambda x: x['updated_at'], reverse=True)
    return list_data


def generate_collection_title(content=None, document_titles=None):
    if content:
        search_result = search_result_from_cache(content, 200, 1)
        titles = [
            sr['title'] for sr in search_result['list']
        ] if search_result and search_result.get('list') else [content]
    else:
        titles = document_titles
    return RagConversations.generate_favorite_title(titles)


def collection_detail(user_id, collection_id):
    pass


def collection_delete(collection):
    # if BotCollection.objects.filter(collection_id=collection.id, del_flag=False).exists():
    #     raise ValidationError(_('此收藏夹被用于专题中，不能删除'))

    collection.del_flag = True
    collection.save()
    return True
    pass


def collections_delete(validated_data):
    vd = validated_data
    # todo  删除关联的专题收藏夹 BotCollection对应的记录
    if vd.get('is_all'):
        query_filter = Q(user_id=vd['user_id'], del_flag=False)
        if vd.get('ids'):
            query_filter &= ~Q(id__in=vd['ids'])
        collections = Collection.objects.filter(query_filter)

    else:
        collections = Collection.objects.filter(
            id__in=vd['ids'], del_flag=False, type=Collection.TypeChoices.PERSONAL)
    collections_dict = collections.values('id', 'total_public', 'total_personal').all()
    BotCollection.objects.filter(
        collection_id__in=[c['id'] for c in collections_dict], del_flag=False).update(del_flag=True)
    effect_num = collections.update(del_flag=True)
    logger.debug(f"collections_delete effect_num: {effect_num}")
    return effect_num


def _save_public_collection(saved_collections, public_collections):
    saved_collections_dict = {c.id: c for c in saved_collections}
    for pc in public_collections:
        coll_data = {
            'id': pc['id'],
            'title': pc['name'],
            'user_id': None,
            'type': Collection.TypeChoices.PUBLIC,
            'total_public': pc['total'],
            'del_flag': False,
            'task_id': None,
            'updated_at': datetime.datetime.strptime(pc['update_time'][:19], '%Y-%m-%dT%H:%M:%S'),
        }
        serial = CollectionPublicSerializer(data=coll_data)
        if not serial.is_valid():
            logger.error(f"public collection data is invalid: {serial.errors}")
        if pc['id'] not in saved_collections_dict.keys():
            # create
            serial.save()
        else:
            # update
            collection = saved_collections_dict[pc['id']]
            serial.update(collection, coll_data)


def collection_docs(collection_id, page_size=10, page_num=1):
    query_set = CollectionDocument.objects.filter(collection_id=collection_id, del_flag=False).order_by('-updated_at')
    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)]
    docs = [cd.document for cd in c_docs]

    docs_data = DocumentApaListSerializer(docs, many=True).data
    for i, d_data in enumerate(docs_data):
        docs_data[i]['doc_apa'] = f"[{start_num + i + 1}] {d_data['doc_apa']}"

    if c_docs:
        collection = c_docs[0].collection
        return {
            'collection_id': collection_id,
            'collection_type': collection.type,
            'collection_title': collection.title,
            'list': docs_data,
            'total': total
        }
    return {}


def collections_docs(user_id, validated_data):
    vd = validated_data
    collection_ids = vd['collection_ids']
    page_size = vd['page_size']
    page_num = vd['page_num']
    res_data = []
    public_count, need_public_count = 0, 0
    public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    public_count = len(public_collections)
    if page_num == 1 and vd['list_type'] == 'all':
        need_public_count = public_count
        for c in public_collections:
            res_data.append({
                'id': None,
                'doc_apa': f"{_('公共库')}: {c.title}",
                'has_full_text': False,
            })
    query_set, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
        vd['user_id'], collection_ids, vd['list_type'])
    query_total = query_set.count()
    total = query_total + public_count
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    # 没有按照titles名称升序排序
    # c_docs = query_set[start_num:(page_size * page_num - need_public_count)]
    # docs = Document.objects.filter(id__in=[cd['document_id'] for cd in c_docs]).all()
    # 按照名称升序排序
    all_c_docs = query_set.all()
    docs = Document.objects.filter(id__in=[cd['document_id'] for cd in all_c_docs]).order_by('title')[
           start_num:(page_size * page_num - need_public_count)
    ]

    if vd['list_type'] == 'all':
        docs_data = DocumentApaListSerializer(docs, many=True).data
        data_dict = {d['id']: d for d in docs_data}
        temp_res_data = []
        for d in docs:
            temp = None
            # 本人个人库列表
            if (
                (
                    DocumentLibrary.objects.filter(
                        document_id=d.id, del_flag=False, user_id=user_id,
                        task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
                    ).exists()
                    or d.collection_id == user_id)
                and d.object_path
            ):
                temp = {
                    'id': d.id,
                    'doc_apa': data_dict[d.id]['doc_apa'],
                    'has_full_text': True,
                }

            if not temp:
                temp = {
                    'id': d.id,
                    'doc_apa': data_dict[d.id]['doc_apa'],
                    'has_full_text': False,
                }
            temp_res_data.append(temp)
        for i, d in enumerate(temp_res_data):
            d['doc_apa'] = f"[{start_num + i + 1}] {d['doc_apa']}"
            res_data.append(d)
    else:
        res_data = CollectionDocumentListCollectionSerializer(docs, many=True).data
        if vd['list_type'] == 'all_documents':
            query_set, doc_lib_document_ids, sub_bot_document_ids, ref_documents = \
                CollectionDocumentListSerializer.get_collection_documents(vd['user_id'], collection_ids, 'personal')
            document_ids = [cd['document_id'] for cd in query_set.all()]
            for index, d_id in enumerate(res_data):
                if d_id['id'] in document_ids:
                    res_data[index]['type'] = 'personal'
        else:
            for index, d_id in enumerate(res_data):
                res_data[index]['type'] = vd['list_type']
    return {
        'list': res_data,
        # 个人库库文献 不能在添加到个人库
        'is_all_in_document_library': True if vd['list_type'] == 'personal' else False,
        'total': total,
        'show_total': query_total,
    }


def collection_chat_operation_check(user_id, validated_data):
    subscribe_collection_id_prefix = 'bot_'  # 订阅收藏夹id拼装：'bot_<bot_id>'
    vd = validated_data
    ids = vd['ids'] if vd.get('ids') else []
    # 过滤订阅收藏夹
    ids = [cid for cid in ids if not cid.startswith(subscribe_collection_id_prefix)]
    # 过滤无效collection_id
    collections = Collection.objects.filter(id__in=ids, del_flag=False).all()
    ids = [c.id for c in collections]

    public_collections = RagCollection.list()
    public_collection_ids = [pc['id'] for pc in public_collections]
    if vd.get('is_all'):
        personal_collections = Collection.objects.filter(user_id=user_id, del_flag=False).all()
        real_collection_ids = [c.id for c in personal_collections] + public_collection_ids
        ids = list(set(real_collection_ids) - set(ids))
    return 0, {'collection_ids': ids}


def collection_delete_operation_check(user_id, validated_data):
    vd = validated_data
    ids = vd['ids'] if vd.get('ids') else []
    if vd.get('is_all'):
        filter_query = Q(user_id=user_id, del_flag=False)
        if vd.get('ids'):
            filter_query &= ~Q(id__in=vd['ids'])
        all_colls = Collection.objects.filter(filter_query).all()
        ids = [c.id for c in all_colls]
    has_reference_bots, bot_titles = _collection_ref_bots(user_id, ids)
    if has_reference_bots:
        return 140003, {
            'msg': f'您当前删除收藏夹，涉及 {len(bot_titles)}条 已生成专题，如删除收藏夹后，将自动更新该专题中对应文献列表。',
            'bot_titles': bot_titles,
        }
    else:
        return 0, ''


def collections_create_bot_check(user_id, collection_ids=None, bot_id=None):
    if not collection_ids:
        collection_ids = []
    if bot_id:
        collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
        collection_ids += [c.collection_id for c in collections]
    query_set, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(user_id, collection_ids, 'all')
    document_ids = [cd['document_id'] for cd in query_set.all()]
    # 是否有关联文献
    filter_query = Q(document_id__in=document_ids, del_flag=False, user_id=user_id,
                     task_status=DocumentLibrary.TaskStatusChoices.COMPLETED,
                     filename__isnull=False)
    person_doc_lib = DocumentLibrary.objects.filter(filter_query).all()
    personal_doc = Document.objects.filter(
        collection_id=user_id, del_flag=False, id__in=document_ids,
        collection_type=Document.TypeChoices.PERSONAL
    ).values('id').all()
    all_person_doc_ids = [pd['id'] for pd in personal_doc] + [pd.document_id for pd in person_doc_lib]
    personal_docs = Document.objects.filter(id__in=all_person_doc_ids)
    if not personal_docs:
        return 0, ''
    ref_docs = [[pd.ref_doc_id, pd.ref_collection_id] for pd in personal_docs.all() if pd.ref_doc_id]
    # 包含未关联到公共库或公共库中无法获取全文的个人上传文件
    if personal_docs.count() != len(ref_docs):
        return 110005, '您当前专题中包含未关联到公共库或公共库中无法获取全文的个人上传文件，订阅该专题的其他用户将无法针对该文献进行智能对话或智能对话中部分功能无法使用。'
    else:
        # 关联文献是否有全文
        filter_query = None
        for rd in ref_docs:
            if not filter_query:
                filter_query = Q(doc_id=rd[0], collection_id=rd[1], full_text_accessible=None)
            else:
                filter_query |= Q(doc_id=rd[0], collection_id=rd[1], full_text_accessible=None)
        if Document.objects.filter(filter_query).exists():
            return 110005, '您当前专题中包含未关联到公共库或公共库中无法获取全文的个人上传文件，订阅该专题的其他用户将无法针对该文献进行智能对话或智能对话中部分功能无法使用。'
    return 0, ''


def collections_published_bot_titles(collection_ids):
    is_in_published_bot, bot_titles = _is_collection_in_published_bot(collection_ids)
    return is_in_published_bot, bot_titles


def collections_reference_bot_titles(user_id, collection_ids):
    has_reference_bots, bot_titles = _collection_ref_bots(user_id, collection_ids)
    return has_reference_bots, bot_titles