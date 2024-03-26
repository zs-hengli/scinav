import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from chat.serializers import ConversationCreateSerializer, ConversationUpdateSerializer, ChatQuerySerializer, \
    QuestionAnswerSerializer
from chat.service import chat_query, conversation_create, conversation_detail, conversation_list, conversation_update, \
    conversation_menu_list
from core.utils.views import extract_json, my_json_response, check_keys, streaming_response

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
# @permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'chat index'}

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
# @permission_classes([AllowAny])
class Conversations(APIView):
    @staticmethod
    def get(request, conversation_id=None, *args, **kwargs):
        logger.debug(f"conversation_id: {conversation_id}")
        if conversation_id and conversation_id != 'menu':
            data = conversation_detail(conversation_id)
        else:
            query = kwargs['request_data']['GET']
            query_data = {
                'user_id': request.user.id,
                'type': query.get('type', 'list'),
                'page_size': int(query.get('page_size', 10)),
                'page_num': int(query.get('page_num', 1)),
            }
            if conversation_id == 'menu':
                data = conversation_menu_list(validated_data=query_data)
            else:
                data = conversation_list(validated_data=query_data)
        return my_json_response(data)

    @staticmethod
    def put(request, conversation_id, *args, **kwargs):
        query_data = request.data
        query_data['user_id'] = request.user.id
        serial = ConversationUpdateSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        data = conversation_update(conversation_id, serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query_data = request.data
        query_data['user_id'] = request.user.id
        serial = ConversationCreateSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        conversation_id = conversation_create(serial.validated_data)
        return my_json_response({'conversation_id': conversation_id})

    @staticmethod
    def delete(request, conversation_id, *args, **kwargs):
        validated_data = {'user_id': request.user.id, 'del_flag': True}
        data = conversation_update(conversation_id, validated_data)
        return my_json_response({'id': data['id']})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
# @permission_classes([AllowAny])
class Chat(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        query_data = request.data
        query_data['user_id'] = request.user.id
        serial = ChatQuerySerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        data = chat_query(serial.validated_data)
        return streaming_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
# @permission_classes([AllowAny])
class QuestionAnswer(APIView):

    @staticmethod
    def put(request, question_id, is_like, *args, **kwargs):
        query_data = {
            'user_id': request.user.id,
            'question_id': question_id,
            'is_like': int(is_like),
        }
        serial = QuestionAnswerSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        serial.save(serial.validated_data)
        return my_json_response({'id': question_id, 'is_like': is_like})
