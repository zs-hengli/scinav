import datetime
import logging

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from bot.models import Bot, BotCollection, BotSubscribe, HotBot
from bot.rag_service import Bot as RagBot
from bot.serializers import (BotDetailSerializer, BotListAllSerializer, HotBotListSerializer, BotListChatMenuSerializer)
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionCreateSerializer
from core.utils.exceptions import InternalServerError, ValidationError
from document.models import Document
from document.serializers import DocumentListSerializer

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
    collections = Collection.objects.filter(id__in=body['collections']).all()
    bot_subscribe_collections = [c for c in collections if c.bot_id]
    if bot_subscribe_collections:
        raise ValidationError(_('订阅专题收藏夹不能用于创建专题'))
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        data['user_id'],
        data['prompt'],
        data['questions'],
        paper_ids=_collections_doc_ids(collections),
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


def _collections_doc_ids(collections: list[Collection]):
    _cids = [c.id for c in collections if c.type == c.TypeChoices.PERSONAL]
    c_docs = CollectionDocument.objects.filter(collection_id__in=_cids).all()
    return [{
        'collection_id': c_doc.document.collection_id,
        'collection_type': Collection.TypeChoices.PERSONAL,
        'doc_id': c_doc.document.doc_id} for c_doc in c_docs
    ]


# 修改专题
def bot_update(bot, bot_collections, updated_attrs, validated_data):
    bc_ids = [bc.collection_id for bc in bot_collections]
    collections = Collection.objects.filter(id__in=validated_data['collections'], del_flag=False).all()
    c_dict = {c.id: c for c in collections}
    c_ids = [c.id for c in collections]
    need_recreate_attrs = ['questions', 'prompt_spec', 'collections']
    if set(need_recreate_attrs) & set(updated_attrs):
        _recreate_bot(bot, collections)
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


def _recreate_bot(bot: Bot, collections):
    RagBot.delete(bot.agent_id)
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        bot.user_id,
        bot.prompt,
        bot.questions,
        paper_ids=_collections_doc_ids(collections),
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


# 删除专题
def bot_delete(bot_id):
    bot = Bot.objects.get(pk=bot_id)
    RagBot.delete(bot.agent_id)
    BotCollection.objects.filter(bot_id=bot.id).update(del_flag=True)
    bot.del_flag = True
    bot.save()
    return bot_id


# 专题详情
def bot_detail(user_id, bot_id):
    bot = Bot.objects.get(pk=bot_id)
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


# 专题文献列表
# bot collection list
def bot_docs(bot_id):
    ag_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
    collections = [ag_c.collection for ag_c in ag_collections]
    collection_ids = [c.id for c in collections]
    c_documents = CollectionDocument.objects.filter(collection_id__in=collection_ids, del_flag=False).all()
    return DocumentListSerializer(c_documents, many=True).data


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
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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
def bot_documents(bot_id, page_size=10, page_num=1):
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections]
    query_set = CollectionDocument.objects.filter(
        collection_id__in=collection_ids).distinct().values('document_id').order_by('document_id')
    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)] if total > start_num else []
    docs = Document.objects.filter(id__in=[cd['document_id'] for cd in c_docs]).all()
    # docs = [cd.document for cd in c_docs]
    docs_data = DocumentListSerializer(docs, many=True).data

    public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    res_data = []
    if public_collections:
        for p_c in public_collections:
            res_data.append({
                'id': None,
                'doc_apa': f"{_('公共库')}: {p_c.title}"
            })
    for i, d in enumerate(docs_data):
        d['doc_apa'] = f"[{start_num + i + 1}] {d['doc_apa']}"
        res_data.append(d)

    return {
        'list': res_data,
        'total': total
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
    bot.save()
    return 0, ''
