import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

import bot.models
from bot.service import (bot_create, bot_delete, bot_detail, bot_documents,
                         bot_list_all, bot_list_my, bot_list_subscribe,
                         bot_publish, bot_subscribe, bot_update, hot_bots)
from core.utils.exceptions import ValidationError
from core.utils.views import check_keys, extract_json, my_json_response

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
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class HotBot(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        data = hot_bots()
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
@permission_classes([AllowAny])
class Bot(APIView):

    @staticmethod
    def get(request, bot_id=None, *args, **kwargs):
        user_id = request.user.id
        if bot_id:
            data = bot_detail(user_id, bot_id)
        else:
            query_data = kwargs['request_data']['GET']
            params = {
                'page_size': int(query_data.get('page_size', 10)),
                'page_num': int(query_data.get('page_num', 1)),
                'list_type': query_data.get('list_type', 'all')
            }
            list_type_map = ['all', 'my', 'subscribe']
            if params['list_type'] not in list_type_map:
                raise ValidationError(f'list_type is illegal must in {list_type_map}')
            if params['list_type'] == 'all':
                data = bot_list_all(user_id, params['page_size'], params['page_num'])
            elif params['list_type'] == 'my':
                data = bot_list_my(user_id, params['page_size'], params['page_num'])
            else:
                data = bot_list_subscribe(user_id, params['page_size'], params['page_num'])
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        body = kwargs['request_data']['JSON']
        user_id = request.user.id
        check_keys(body, ['author', 'title', 'description', 'collections'])
        post_data = {
            'user_id': user_id,
            'author': body['author'],
            'title': body['title'],
            'description': body['description'],
            'prompt_spec': body.get('prompt_spec', None),
            'questions': body.get('questions', None),
            'llm': None,
            'tools': None,
            'cover_url': None,
            'type': bot.models.Bot.TypeChoices.PERSONAL,
            'collections': body['collections']
        }
        if not isinstance(post_data['collections'], list):
            raise ValidationError("collections is not a list[string]")
        data = bot_create(post_data)
        return my_json_response(data)

    @staticmethod
    def put(request, bot_id, *args, **kwargs):
        body = kwargs['request_data']['JSON']
        body['user_id'] = request.user.id
        data = bot_update(bot_id, body)
        return my_json_response(data)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        bot_delete(bot_id)
        return my_json_response({'bot_id': bot_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
# @permission_classes([AllowAny])
class BotSubscribe(APIView):

    @staticmethod
    def post(request, bot_id, action, *args, **kwargs):
        user_id = request.user.id
        action_map = ['subscribe', 'unsubscribe']
        if action not in action_map:
            raise ValidationError(f'action is illegal must in {action_map}')
        bot_subscribe(user_id, bot_id, action)
        return my_json_response({'bot_id': bot_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
# @permission_classes([AllowAny])
class BotDocuments(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):
        query = kwargs['request_data']['GET']
        query_data = {
            'page_size': int(query.get('page_size', 10)),
            'page_num': int(query.get('page_num', 1)),
        }
        docs = bot_documents(bot_id, query_data['page_size'], query_data['page_num'])
        return my_json_response(docs)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
# @permission_classes([AllowAny])
class BotPublish(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):
        code, msg = bot_publish(bot_id)
        return my_json_response(code=code, msg=msg, data={})
