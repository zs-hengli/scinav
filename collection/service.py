import datetime
import logging

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from bot.models import BotCollection, BotSubscribe, Bot
from bot.rag_service import Collection as RagCollection, Conversations as RagConversations
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionPublicSerializer, CollectionListSerializer, CollectionRagPublicListSerializer, \
    CollectionSubscribeSerializer
from core.utils.exceptions import ValidationError
from document.models import Document, DocumentLibrary
from document.serializers import DocumentApaListSerializer
from document.service import search_result_from_cache

logger = logging.getLogger(__name__)


def collection_list(user_id, list_type, page_size, page_num):
    coll_list = []
    start_num = page_size * (page_num - 1)
    # 1 public collections
    public_total, subscribe_total, sub_add_list, my_total = 0, 0, [], 0
    if 'public' in list_type:
        public_collections = RagCollection.list()
        public_collections = [pc | {'updated_at': pc['update_time']} for pc in public_collections]
        pub_serial = CollectionRagPublicListSerializer(data=public_collections, many=True)
        pub_serial.is_valid(raise_exception=True)
        public_total = len(pub_serial.data)
        if start_num == 0:
            coll_list = pub_serial.data
            ids = [c['id'] for c in public_collections]
            if Collection.objects.filter(id__in=ids, del_flag=False).count() != len(ids):
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
            coll['is_in_published_bot'], coll['bot_titles'] = _is_collection_in_published_bot(coll['id'])
    return {
        'list': coll_list,
        'total': my_total + subscribe_total + public_total,
    }


def _is_collection_in_published_bot(collection_id):
    is_in_published_bot = BotCollection.objects.filter(
        collection_id=collection_id, del_flag=False, bot__type=Bot.TypeChoices.PUBLIC).exists()
    bot_titles = None
    if is_in_published_bot:
        bots = BotCollection.objects.filter(
            collection_id=collection_id, del_flag=False, bot__type=Bot.TypeChoices.PUBLIC).values('bot__title').all()
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
    bot_sub = BotSubscribe.objects.filter(bot__user_id=user_id, del_flag=False).all()
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
        effect_num = Collection.objects.filter(id__in=vd['ids'], del_flag=False).update(del_flag=True)
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
    if vd['list_type'] == 'all':
        public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
        if public_collections:
            for p_c in public_collections:
                res_data.append({
                    'id': None,
                    'doc_apa': f"{_('公共库')}: {p_c.title}"
                })
        query_set = CollectionDocument.objects.filter(
            collection_id__in=collection_ids, del_flag=False).values('document_id') \
            .order_by('document_id').distinct()
    elif vd['list_type'] == 'public':
        query_set = CollectionDocument.objects.filter(
            collection_id__in=collection_ids, del_flag=False, document__collection_type=Document.TypeChoices.PUBLIC
        ).values('document_id').order_by('document_id').distinct()
    else:
        # todo DocumentLibrary 完善后添加
        query_set = CollectionDocument.objects.filter(
            collection_id__in=collection_ids, del_flag=False, document__collection_type=Document.TypeChoices.PERSONAL
        ).values('document_id').order_by('document_id').distinct()

    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)]
    docs = Document.objects.filter(id__in=[cd['document_id'] for cd in c_docs]).all()

    docs_data = DocumentApaListSerializer(docs, many=True).data
    for i, d in enumerate(docs_data):
        d['doc_apa'] = f"[{start_num + i + 1}] {d['doc_apa']}"
        res_data.append(d)
    return {
        'list': res_data,
        'total': total
    }
