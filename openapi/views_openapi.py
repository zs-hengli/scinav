import json
import logging

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse, OpenApiSchemaBase
from rest_framework.decorators import throttle_classes, permission_classes
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.models import Bot
from bot.service import bot_list_all, bot_list_my
from chat.serializers import ChatQuerySerializer
from chat.service import chat_query
from core.utils.throttling import UserRateThrottle
from core.utils.views import extract_json, my_json_response, streaming_response
from document.serializers import SearchQuerySerializer
from document.service import search, presigned_url, get_document_library_list
from document.tasks import async_add_user_operation_log
from openapi.serializers_openapi import ChatResponseSerializer, UploadFileResponseSerializer, \
    SearchResponseSerializer, TopicPlazaRequestSerializer, TopicPlazaResponseSerializer, \
    PersonalLibraryRequestSerializer, PersonalLibraryResponseSerializer
from openapi.service import upload_paper

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
@throttle_classes([UserRateThrottle])
class Index(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='content',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='search content',
                examples=[
                    OpenApiExample(
                        'example',
                        value='test',
                    ),
                ],
            ),
            OpenApiParameter(
                name='page_size',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='page size',
                examples=[
                    OpenApiExample(
                        'example',
                        value=10,
                    ),
                ],
            ),
        ],
    )
    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        logger.debug(f"dddddddd request.token: {request.headers}")
        data = {'desc': 'openapi index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
@throttle_classes([UserRateThrottle])
class Search(APIView):
    """
    1. Search
    """
    @staticmethod
    @extend_schema(
        operation_id='Search_Papers',
        description='search papers',
        tags=['Papers'],
        request={'application/json':SearchQuerySerializer},
        responses={200: SearchResponseSerializer},
    )
    def post(request, *args, **kwargs):
        user_id = request.user.id
        query = request.data
        serial = SearchQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(
                code=100001, msg=f'validate error, {list(serial.errors.keys())}', data=serial.errors)
        post_data = serial.validated_data
        data = search(
            user_id, post_data['content'], post_data['page_size'], post_data['page_num'], topn=post_data['topn']
        )
        async_add_user_operation_log.apply_async(kwargs={
            'user_id': user_id,
            'operation_type': 'search',
            'operation_content': post_data['content'],
            'source': 'api'
        })
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
@throttle_classes([UserRateThrottle])
class Chat(APIView):
    """
    Conversation 不会出现在ui
    """
    @staticmethod
    @extend_schema(
        operation_id='Chat',
        description='Chat',
        tags=['Chat'],
        request={'application/json':ChatQuerySerializer},
        responses={
            (200, 'application/json'): OpenApiResponse(
                ChatResponseSerializer,
                description='This endpoint streams the response of a conversation query, '
                            'allowing for real-time data processing and interaction. '
                            'The stream is formatted according to the Server-Sent Events (SSE) protocol, '
                            'enabling efficient client-side handling of the data stream.',
            ),
            (200, 'text/event-stream'): OpenApiResponse(
                OpenApiSchemaBase,
                examples=[
                    OpenApiExample(
                        'example',
                        value='''{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "4ee477d8-73b4-4a31-aeb5-5f3f0c889965", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-3.5-turbo", "input_tokens": 218, "output_tokens": 29}, "metadata": {"session_id": "303bcea7-14eb-4595-a92d-e079c2e4c150", "user_id": "661cb956617361c9dbec4824"}}
{"event": "tool_start", "name": "chat_tool", "run_id": "0f3b43c4-4cee-4581-9108-8942b7b39f98", "input": {"query": "Key points of the paper 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit'"}, "output": null, "chunk": null, "statistics": null, "metadata": {"session_id": "303bcea7-14eb-4595-a92d-e079c2e4c150", "user_id": "661cb956617361c9dbec4824"}}
{"event": "tool_end", "name": "chat_tool", "run_id": "0f3b43c4-4cee-4581-9108-8942b7b39f98", "input": {"query": "Key points of the paper 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit'"}, "output": "[{'citation_id': 1, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'Using (2.7), we have', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(15, (72.00050354003906, 366.73040771484375, 161.1505584716797, 376.69305419921875))]}, {'citation_id': 2, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'From this we obtain', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(14, (72.00106811523438, 623.7703247070312, 159.97622680664062, 633.7329711914062))]}, {'citation_id': 3, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'Using (5.19), (5.20) and (5.23), we have', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(16, (71.99996948242188, 71.29052734375, 245.88819885253906, 81.25316619873047))]}, {'citation_id': 4, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'We make the following ansatz', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(9, (72.00053405761719, 574.09033203125, 202.1900177001953, 584.052978515625))]}, {'citation_id': 5, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'Using (5.11), we obtain', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(15, (72.00119018554688, 584.890380859375, 174.13916015625, 594.85302734375))]}, {'citation_id': 6, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'a simple calculation leads to', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(2, (71.99996948242188, 447.85040283203125, 195.54391479492188, 457.81304931640625))]}, {'citation_id': 7, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'The second part of the right hand side reads', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(5, (71.99996948242188, 71.29052734375, 266.6369934082031, 81.25316619873047))]}, {'citation_id': 8, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'where h is the molecular field', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(9, (72.00006103515625, 145.23208618164062, 201.37013244628906, 157.3330535888672))]}, {'citation_id': 9, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': '5. The small Deborah number limit. Our aim is to derive the Ericksen-\\nLeslie equation from the microscopic molecular theory represented by (2.7) and (2.8).', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(9, (72.00053405761719, 349.71209716796875, 441.20941162109375, 373.8130798339844))]}, {'citation_id': 10, 'collection_type': 's2', 'collection_id': 's2', 'doc_id': 4598629, 'title': 'A Molecular Kinetic Theory of Inhomogeneous Liquid Crystal Flow and the Small Deborah Number Limit', 'authors': ['E. Weinan', ' Pingwen Zhang'], 'content': 'where h is the molecular field,', 'content_type': 'Text-Fragment', 'section': '', 'bbox': [(11, (71.99996948242188, 69.1521987915039, 204.1248321533203, 81.25316619873047))]}]", "chunk": null, "statistics": null, "metadata": {"session_id": "303bcea7-14eb-4595-a92d-e079c2e4c150", "user_id": "661cb956617361c9dbec4824"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "0a11b2fc-95b4-4878-9df9-42980c31521b", "input": null, "output": null, "chunk": "1. Derivation of the Ericksen-Leslie equation from microscopic molecular theory. 2. Utilization of various equations (e.g., (2.7), (5.19), (5.20), (5.23), (5.11)) in the analysis.", "statistics": null, "metadata": {"session_id": "303bcea7-14eb-4595-a92d-e079c2e4c150", "user_id": "661cb956617361c9dbec4824"}}
{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "0a11b2fc-95b4-4878-9df9-42980c31521b", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-3.5-turbo", "input_tokens": 1049, "output_tokens": 101}, "metadata": {"session_id": "303bcea7-14eb-4595-a92d-e079c2e4c150", "user_id": "661cb956617361c9dbec4824"}}
''',
                    ),
                ],
            )
        }
    )
    def post(request, *args, **kwargs):
        user_id = request.user.id
        query = request.data
        serial = ChatQuerySerializer(data=query)
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
        data = chat_query(user_id, validated_data)
        return streaming_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
@throttle_classes([UserRateThrottle])
class UploadPaper(APIView):
    @staticmethod
    @extend_schema(
        operation_id='Upload_Paper',
        description='Upload paper to personal library.',
        tags=['Papers'],
        request={
            'application/octet-stream': {
                'format': 'binary',
                'description': 'paper file binary',
            }
        },
        responses={
            (200, 'application/json'): UploadFileResponseSerializer
        },
    )
    def put(request, filename, *args, **kwargs):
        user_id = request.user.id
        file: InMemoryUploadedFile = request.data.get('file')
        if not file:
            return my_json_response(code=100001, msg='file not found')
        # logger.debug(f'ddddddddd file: {file.name}, {file.file}')
        code, msg, data = upload_paper(user_id, file)
        return my_json_response(data, code, msg)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class TopicPlaza(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List_Topic_Plaza',
        description='List Topic Plaza',
        tags=['Topics'],
        parameters=[TopicPlazaRequestSerializer],
        # request={''},
        responses={
            (200, 'application/json'): OpenApiResponse(TopicPlazaResponseSerializer,)
        }
    )
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = TopicPlazaRequestSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = bot_list_all(request.user.id, vd['page_size'], vd['page_num'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class MyTopics(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List_My_Topics',
        description='List My Topics',
        tags=['Topics'],
        parameters=[TopicPlazaRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(TopicPlazaResponseSerializer,)
        }
    )
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = TopicPlazaRequestSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = bot_list_my(request.user.id, vd['page_size'], vd['page_num'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class PersonalLibrary(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List_Personal_Library',
        description='List Personal Library',
        tags=['PersonalLibrary'],
        parameters=[PersonalLibraryRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(PersonalLibraryResponseSerializer,)
        }
    )
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = PersonalLibraryRequestSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = get_document_library_list(request.user.id, vd['list_type'], vd['page_size'], vd['page_num'])
        return my_json_response(data)
