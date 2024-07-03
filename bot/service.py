import datetime
import logging

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bot.base_service import recreate_bot, collections_doc_ids, mine_bot_document_ids
from bot.models import Bot, BotCollection, BotSubscribe, HotBot, BotTools
from bot.rag_service import Bot as RagBot
from bot.serializers import (BotDetailSerializer, BotListAllSerializer, HotBotListSerializer, BotListChatMenuSerializer,
                             MyBotListAllSerializer, BotToolsDetailSerializer, BotToolsUpdateQuerySerializer,
                             BotsPlazaResultsSerializer)
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer, bot_subscribe_personal_document_num
from core.utils.exceptions import InternalServerError, ValidationError
from document.base_service import update_document_lib
from document.models import Document, DocumentLibrary
from document.tasks import async_schedule_publish_bot_task, async_ref_document_to_document_library

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
        'tools': body['tools'],
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
        tools=data['tools'],
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
    return bot


# 修改专题
def bot_update(bot, bot_collections, updated_attrs, validated_data):
    bc_ids = [bc.collection_id for bc in bot_collections]
    collections = Collection.objects.filter(id__in=validated_data['collections'], del_flag=False).all()
    c_dict = {c.id: c for c in collections}
    c_ids = [c.id for c in collections]
    need_recreate_attrs = ['questions', 'prompt_spec', 'collections', 'tools']
    if set(need_recreate_attrs) & set(updated_attrs):
        recreate_bot(bot, collections)
    # update ref_document_to_document_library
    if bot.type == Bot.TypeChoices.PUBLIC:
        for collection_id in validated_data['collections']:
            if collection_id not in bc_ids:
                document_ids = CollectionDocument.objects.filter(
                    collection_id=collection_id, del_flag=False).values_list('document_id', flat=True).all()
                async_ref_document_to_document_library.apply_async(args=[list(document_ids)])
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


# 专题列表
def hot_bots():
    hot_bot = HotBot.objects.filter(del_flag=False, bot__del_flag=False).order_by('order_num', '-updated_at').all()
    hot_bot_list_data = HotBotListSerializer(hot_bot, many=True).data
    return hot_bot_list_data


def get_bot_list(validated_data):
    vd = validated_data
    if validated_data['list_type'] == 'all':
        bot_list = bot_list_all(vd['user_id'], vd['page_size'], vd['page_num'])
    elif validated_data['list_type'] == 'my':
        bot_list = bot_list_mine(vd['user_id'], vd['page_size'], vd['page_num'])
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
    order0_query_set = Bot.objects.filter(
        type=Bot.TypeChoices.PUBLIC, del_flag=False, order=0).order_by('-updated_at')
    order_query_set = Bot.objects.filter(
        type=Bot.TypeChoices.PUBLIC, del_flag=False, order__gt=0).order_by('order', '-updated_at')
    order_filter_count = order_query_set.count()
    order0_filter_count = order0_query_set.count()
    start_num = page_size * (page_num - 1)
    end_num = start_num + page_size
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    order_bots = list(order_query_set[start_num:end_num])
    order0_bots = []
    # 如果获取的 order > 0 的结果不足页大小，则补充 order = 0 的结果
    remaining_slots = page_size - len(order_bots)
    if remaining_slots > 0:
        order0_bots_start = max(0, start_num - order_filter_count)
        order0_bots_end = order0_bots_start + remaining_slots
        order0_bots = list(order0_query_set[order0_bots_start:order0_bots_end])
    bots = order_bots + order0_bots

    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = False
        if b_data['id'] in us_bot_ids:
            bot_list_data[index]['subscribed'] = True
    return {
        'list': bot_list_data,
        'total': order_filter_count + order0_filter_count
    }


def bots_plaza():
    order0_query_set = Bot.objects.filter(
        type=Bot.TypeChoices.PUBLIC, del_flag=False, order=0).order_by('-updated_at')
    order_query_set = Bot.objects.filter(
        type=Bot.TypeChoices.PUBLIC, del_flag=False, order__gt=0).order_by('order', '-updated_at')
    bots = list(order_query_set) + list(order0_query_set)
    data = BotsPlazaResultsSerializer(bots, many= True).data
    return data


def bot_list_subscribe(user_id, page_size=10, page_num=1):
    user_subscribe_bot = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bot_ids = [us_bot.bot_id for us_bot in user_subscribe_bot]
    filter_query = Q(del_flag=False) & (Q(id__in=bot_ids) | Q(user_id=user_id))
    query_set = Bot.objects.filter(filter_query).order_by('-pub_date')
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


def bot_list_mine(user_id, page_size=10, page_num=1):
    query_set = Bot.objects.filter(user_id=user_id, del_flag=False).order_by('-created_at')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]
    bot_dict = {b.id: b for b in bots}
    bot_list_data = MyBotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['doc_total'] = _mine_bot_documents_total(bot_dict[b_data['id']])
        bot_list_data[index]['subscribed'] = True

    return {
        'list': bot_list_data,
        'total': filter_count
    }


def _mine_bot_documents_total(bot):
    total = 0
    collections = BotCollection.objects.filter(
        bot_id=bot.id, del_flag=False).values_list('collection_id', flat=True).all()
    public_collection_ids = Collection.objects.filter(
        id__in=collections, type=Collection.TypeChoices.PUBLIC, del_flag=False).values('id', 'total_public').all()
    if public_collection_ids:
        total += sum([p_c['total_public'] for p_c in public_collection_ids])
    total += CollectionDocument.objects.filter(
        collection_id__in=collections, del_flag=False).values('document_id').distinct('document_id').count()
    return total


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
    data = {
        'user_id': user_id,
        'bot_id': bot_id,
        'del_flag': action != 'subscribe'
    }
    BotSubscribe.objects.update_or_create(data, user_id=user_id, bot_id=bot_id)


def bot_user_full_text_document_ids(bot_id=None, bot: Bot = None):
    """
    专题创建者拥有全文权限的公共库文献id
    """
    if not bot:
        bot = Bot.objects.get(pk=bot_id)
    bot_id = bot.id
    bot_document_ids = mine_bot_document_ids(bot_id)
    bot_document_lib_ids = DocumentLibrary.objects.filter(
        user_id=bot.user_id,
        del_flag=False,
        document_id__in=set(bot_document_ids),
        # task_type='public',
        task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
        ).values_list('document_id', flat=True).all()
    document_ids = Document.objects.filter(
        id__in=bot_document_lib_ids, full_text_accessible=True, del_flag=False).values_list('id', flat=True).all()
    return list(document_ids)


def bot_publish(bot_id, order, action=Bot.TypeChoices.PUBLIC):
    bot = Bot.objects.filter(pk=bot_id).first()
    if not bot:
        return 100002, 'bot not exist', {}
    if bot.type == Bot.TypeChoices.IN_PROGRESS:
        return 110006, 'bot publish is in progress', {}

    if action == Bot.TypeChoices.PUBLIC:
        bot.type = Bot.TypeChoices.IN_PROGRESS
        bot.pub_date = datetime.datetime.now()
        bot.order = order
        # 个人文献 下载关联公共库文献
        p_documents, ref_documents = bot_subscribe_personal_document_num(bot.user_id, bot=bot)
        if ref_documents:
            update_document_lib('0000', ref_documents)
        elif action == Bot.TypeChoices.PUBLIC:
            bot.type = Bot.TypeChoices.PUBLIC
    else:
        bot.type = Bot.TypeChoices.PERSONAL
    bot.save()
    async_schedule_publish_bot_task.apply_async()
    return 0, '', MyBotListAllSerializer(bot).data


def bot_tools_create(user_id, bot_id, validated_data: dict, checked=False):
    vd = validated_data
    tool = BotTools(
        user_id=user_id,
        bot_id=bot_id,
        name=vd['name'],
        url=vd['url'],
        openapi_json_path=vd['openapi_json_path'],
        auth_type=vd['auth_type'],
        username_password_base64=vd['username_password_base64'],
        token=vd['token'],
        api_key=vd['api_key'],
        custom_header=vd['custom_header'],
        endpoints=vd['endpoints'],
        checked=checked,
    )
    tool.save()
    return tool, BotToolsDetailSerializer(tool).data


def bot_tools_update(tool: BotTools, validated_data: dict):
    serial = BotToolsDetailSerializer(tool)
    tool = serial.update(tool, validated_data)
    return tool, BotToolsDetailSerializer(tool).data


def formate_bot_tools(query_tools):
    tools = BotTools.objects.filter(pk__in=[t['id'] for t in query_tools], del_flag=False).all()
    formate_tools = BotToolsUpdateQuerySerializer(tools, many=True).data
    return formate_tools, tools


def bot_tools_add_bot_id(bot_id, tools):
    for tool in tools:
        if not tool.bot_id:
            tool.bot_id = bot_id
            tool.save()
    formate_tools = BotToolsUpdateQuerySerializer(tools, many=True).data
    return formate_tools, tools


def del_invalid_bot_tools(bot_id, valid_tool_ids):
    filter_query = Q(bot_id=bot_id, del_flag=False) & ~Q(id__in=valid_tool_ids)
    BotTools.objects.filter(filter_query).update(del_flag=True)
