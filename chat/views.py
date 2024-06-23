import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes, renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.models import Bot
from chat.models import Conversation, ConversationShare
from chat.serializers import ConversationCreateSerializer, ConversationUpdateSerializer, ChatQuerySerializer, \
    QuestionAnswerSerializer, ConversationsMenuQuerySerializer, QuestionUpdateAnswerQuerySerializer, \
    QuestionListQuerySerializer, ConversationShareListQuerySerializer, ConversationShareCreateQuerySerializer, \
    ConversationShareDetailSerializer
from chat.service import chat_query, conversation_create, conversation_detail, conversation_list, conversation_update, \
    conversation_menu_list, question_list, conversation_share_create, conversation_create_by_share
from core.utils.views import extract_json, my_json_response, streaming_response, ServerSentEventRenderer

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'chat index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
class Conversations(APIView):
    @staticmethod
    def get(request, conversation_id=None, *args, **kwargs):
        logger.debug(f"conversation_id: {conversation_id}")
        conversation = Conversation.objects.filter(id=conversation_id).first()
        if conversation_id and conversation_id != 'menu':
            if not conversation:
                return my_json_response({}, code=100002, msg='conversation not found')
            elif conversation.user_id != request.user.id:
                return my_json_response({}, code=100003, msg='access denied for this conversation')
            data = conversation_detail(conversation_id)
        else:
            query = kwargs['request_data']['GET']
            query_data = {
                'user_id': request.user.id,
                'type': query.get('type', 'list'),
                'page_size': int(query.get('page_size', 10)),
                'page_num': int(query.get('page_num', 1)),
            }
            data = conversation_list(validated_data=query_data)
        return my_json_response(data)

    @staticmethod
    def put(request, conversation_id, *args, **kwargs):
        query_data = request.data
        conversation = Conversation.objects.filter(id=conversation_id, user_id=request.user.id).first()
        if not conversation:
            return my_json_response({}, code=100002, msg='conversation not found')
        serial = ConversationUpdateSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        data = conversation_update(request.user.id, conversation_id, serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query_data = request.data
        conversation_share = None
        if query_data.get('share_id'):
            conversation_share = ConversationShare.objects.filter(id=query_data['share_id'], del_flag=False).first()
            if not conversation_share:
                return my_json_response({}, code=100002, msg='conversation share not found')
            query_data['bot_id'] = conversation_share.bot_id
            query_data['collections'] = conversation_share.collections
            if conversation_share.documents:
                query_data['documents'] = conversation_share.documents
            if not query_data.get('model'):
                query_data['model'] = conversation_share.model
        serial = ConversationCreateSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        validated_data = serial.validated_data
        bot_be_deleted = False
        if validated_data.get('bot_id'):
            bot = Bot.objects.filter(id=validated_data.get('bot_id')).first()
            if bot and bot.del_flag:
                # return my_json_response({}, code=120003, msg='专题被删除，无法创建对话')
                bot_be_deleted = True
            if not bot:
                return my_json_response({}, code=100002, msg='bot not found')
        if query_data.get('share_id'):
            if bot_be_deleted:
                validated_data['bot_id'] = None
                validated_data['collections'] = []
                validated_data['doc_ids'] = []
                validated_data['all_document_ids'] = []
            conversation = conversation_create_by_share(request.user.id, conversation_share, validated_data)
        else:
            conversation = conversation_create(request.user.id, validated_data)
        data = {
            'conversation_id': conversation.id,
            'title': conversation.title,
        }
        return my_json_response(data)

    @staticmethod
    def delete(request, conversation_id, *args, **kwargs):
        validated_data = {'del_flag': True}
        data = conversation_update(request.user.id, conversation_id, validated_data)
        return my_json_response({'id': data['id']})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class ConversationsMenu(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params
        serial = ConversationsMenuQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = conversation_menu_list(request.user.id, vd['list_type'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class Questions(APIView):
    @staticmethod
    def get(request, conversation_id, *args, **kwargs):
        query = request.query_params
        serial = QuestionListQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        conversation = Conversation.objects.filter(id=conversation_id, user_id=request.user.id).first()
        if not conversation:
            return my_json_response({}, code=100002, msg='conversation not found')
        vd = serial.validated_data
        data = question_list(conversation_id, vd['page_num'], vd['page_size'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST', 'OPTIONS']), name='dispatch')
@renderer_classes([ServerSentEventRenderer])
class Chat(APIView):
    @staticmethod
    def post(request, *args, **kwargs):
        query_data = request.data
        serial = ChatQuerySerializer(data=query_data)
        if not serial.is_valid():
            out_str = json.dumps({
                'event': 'on_error', 'error_code': 100001,
                'error': f'validate error, {list(serial.errors.keys())}', 'detail': serial.errors}) + '\n'
            logger.error(f'error msg: {out_str}')
            return streaming_response(iter(out_str))
        validated_data = serial.validated_data
        if (
            validated_data.get('bot_id')
            and not Bot.objects.filter(id=validated_data['bot_id'], del_flag=False).exists()
        ):
            out_str = json.dumps({
                'event': 'on_error', 'error_code': 100002, 'error': 'bot not found', 'detail': {}}) + '\n'
            logger.error(f'error msg: {out_str}')
            return streaming_response(iter(out_str))
        data = chat_query(request.user.id, validated_data)
        return streaming_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
class QuestionLikeAnswer(APIView):

    @staticmethod
    def put(request, question_id, is_like, *args, **kwargs):
        query_data = {
            'user_id': request.user.id,
            'question_id': question_id,
            'is_like': int(is_like),
        }
        serial = QuestionAnswerSerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        serial.save(serial.validated_data)
        return my_json_response({'id': question_id, 'is_like': is_like})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
class QuestionUpdateAnswer(APIView):

    @staticmethod
    def put(request, *args, **kwargs):
        query = request.data
        query['user_id'] = request.user.id
        serial = QuestionUpdateAnswerQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        validated_data = serial.validated_data
        serial.update_answer(validated_data)
        data = {'answer': validated_data['answer']}
        if validated_data.get('question_id'):
            data['question_id'] = validated_data['question_id']
        if validated_data.get('conversation_id'):
            data['conversation_id'] = validated_data['conversation_id']
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class ConversationShares(APIView):
    @staticmethod
    def get(request, share_id, *args, **kwargs):
        share = ConversationShare.objects.filter(id=share_id).first()
        if not share:
            return my_json_response({}, code=100002, msg='conversation share not found')
        return my_json_response(ConversationShareDetailSerializer(share).data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = ConversationShareCreateQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        conversation = Conversation.objects.filter(id=vd['conversation_id'], user_id=request.user.id).first()
        if not conversation:
            return my_json_response({}, code=100002, msg='conversation not found')
        data = conversation_share_create(request.user.id, vd, conversation)
        return my_json_response(data)
