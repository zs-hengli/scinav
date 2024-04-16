import datetime
import logging

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from bot.models import BotCollection, BotSubscribe, Bot
from bot.rag_service import Collection as RagCollection, Conversations as RagConversations
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionPublicSerializer, CollectionListSerializer, \
    CollectionRagPublicListSerializer, \
    CollectionSubscribeSerializer, CollectionDocumentListSerializer
from core.utils.exceptions import ValidationError
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
            coll['is_in_published_bot'], coll['bot_titles'] = _is_collection_in_published_bot([coll['id']])
    return {
        'list': coll_list,
        'total': my_total + subscribe_total + public_total,
    }


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
    coll_doc_num = DocumentLibrary.objects.filter(del_flag=False, user_id=user_id, document_id__in=doc_ids).values(
        'document_id').distinct('document_id').count()
    return len(doc_ids) == coll_doc_num


def _bot_subscribe_collection_list(user_id):
    bot_sub = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bot_ids = [bc.bot_id for bc in bot_sub]
    bots = Bot.objects.filter(id__in=bot_ids)
    bots_dict = {b.id: b for b in bots}
    bot_collections = BotCollection.objects.filter(
        bot_id__in=bot_ids, del_flag=False).order_by('bot_id', '-updated_at').all()
    bot_sub_collect = {}
    for bc in bot_collections:
        if bc.bot_id not in bot_sub_collect:
            bot_sub_collect[bc.bot_id] = {
                'id': None,
                'bot_id': bc.bot_id,
                'name': bots_dict[bc.bot_id].title,
                'type': Collection.TypeChoices.SUBSCRIBE,
                'updated_at': bc.updated_at,
                'total': 0,
            }
        bot_sub_collect[bc.bot_id]['total'] += bc.collection.total_public + bc.collection.total_personal
        bot_sub_collect[bc.bot_id]['updated_at'] = max(
            bot_sub_collect[bc.bot_id]['updated_at'], bc.collection.updated_at)
    return list(bot_sub_collect.values())


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
    if vd.get('is_all'):
        query_filter = Q(user_id=vd['user_id'], del_flag=False)
        if vd.get('ids'):
            query_filter &= ~Q(id__in=vd['ids'])
        effect_num = Collection.objects.filter(query_filter).update(del_flag=True)
    else:
        effect_num = Collection.objects.filter(
            id__in=vd['ids'], del_flag=False, type=Collection.TypeChoices.PERSONAL).update(del_flag=True)
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


def collections_docs(validated_data):
    vd = validated_data
    collection_ids = vd['collection_ids']
    page_size = vd['page_size']
    page_num = vd['page_num']
    res_data = []
    query_set = CollectionDocumentListSerializer.get_collection_documents(
        vd['user_id'], collection_ids, vd['list_type'])

    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)]
    docs = Document.objects.filter(id__in=[cd['document_id'] for cd in c_docs]).all()

    if vd['list_type'] == 'all':
        docs_data = DocumentApaListSerializer(docs, many=True).data
        for i, d in enumerate(docs_data):
            d['doc_apa'] = f"[{start_num + i + 1}] {d['doc_apa']}"
            res_data.append(d)
    else:
        res_data = CollectionDocumentListCollectionSerializer(docs, many=True).data
        if vd['list_type'] == 'all_documents':
            query_set = CollectionDocumentListSerializer.get_collection_documents(
                vd['user_id'], collection_ids, 'personal')
            document_ids = [cd['document_id'] for cd in query_set.all()]
            for index, d_id in enumerate(res_data):
                if d_id in document_ids:
                    res_data[index]['type'] = 'personal'
        else:
            for index, d_id in enumerate(res_data):
                res_data[index]['type'] = vd['list_type']
    return {
        'list': res_data,
        'total': total
    }


def collection_chat_operation_check(user_id, validated_data):
    subscribe_collection_id_prefix = 'bot_'  # 订阅收藏夹id拼装：'bot_<bot_id>'
    vd = validated_data
    ids = vd['ids'] if vd.get('ids') else []
    # 过滤无效collection_id
    sub_collection_ids = [cid for cid in ids if cid.startswith(subscribe_collection_id_prefix)]
    collections = Collection.objects.filter(id__in=ids, del_flag=False).all()
    ids = [c.id for c in collections] + sub_collection_ids

    public_collections = RagCollection.list()
    public_collection_ids = [pc['id'] for pc in public_collections]
    subscribe_collections = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    all_sub_collection_bot_ids = [f"{subscribe_collection_id_prefix}{sc.bot_id}" for sc in subscribe_collections]
    if vd.get('is_all'):
        personal_collections = Collection.objects.filter(user_id=user_id, del_flag=False).all()
        real_collection_ids = [c.id for c in personal_collections] + public_collection_ids
        ids = list(set(real_collection_ids + all_sub_collection_bot_ids) - set(ids))
    if (set(all_sub_collection_bot_ids) & set(ids)) and (set(ids) - set(all_sub_collection_bot_ids)):
        return 140002, '订阅收藏夹无法与其他收藏夹共同生成对话，请重新选择'
    # 全是 订阅收藏夹
    if set(all_sub_collection_bot_ids) & set(ids):
        if len(ids) > 1:  # 订阅收藏夹不能有多个
            return 140002, '订阅收藏夹无法与其他收藏夹共同生成对话，请重新选择'
        else:
            return 0, {'bot_id': ids[0][len(subscribe_collection_id_prefix):]}
    else:  # 全是公共收藏夹或者个人收藏夹
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
    is_in_published_bot, bot_titles = _is_collection_in_published_bot(ids)
    if is_in_published_bot:
        return 140003, {
            'msg': f'您当前删除收藏夹，涉及 {len(bot_titles)}条 已发布专题，如删除收藏夹后，将自动更新该专题中对应文献列表。',
            'bot_titles': bot_titles,
        }
    else:
        return 0, ''