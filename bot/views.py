import logging

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.base_service import bot_detail, bot_documents
from bot.models import Bot, HotBot, BotTools
from bot.rag_service import Bot as RagBot
from bot.serializers import BotCreateSerializer, BotListQuerySerializer, BotDocumentsQuerySerializer, \
    BotToolsCreateQuerySerializer, BotToolsUpdateQuerySerializer, BotToolsDeleteQuerySerializer, BotDetailSerializer, \
    MyBotListAllSerializer
from bot.service import (bot_create, bot_delete, bot_publish, bot_subscribe, bot_update, hot_bots, get_bot_list,
                         bot_tools_create, bot_tools_update, formate_bot_tools, del_invalid_bot_tools,
                         bot_tools_add_bot_id, bot_user_full_text_document_ids, bots_plaza, bots_advance_share_info)
from document.tasks import async_add_user_operation_log
from core.utils.exceptions import ValidationError
from core.utils.views import extract_json, my_json_response

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'bot index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'DELETE']), name='dispatch')
@permission_classes([AllowAny])
class HotBots(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        data = hot_bots()
        return my_json_response(data)

    @staticmethod
    def post(request, bot_id, order=1, *args, **kwargs):
        bot = Bot.objects.filter(pk=bot_id).first()
        query = request.data
        if not bot:
            return my_json_response(code=100002, msg=_('bot not found'))
        if bot.type != Bot.TypeChoices.PUBLIC:
            return my_json_response(code=100001, msg=_('bot is not published'))
        hot_bot_data = {
            'bot_id': bot_id,
            'order_num': order,
            'del_flag': False,
        }
        if query.get('action') and query['action'] == 'delete':
            hot_bot_data['del_flag'] = True
        if query.get('order_num'):
            hot_bot_data['order_num'] = query['order_num']
        HotBot.objects.update_or_create(hot_bot_data, bot_id=bot_id)
        return my_json_response(hot_bot_data)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        hot_bot = HotBot.objects.filter(bot_id=bot_id).first()
        if not hot_bot:
            return my_json_response(code=100002, msg=_('hot_bot not found'))
        hot_bot.del_flag = True
        hot_bot.save()
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
class Bots(APIView):

    @staticmethod
    def get(request, bot_id=None, *args, **kwargs):
        user_id = request.user.id
        query = request.query_params.dict()
        if bot_id:
            bot = Bot.objects.filter(pk=bot_id).first()
            if not bot:
                return my_json_response(code=100002, msg=_('bot not found'))
            data = bot_detail(user_id, bot)
            async_add_user_operation_log.apply_async(kwargs={
                'user_id': user_id,
                'operation_type': 'bot_detail',
                'obj_id1': bot.id,
                'obj_id2': query['from'][:32] if query.get('from') else None,
            })
        else:
            query_data = kwargs['request_data']['GET']
            query_data['user_id'] = user_id
            serial = BotListQuerySerializer(data=query_data)
            if not serial.is_valid():
                return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
            data = get_bot_list(serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        user_id = request.user.id
        request_data = request.data
        request_data['user_id'] = user_id
        serial = BotCreateSerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        tools = None
        if vd.get('tools'):
            vd['tools'], tools = formate_bot_tools(vd['tools'])
        bot = bot_create(vd)
        tool_ids = []
        if tools:
            bot.tools, _ = bot_tools_add_bot_id(bot.id, tools)
            tool_ids = [t['id'] for t in bot.tools]
            bot.save()
        del_invalid_bot_tools(bot.id, tool_ids)

        data = BotDetailSerializer(bot).data
        return my_json_response(data)

    @staticmethod
    def put(request, bot_id, *args, **kwargs):
        bot = Bot.objects.filter(pk=bot_id).first()
        if not bot:
            return my_json_response({}, code=100002, msg='validate bot_id error')
        if bot.user_id != request.user.id:
            return my_json_response({}, code=100003, msg='no permission')
        request_data = request.data
        request_data['user_id'] = request.user.id
        serial = BotCreateSerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        tool_ids = []
        if vd.get('tools'):
            vd['tools'], _ = formate_bot_tools(vd['tools'])
            tool_ids = [t['id'] for t in vd['tools']]
        del_invalid_bot_tools(bot.id, tool_ids)
        del vd['type']  # update bot not update type
        updated_bot, bot_collections, updated_attrs = serial.updated_attrs(bot, vd)
        data = bot_update(updated_bot, bot_collections, updated_attrs, vd)
        return my_json_response(data)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        # if HotBot.objects.filter(bot_id=bot_id, del_flag=False).exists():
        #     return my_json_response({}, code=100003, msg=_('bot is hot, can not delete'))
        bot_delete(bot_id)
        return my_json_response({'bot_id': bot_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST', 'PUT', 'DELETE', ]), name='dispatch')
class BotsTools(APIView):
    @staticmethod
    def post(request, *args, **kwargs):
        request_data = request.data
        bot_id = request_data.get('bot_id', None)
        if bot_id:
            bot = Bot.objects.filter(pk=bot_id).first()
            if not bot:
                return my_json_response({}, code=100002, msg='bot_id is illegal')
        serial = BotToolsCreateQuerySerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        # check tool
        validate_data = serial.validated_data
        tools_res = RagBot.openapi_tools(
            validate_data['name'], validate_data['url'], validate_data['openapi_json_path'],
            validate_data['endpoints']
        )
        if not tools_res:
            return my_json_response({}, code=110007, msg='AI工具校验失败，请检查AI工具信息')
        _, data = bot_tools_create(request.user.id, bot_id, validate_data, checked=True)
        return my_json_response(data)

    @staticmethod
    def put(request, *args, **kwargs):
        request_data = request.data
        bot_id = request_data.get('bot_id', None)
        if bot_id:
            bot = Bot.objects.filter(pk=bot_id).first()
            if not bot:
                return my_json_response({}, code=100002, msg='bot_id is illegal')
        bot_tool = BotTools.objects.filter(user_id=request.user.id, bot_id=bot_id, pk=request_data['id']).first()
        if not bot_tool:
            return my_json_response({}, code=100002, msg='tool_id is illegal')
        serial = BotToolsUpdateQuerySerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        # check tool
        validate_data = serial.validated_data
        tools_res = RagBot.openapi_tools(
            validate_data['name'], validate_data['url'], validate_data['openapi_json_path'],
            validate_data['endpoints']
        )
        if not tools_res:
            return my_json_response({}, code=110007, msg='AI工具校验失败，请检查AI工具信息')
        _, data = bot_tools_update(bot_tool, validate_data)
        return my_json_response(data)

    @staticmethod
    def delete(request, *args, **kwargs):
        request_data = request.data
        bot_id = request_data.get('bot_id', None)
        if bot_id:
            bot = Bot.objects.filter(pk=bot_id).first()
            if not bot:
                return my_json_response({}, code=100002, msg='bot_id is illegal')
        serial = BotToolsDeleteQuerySerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        validated_data = serial.validated_data
        tool = BotTools.objects.filter(user_id=request.user.id, bot_id=bot_id, pk=validated_data['id']).first()
        if not tool:
            return my_json_response({}, code=100002, msg='tools id is illegal')
        return my_json_response({'id': bot_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class BotSubscribe(APIView):

    @staticmethod
    def post(request, bot_id, action, *args, **kwargs):
        user_id = request.user.id
        action_map = ['subscribe', 'unsubscribe']
        if action not in action_map:
            raise ValidationError(f'action is illegal must in {action_map}')
        bot = Bot.objects.filter(pk=bot_id).first()
        if not bot:
            return my_json_response({}, code=100002, msg='bot_id is illegal')
        if bot.user_id == user_id:
            return my_json_response({}, code=100003, msg='can not subscribe self bot')
        bot_subscribe(user_id, bot, action)
        # 专题拥有者有专题文章的全文访问权限的公共库document_ids
        documents_ids = bot_user_full_text_document_ids(bot=bot)
        return my_json_response({
            'bot_id': bot_id,
            'bot_user_has_full_text_documents': True if documents_ids else False
        })


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class BotDocuments(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):
        query = request.query_params.dict()
        query['bot_id'] = bot_id
        bot = Bot.objects.filter(pk=bot_id).first()
        if not bot:
            return my_json_response({}, code=100002, msg=_('bot_id is illegal'))
        serial = BotDocumentsQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        docs = bot_documents(request.user.id, bot, vd['list_type'], vd['page_size'], vd['page_num'], vd['keyword'])
        return my_json_response(docs)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class BotPublish(APIView):

    @staticmethod
    def get(request, bot_id, order=0, *args, **kwargs):
        if isinstance(order, str) and not order.isdigit():
            return my_json_response({}, code=100001, msg='order must be int')
        order = int(order)
        code, msg, data = bot_publish(bot_id, order=order)
        return my_json_response(code=code, msg=msg, data=data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class BotUnPublish(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):
        bot = Bot.objects.filter(pk=bot_id).first()
        if not bot:
            return my_json_response({}, 100002, 'bot not exists')
        bot.type = Bot.TypeChoices.PERSONAL
        bot.pub_date = None
        bot.order = 0
        bot.save()
        return my_json_response(MyBotListAllSerializer(bot).data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class BotsPlaza(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        data = bots_plaza()
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class BotsAdvanceShare(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        bot_id = query.get('bot_id', None)
        bot = None
        if bot_id:
            bot = Bot.objects.filter(pk=bot_id).first()
            if not bot:
                return my_json_response({}, 100002, 'bot not exists')
        data = bots_advance_share_info(request.user.id, bot)
        return my_json_response(data)
