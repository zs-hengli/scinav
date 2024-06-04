import json
import logging

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse, OpenApiSchemaBase
from rest_framework.decorators import throttle_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.models import Bot
from bot.service import bot_list_all, bot_list_mine
from chat.service import chat_query
from core.utils.throttling import UserRateThrottle
from core.utils.views import extract_json, streaming_response, openapi_response, \
    openapi_exception_response
from document.service import get_document_library_list
from document.tasks import async_add_user_operation_log
from openapi.base_service import record_openapi_log
from openapi.models import OpenapiLog
from openapi.serializers_openapi import ChatResponseSerializer, UploadFileResponseSerializer, \
    TopicListRequestSerializer, PersonalLibraryRequestSerializer, SearchDocumentResultSerializer, ChatQuerySerializer, \
    DocumentLibraryPersonalSerializer, CollectionListRequestSerializer, CollectionListSerializer
from openapi.serializers_openapi import SearchQuerySerializer, ExceptionResponseSerializer, TopicListSerializer
from openapi.service import upload_paper, get_request_openapi_key_id
from openapi.service_openapi import search, collection_list_mine

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
        return openapi_response(None)
        # return openapi_exception_response(100000, '系统内部错误 请联系管理员')


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class Search(APIView):
    """
    1. Search
    """
    @staticmethod
    @extend_schema(
        operation_id='Search Papers',
        description='Search papers by content. ',
        tags=['Papers'],
        parameters=[SearchQuerySerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(SearchDocumentResultSerializer(many=True)),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    "$OPENAPI_BASE_URL/openapi/v1/papers/search?content=LLM&limit=100" \\
    --header 'X-API-KEY: ••••••'
\n'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests

headers = {
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/papers/search?content=LLM&limit=100"

response = requests.get(url, headers=headers)

print(response.text)
\n'''},
        ]},
    )
    def get(request, *args, **kwargs):
        # openapi_key_id = get_request_openapi_key_id(request)
        user_id = request.user.id
        query = request.query_params.dict()
        serial = SearchQuerySerializer(data=query)
        if not serial.is_valid():
            error_msg = f'validate error, {list(serial.errors.keys())}'
            return openapi_exception_response(100001, error_msg)
        vd = serial.validated_data
        data = search(user_id, vd['content'], vd['limit'])
        async_add_user_operation_log.apply_async(kwargs={
            'user_id': user_id,
            'operation_type': 'search',
            'operation_content': vd['content'],
            'source': 'api'
        })
        # record_openapi_log(user_id, openapi_key_id, OpenapiLog.Api.SEARCH, OpenapiLog.Status.SUCCESS)
        return openapi_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class PersonalLibrary(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List Personal Library',
        description='List personal library, ordered by updated_at desc.',
        tags=['PersonalLibrary'],
        parameters=[PersonalLibraryRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(DocumentLibraryPersonalSerializer(many=True),),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    "$OPENAPI_BASE_URL/openapi/v1/personal/library?status=completed&limit=100" \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests
            
headers = {
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/personal/library?status=completed&limit=100"

response = requests.get(url, headers=headers)

print(response.text)
\n'''
             }
        ]},
    )
    def get(request, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        query = request.query_params.dict()
        serial = PersonalLibraryRequestSerializer(data=query)
        if not serial.is_valid():
            error_msg = f'validate error, {list(serial.errors.keys())}'
            return openapi_exception_response(100001, error_msg)
        vd = serial.validated_data
        data = get_document_library_list(request.user.id, vd['status'], vd['limit'])
        ret_data = []
        if data and data['list']:
            for item in data['list']:
                ret_data.append({
                    'id': item['id'],
                    'filename': item['filename'],
                    'paper_title': item['document_title'],
                    'paper_id': item['document_id'],
                    'pages': item['pages'],
                    'status': item['status'],
                    'reference_type': item['reference_type'],
                    'record_time': item['record_time'],
                    'type': item['type'],
                })
        return openapi_response(ret_data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
@throttle_classes([UserRateThrottle])
class UploadPaper(APIView):
    @staticmethod
    @extend_schema(
        operation_id='Upload Paper Pdf',
        description='Upload paper pdf to personal library.',
        tags=['Papers'],
        parameters=[
            OpenApiParameter(
                name='filename',
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.STR,
                description='The filename of the paper pdf file.',
            ),
        ],
        request={
            'application/octet-stream': {
                'format': 'binary',
                'description': 'paper pdf file binary',
            }
        },
        responses={
            (200, 'application/json'): OpenApiResponse(UploadFileResponseSerializer),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL', 'source': '''curl --request PUT \\
    -T '<path>/xxx.pdf' \\
    "$OPENAPI_BASE_URL/openapi/v1/papers/upload/xxx.pdf" \\
    --header 'Content-Type: application/octet-stream' \\
    --header 'X-API-KEY: ••••••'\n
'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests

headers = {
  'Content-Type': 'application/octet-stream',
  'X-API-KEY': '••••••'
}
file_path = '<path>/xxx.pdf'
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/papers/upload/xxx.pdf"
with open(file_path, "rb") as file:
    response = requests.put(url, headers=headers, data=file)

print(response.text)
\n'''}
        ]},
    )
    def put(request, filename, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        user_id = request.user.id
        file: InMemoryUploadedFile = request.data.get('file')
        if not file.name.endswith('.pdf'):
            error_msg = 'filename is invalid, must end with .pdf'
            return openapi_exception_response(100001, error_msg)

        if not file:
            error_msg = 'file not found'
            return openapi_exception_response(100001, error_msg)
        # logger.debug(f'ddddddddd file: {file.name}, {file.file}')
        code, msg, data = upload_paper(user_id, file)

        record_openapi_log(
            user_id, openapi_key_id, OpenapiLog.Api.UPLOAD_PAPER, OpenapiLog.Status.SUCCESS, obj_id1=data['task_id']
        )
        if code != 0:
            return openapi_exception_response(code, msg)
        return openapi_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class TopicPlaza(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List Topic Plaza',
        description='List topic plaza.',
        tags=['Topics'],
        parameters=[TopicListRequestSerializer],
        # request={''},
        responses={
            (200, 'application/json'): OpenApiResponse(TopicListSerializer(many=True),),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    "$OPENAPI_BASE_URL/openapi/v1/topics/plaza?limit=100" \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests
            
headers = {
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/topics/plaza?limit=100"

response = requests.get(url, headers=headers)

print(response.text)
\n'''}
        ]},
    )
    def get(request, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        query = request.query_params.dict()
        serial = TopicListRequestSerializer(data=query)
        if not serial.is_valid():
            error_msg = f'validate error, {list(serial.errors.keys())}'
            return openapi_exception_response(100001, error_msg)
        vd = serial.validated_data
        data = bot_list_all(request.user.id, vd['limit'])
        return openapi_response(data['list'])


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class MineTopics(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List My Topics',
        description='List my topics.',
        tags=['Topics'],
        parameters=[TopicListRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(TopicListSerializer(many=True),),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    "$OPENAPI_BASE_URL/openapi/v1/topics/mine?limit=100" \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests
            
headers = {
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/topics/mine?limit=100"

response = requests.get(url, headers=headers)

print(response.text)
\n'''}
        ]},
    )
    def get(request, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        query = request.query_params.dict()
        serial = TopicListRequestSerializer(data=query)
        if not serial.is_valid():
            error_msg = f'validate error, {list(serial.errors.keys())}'
            return openapi_exception_response(100001, error_msg)
        vd = serial.validated_data
        data = bot_list_mine(request.user.id, vd['limit'])
        return openapi_response(data['list'])


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class MineCollection(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List My Collections',
        description='List my collections.',
        tags=['Collections'],
        parameters=[CollectionListRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(CollectionListSerializer(many=True), ),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    "$OPENAPI_BASE_URL/openapi/v1/collections/mine?limit=100" \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests

headers = {
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/collections/mine?limit=100"

response = requests.get(url, headers=headers)

print(response.text)
\n'''}
        ]},
    )
    def get(request, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        query = request.query_params.dict()
        serial = CollectionListRequestSerializer(data=query)
        if not serial.is_valid():
            error_msg = f'validate error, {list(serial.errors.keys())}'
            return openapi_exception_response(100001, error_msg)
        vd = serial.validated_data
        data = collection_list_mine(request.user.id, vd['limit'])
        return openapi_response(data)


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
        description='Conversation by Large Language Model with topic, collections or papers.\n'
                    'In the same conversation, multiple rounds of dialogue are possible, and subsequent questions can '
                    'build upon the previous answers.',
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
                        value='''{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": "It", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " appears there are no specific papers listed in the", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " current knowledge base. Could you", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " please provide more context or specify the topic or", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " field of research you are interested", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " in?", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " This will help me identify the relevant paper", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": " for you.", "statistics": null, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "75288f21-4310-4584-b3d6-7e78cc40e7dc", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-4o", "input_tokens": 352, "output_tokens": 44}, "metadata": {"session_id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "user_id": "6618f9172e18b95b4e73b496"}}
{"event": "conversation", "name": null, "run_id": null, "id": "da421b51-928f-4b50-85d3-3a5c37a1cef7", "question_id": "224e41e8-0260-4eb5-b066-8ad1506dce76"}
''',
                    ),
                ],
            ),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL', 'source': '''curl --request POST \\
    "$OPENAPI_BASE_URL/openapi/v1/chat" \\
    --header 'Content-Type: application/json' \\
    --header 'X-API-KEY: ••••••' \\
    --data '{
        "content": "what is LLM",
        "conversation_id": "d02df0c9-9df2-4d3b-9c32-2cc3ab27f726",
        "topic_id": "367a4c84-8738-444b-856d-90e6196c6fe6"
    }' 
\n'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import os
import requests
import json

payload = json.dumps({
  "content": "what is LLM",
  "conversation_id": "d02df0c9-9df2-4d3b-9c32-2cc3ab27f726",
  "topic_id": "367a4c84-8738-444b-856d-90e6196c6fe6"
})
headers = {
  'Content-Type': 'application/json',
  'X-API-KEY': '••••••'
}
openapi_base_url = os.environ.get('OPENAPI_BASE_URL', 'openapi-base-url')
url = f"{openapi_base_url}/openapi/v1/chat"

response = requests.post(url, headers=headers, data=payload, stream=True)
for line in response.iter_lines():
    print(line)
\n'''}
        ]},
    )
    def post(request, *args, **kwargs):
        openapi_key_id = get_request_openapi_key_id(request)
        user_id = request.user.id
        query = request.data
        serial = ChatQuerySerializer(data=query)
        if not serial.is_valid():
            out_str = json.dumps({
                'event': 'on_error', 'error_code': 100001,
                'error': f'validate error, {list(serial.errors.keys())}', 'detail': serial.errors}) + '\n'
            logger.error(f'error msg: {out_str}')
            return streaming_response(iter(out_str))
        vd = serial.validated_data
        if vd.get('topic_id'): vd['bot_id'] = vd['topic_id']
        if vd.get('paper_knowledge') and vd['paper_knowledge'].get('collection_ids'):
            vd['collections'] = vd['paper_knowledge']['collection_ids']
        if vd.get('paper_knowledge') and vd['paper_knowledge'].get('paper_ids'):
            vd['documents'] = vd['paper_knowledge']['paper_ids']

        if vd.get('topic_id') and not Bot.objects.filter(id=vd['topic_id'], del_flag=False).exists():
            out_str = json.dumps({
                'event': 'on_error', 'error_code': 100002, 'error': 'topic not found', 'detail': {}}) + '\n'
            logger.error(f'error msg: {out_str}')
            return streaming_response(iter(out_str))

        data = chat_query(user_id, vd, openapi_key_id)
        return streaming_response(data)
