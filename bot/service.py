import datetime
import logging

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bot.base_service import recreate_bot, collections_doc_ids
from bot.models import Bot, BotCollection, BotSubscribe, HotBot
from bot.rag_service import Bot as RagBot
from bot.serializers import (BotDetailSerializer, BotListAllSerializer, HotBotListSerializer, BotListChatMenuSerializer)
from collection.models import Collection
from collection.serializers import CollectionDocumentListSerializer
from core.utils.exceptions import InternalServerError, ValidationError
from document.base_service import update_document_lib
from document.models import Document
from document.serializers import DocumentApaListSerializer, CollectionDocumentListCollectionSerializer

logger = logging.getLogger(__name__)


# 创建专题
def bot_create(body):
    data = {
        'user_id': body['user_id'],
        'author': body['author'],
        'title': body['title'],
        'description': body['description'],
        'prompt': body.get('prompt_spec', None),
        'questions': body['questions'],
        # 'llm': body['llm'],
        # 'tools': body['tools'],
        'cover_url': body['cover_url'],
        'type': body['type'],
    }
    data['prompt'] = {
        'type': 'SystemPrompt',
        "spec": {
            "system_prompt": data['prompt'],
        }
    }
    filter_query = (
        Q(id__in=body['collections'], del_flag=False) &
        (Q(user_id=body['user_id']) | Q(type=Collection.TypeChoices.PUBLIC))
    )
    collections = Collection.objects.filter(filter_query).all()
    bot_subscribe_collections = [c for c in collections if c.bot_id]
    if bot_subscribe_collections:
        raise ValidationError(_('订阅专题收藏夹不能用于创建专题'))
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        data['user_id'],
        data['prompt'],
        data['questions'],
        paper_ids=collections_doc_ids(collections),
        public_collection_ids=public_collection_ids,
    )
    if rag_ret.get('id'):
        data['extension'] = rag_ret
        data['agent_id'] = rag_ret['id']
        # data['prompt'] = rag_ret['spec']['prompt']
        bot = Bot.objects.create(**data)
        # save BotCollection
        for c in collections:
            bot_c_data = {
                'bot_id': bot.id,
                'collection_id': c.id,
                'collection_type': c.type
            }
            BotCollection.objects.create(**bot_c_data)
    else:
        raise InternalServerError('RAG create bot failed')
    return BotDetailSerializer(bot).data


# 修改专题
def bot_update(bot, bot_collections, updated_attrs, validated_data):
    bc_ids = [bc.collection_id for bc in bot_collections]
    collections = Collection.objects.filter(id__in=validated_data['collections'], del_flag=False).all()
    c_dict = {c.id: c for c in collections}
    c_ids = [c.id for c in collections]
    need_recreate_attrs = ['questions', 'prompt_spec', 'collections']
    if set(need_recreate_attrs) & set(updated_attrs):
        recreate_bot(bot, collections)
    # update BotCollection
    if to_add_ids := set(c_ids) - set(bc_ids):
        logger.debug(f'bot_update to_add_ids: {to_add_ids}')
        for c_id in to_add_ids:
            bc_data = {
                'bot_id': bot.id,
                'collection_id': c_id,
                'collection_type': c_dict[c_id].type
            }
            BotCollection.objects.update_or_create(
                bc_data, bot_id=bc_data['bot_id'], collection_id=bc_data['collection_id'])
    if to_dell_c_ids := set(bc_ids) - set(c_ids):
        logger.debug(f'bot_update to_dell_c_ids: {to_dell_c_ids}')
        BotCollection.objects.filter(bot_id=bot.id, collection_id__in=to_dell_c_ids).update(del_flag=True)
    bot.save()
    return BotDetailSerializer(bot).data


# 删除专题
def bot_delete(bot_id):
    bot = Bot.objects.get(pk=bot_id)
    RagBot.delete(bot.agent_id)
    BotCollection.objects.filter(bot_id=bot.id).update(del_flag=True)
    bot.del_flag = True
    bot.save()
    return bot_id


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
    # if bot.user_id == user_id:
    #     return True
    if BotSubscribe.objects.filter(user_id=user_id, bot=bot, del_flag=False).exists():
        return True
    return False


# 专题列表
def hot_bots():
    hot_bot = HotBot.objects.filter(del_flag=False, bot__del_flag=False).order_by('order_num').all()
    hot_bot_list_data = HotBotListSerializer(hot_bot, many=True).data
    return hot_bot_list_data


def get_bot_list(validated_data):
    vd = validated_data
    if validated_data['list_type'] == 'all':
        bot_list = bot_list_all(vd['user_id'], vd['page_size'], vd['page_num'])
    elif validated_data['list_type'] == 'my':
        bot_list = bot_list_my(vd['user_id'], vd['page_size'], vd['page_num'])
    elif validated_data['list_type'] == 'subscribe':
        bot_list = bot_list_subscribe(vd['user_id'], vd['page_size'], vd['page_num'])
    elif validated_data['list_type'] == 'chat_menu':
        bot_list = bot_list_chat_menu(vd['user_id'], vd['page_size'], vd['page_num'])
    else:
        raise ValidationError('list_type error')
    return bot_list


def bot_list_all(user_id, page_size=10, page_num=1):
    user_subscribe_bot = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    us_bot_ids = [us_b.bot_id for us_b in user_subscribe_bot]
    query_set = Bot.objects.filter(type=Bot.TypeChoices.PUBLIC, del_flag=False).order_by('-pub_date', '-created_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]
    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = False
        if b_data['id'] in us_bot_ids:
            bot_list_data[index]['subscribed'] = True
    return {
        'list': bot_list_data,
        'total': filter_count
    }


def bot_list_subscribe(user_id, page_size=10, page_num=1):
    user_subscribe_bot = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bot_ids = [us_bot.bot_id for us_bot in user_subscribe_bot]
    query_set = Bot.objects.filter(id__in=bot_ids, del_flag=False).order_by('-pub_date')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]

    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = True
    return {
        'list': bot_list_data,
        'total': filter_count
    }


def bot_list_my(user_id, page_size=10, page_num=1):
    query_set = Bot.objects.filter(user_id=user_id, del_flag=False).order_by('-created_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]

    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = True

    return {
        'list': bot_list_data,
        'total': filter_count
    }


def bot_list_chat_menu(user_id, page_size=10, page_num=1):
    """
    my bot + public bot
    """
    bot_sub = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    filter_query = (
        Q(user_id=user_id, del_flag=False)
        | Q(id__in=[b.bot_id for b in bot_sub], del_flag=False)
    )
    query_set = Bot.objects.filter(filter_query).order_by('-pub_date', '-created_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]
    bot_list_data = BotListChatMenuSerializer(bots, many=True).data
    return {
        'list': bot_list_data,
        'total': filter_count
    }


# 专题订阅和取消订阅
def bot_subscribe(user_id, bot_id, action='subscribe'):
    # 订阅： 加个人文件库 创建同名收藏夹
    # 取消订阅 删除收藏夹
    # todo 收藏夹有调整 增加文献时修改订阅者的个人文件库
    # if action == 'subscribe':
    #     bot = Bot.objects.filter(pk=bot_id).values_list('title', 'type', 'user_id', named=True).first()
    #     items = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
    #     total_public = sum(items.values_list('collection__total_public', flat=True))
    #     total_personal = sum(items.values_list('collection__total_personal', flat=True))
    #     collect_data = {
    #         'user_id': user_id,
    #         'title': bot.title,
    #         'type': Collection.TypeChoices.PERSONAL,
    #         'bot_id': bot_id,
    #         'total_public': total_public,
    #         'total_personal': total_personal,
    #         'del_flag': False,
    #     }
    #     Collection.objects.update_or_create(collect_data, user_id=user_id, bot_id=bot_id)
    # else:
    #     Collection.objects.filter(user_id=user_id, bot_id=bot_id).update(del_flag=True)
    data = {
        'user_id': user_id,
        'bot_id': bot_id,
        'del_flag': action != 'subscribe'
    }
    BotSubscribe.objects.update_or_create(data, user_id=user_id, bot_id=bot_id)


# 专题文献列表
def bot_documents(user_id, bot, list_type, page_size=10, page_num=1):
    bot_id = bot.id
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections]
    # query_set = CollectionDocument.objects.filter(
    #     collection_id__in=collection_ids).distinct().values('document_id').order_by('document_id')
    public_count, need_public, need_public_count, personal_count, public_collections = 0, False, 0, 0, []
    public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    public_collection_ids = [c.id for c in public_collections]
    if page_num == 1 and list_type in ['all', 'all_documents']:
        need_public_count = len(public_collections)
    elif page_num == 1 and list_type == 's2':
        if 's2' in public_collection_ids:
            need_public_count = 1
            public_collections = [pc for pc in public_collections if pc.id == 's2']
    elif page_num == 1 and list_type == 'arxiv':
        if 'arxiv' in public_collection_ids:
            need_public_count = 1
            public_collections = [pc for pc in public_collections if pc.id == 'arxiv']
    if page_num == 1 and list_type in ['all', 'all_documents', 's2', 'arxiv']:
        need_public = True
    public_count = len(public_collections)

    query_set, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
        user_id, collection_ids, list_type, bot)
    start_num = page_size * (page_num - 1)
    doc_ids = []
    show_total = 0
    # 个人上传文件库 关联的文献
    # 未发布专题 显示未公共库文献， 专题广场专题显示为订阅全文
    ref_doc_lib_ids = set(d3 if d3 else []) & set(CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id))
    if d3 and (
        list_type in ['all', 'all_documents']
        or (list_type in ['s2', 'arxiv'] and bot.type == Collection.TypeChoices.PERSONAL)
        or (list_type in ['subscribe_full_text'] and bot.type == Collection.TypeChoices.PUBLIC)
        or (list_type in ['personal'] and ref_doc_lib_ids)
    ):
        if list_type in ['personal']:
            d3 = list(ref_doc_lib_ids)
        elif list_type in ['s2', 'arxiv']:
            d3 = list(set(d3) - set(ref_doc_lib_ids))
        doc_ids = d3[start_num:(page_size * page_num - need_public_count)]
        need_public_count += len(doc_ids)
        public_count += len(d3)
        show_total += len(d3)
    personal_count = query_set.count()
    total = public_count + personal_count
    show_total += personal_count
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    if page_size * page_num > public_count:
        c_docs = query_set[start_num:(page_size * page_num - need_public_count)] if total > start_num else []
        doc_ids += [cd['document_id'] for cd in c_docs]
    docs = Document.objects.filter(id__in=doc_ids).all()
    # docs = [cd.document for cd in c_docs]
    res_data = []
    if list_type in ['all', 'all_documents', 's2', 'arxiv'] and public_collections and need_public:
        for p_c in public_collections:
            res_data.append({
                'id': None,
                'collection_id': p_c.id,
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
                'doc_apa': data_dict[doc.id]['doc_apa'],
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


def bot_publish(bot_id, action=Bot.TypeChoices.PUBLIC):
    bot = Bot.objects.filter(pk=bot_id).first()
    if not bot:
        return -1, 'bot not exist'
    if action == Bot.TypeChoices.PUBLIC:
        bot.type = Bot.TypeChoices.PUBLIC
        bot.pub_date = datetime.datetime.now()
    else:
        bot.type = Bot.TypeChoices.PERSONAL
    # 个人文献 下载关联公共库文献
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections]
    query_set, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
        bot.user_id, collection_ids, 'personal', bot)
    document_ids = [cd['document_id'] for cd in query_set.all()]
    documents = Document.objects.filter(id__in=document_ids).all()
    ref_documents = []
    for d in documents:
        ref_document = Document.objects.filter(
            collection_id=d.ref_collection_id, doc_id=d.ref_doc_id).values('id').first()
        if ref_document:
            ref_documents.append(ref_document['id'])
    if ref_documents:
        update_document_lib('0000', ref_documents)

    # 本人专题自动订阅
    # BotSubscribe.objects.update_or_create(
    #     user_id=bot.user_id, bot_id=bot_id, defaults={'del_flag': False})
    bot.save()
    return 0, ''
