import logging

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.base_service import bot_detail, bot_documents
from bot.models import Bot, HotBot
from bot.serializers import BotCreateSerializer, BotListQuerySerializer, BotDocumentsQuerySerializer
from bot.service import (bot_create, bot_delete, bot_publish, bot_subscribe, bot_update, hot_bots, get_bot_list)
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
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class HotBots(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        data = hot_bots()
        return my_json_response(data)

    @staticmethod
    def post(request, bot_id, *args, **kwargs):
        bot = Bot.objects.filter(pk=bot_id).first()
        query = request.data
        if not bot:
            return my_json_response(code=100002, msg=_('bot not found'))
        if bot.type != Bot.TypeChoices.PUBLIC:
            return my_json_response(code=100001, msg=_('bot is not published'))
        hot_bot_data = {
            'bot_id': bot_id,
            'order_num': 1,
            'del_flag': False,
        }
        if query.get('action') and query['action'] == 'delete':
            hot_bot_data['del_flag'] = True
        if query.get('order_num'):
            hot_bot_data['order_num'] = query['order_num']
        HotBot.objects.update_or_create(hot_bot_data, bot_id=bot_id)
        return my_json_response(hot_bot_data)


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

        data = bot_create(serial.validated_data)
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
        validated_data = serial.validated_data
        del validated_data['type']  # update bot not update type
        updated_bot, bot_collections, updated_attrs = serial.updated_attrs(bot, validated_data)
        data = bot_update(updated_bot, bot_collections, updated_attrs, validated_data)
        return my_json_response(data)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        # if HotBot.objects.filter(bot_id=bot_id, del_flag=False).exists():
        #     return my_json_response({}, code=100003, msg=_('bot is hot, can not delete'))
        bot_delete(bot_id)
        return my_json_response({'bot_id': bot_id})


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
            return my_json_response({}, code=100002, msg=_('bot_id is illegal'))
        if bot.user_id == user_id:
            return my_json_response({}, code=100003, msg=_('can not subscribe self bot'))
        bot_subscribe(user_id, bot_id, action)
        return my_json_response({'bot_id': bot_id})


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
        docs = bot_documents(request.user.id, bot, vd['list_type'], vd['page_size'], vd['page_num'])
        return my_json_response(docs)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class BotPublish(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):
        code, msg = bot_publish(bot_id)
        return my_json_response(code=code, msg=msg, data={})
