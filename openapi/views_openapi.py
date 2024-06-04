import json
import logging
import os

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

OPENAPI_BASE_URL = os.environ.get('OPENAPI_BASE_URL', '$OPENAPI_BASE_URL')


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
             'source': f'''curl -X GET \\
    "{OPENAPI_BASE_URL}/openapi/v1/papers/search?content=LLM&limit=100" \\
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
             'source': f'''curl -X GET \\
    "{OPENAPI_BASE_URL}/openapi/v1/personal/library?status=completed&limit=100" \\
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
            {'lang': 'curl', 'label': 'cURL', 'source': f'''curl --request PUT \\
    -T '<path>/xxx.pdf' \\
    "{OPENAPI_BASE_URL}/openapi/v1/papers/upload/xxx.pdf" \\
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
             'source': f'''curl -X GET \\
    "{OPENAPI_BASE_URL}/openapi/v1/topics/plaza?limit=100" \\
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
             'source': f'''curl -X GET \\
    "{OPENAPI_BASE_URL}/openapi/v1/topics/mine?limit=100" \\
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
             'source': f'''curl -X GET \\
    "{OPENAPI_BASE_URL}/openapi/v1/collections/mine?limit=100" \\
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
                        value='''{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "393cf8ca-a971-4013-8998-e44b1117c2cf", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-4o", "input_tokens": 3045, "output_tokens": 31}, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "tool_start", "name": "paper_content_search", "run_id": "266b1fa5-41a9-4eb3-9bdd-bf365b7abe5f", "input": {"queries": ["\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408"]}, "output": null, "chunk": null, "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "tool_end", "name": "paper_content_search", "run_id": "266b1fa5-41a9-4eb3-9bdd-bf365b7abe5f", "input": {"queries": ["\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408"]}, "output": [{"citation_id": 1, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 0, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u6aad \u6aad \u6aad\u6aad \u6aad \u6aad \u6aad \u6aad \u6aad \u6aad\u6aad \u6b90 \u6aad \u6aad \u6aad", "content_type": "Figure", "section": "", "bbox": [[0, [13.0, 59.599998474121094, 97.0999984741211, 99.5]]]}, {"citation_id": 2, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": null, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "", "content_type": "Abstract", "section": "Abstract", "bbox": null}, {"citation_id": 3, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 2, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u6458\u8981:\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u6280\u672f,\u4ee5\u5176\u65e0\u6c61\u67d3\u3001\u4f4e\u6d88\u8017\u3001\u8fd0\u884c\u5e73\u7a33\u3001\u7528\u80fd\u6a21\u5f0f\u591a\u7b49\u4f18\u70b9\u5728\u8282\u80fd\u548c\u73af\u4fdd\u9886\u57df\u8d8a\u6765 \u8d8a\u53d7\u5230\u4eba\u4eec\u7684\u91cd\u89c6\u3002\u4f46\u76f8\u5bf9\u4e8e\u538b\u7f29\u5f0f\u5236\u51b7,\u5176\u6548\u7387\u8f83\u4f4e\u7684\u7f3a\u70b9\u9650\u5236\u4e86\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u6280\u672f\u7684\u5e7f\u6cdb\u5e94\u7528\u3002\u57fa\u4e8e \u6eb4\u5316\u9502\u6c34\u6eb6\u6db2\u6c14\u6db2\u7279\u6027\u4e2d\u6c7d\u6db2\u76f8\u5e73\u8861\u548c\u6eb6\u6db2\u6df7\u5408\u4e0e\u5206\u79bb\u7684\u539f\u7406,\u901a\u8fc7\u8c03\u8282\u673a\u7ec4\u5faa\u73af\u8fc7\u7a0b\u4e2d\u5185\u90e8\u548c\u5916\u90e8\u7684\u53c2\u6570, \u5b9e\u9a8c\u5206\u6790\u5bf9\u5236\u51b7\u673a\u7ec4\u5236\u51b7\u7279\u6027\u7684\u8026\u5408\u5f71\u54cd\u3002\u5b9e\u9a8c\u7ed3\u679c\u8868\u660e:\u84b8\u53d1\u6e29\u5ea6\u3001\u5145\u6ce8\u6d53\u5ea6\u548c\u5438\u6536\u538b\u529b\u7684\u63d0\u9ad8\u5747\u80fd\u63d0\u9ad8\u5236 \u51b7\u91cf\u548cCOP\u503c,\u4e14\u5438\u6536\u538b\u529b\u7684\u63d0\u9ad8\u6548\u679c\u6700\u663e\u8457,\u5176\u589e\u5e45\u8303\u56f4\u6700\u9ad8\u53ef\u4ee5\u8d85\u8fc7100%,\u800c\u51b7\u5374\u6c34\u6e29\u5ea6\u7684\u63d0\u9ad8\u964d\u4f4e\u4e86 \u5236\u51b7\u91cfCOP\u503c\u3002\u56e0\u6b64,\u9002\u5f53\u7684\u8026\u5408\u8c03\u8282\u673a\u7ec4\u5faa\u73af\u7684\u70ed\u7269\u7406\u53c2\u6570\u53ef\u4ee5\u660e\u663e\u63d0\u9ad8\u5236\u51b7\u6027\u80fd\u3002 \u5173\u952e\u8bcd:\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7;\u7269\u7406\u53c2\u6570;\u8026\u5408;\u5236\u51b7\u91cf;COP\n\u7287\u7297\u7290:10.3969/j.issn.04381157.2012.z2.001 \u4e2d\u56fe\u5206\u7c7b\u53f7:TU831 \u6587\u732e\u6807\u5fd7\u7801:A \u6587\u7ae0\u7f16\u53f7:0438-1157(2012)S2-001-07", "content_type": "Text-Fragment", "section": "", "bbox": [[0, [30.0, 167.0, 483.0, 293.20001220703125]]]}, {"citation_id": 4, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 22, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "4\u7ed3\u8bba \u901a\u8fc7\u8bd5\u9a8c\u7814\u7a76,\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u5faa\u73af\u5185\u90e8\u5916 \u90e8\u70ed\u7269\u7406\u53c2\u6570\u7684\u8026\u5408\u53d8\u5316\u5bf9\u5236\u51b7\u6027\u80fd\u4ea7\u751f\u4e00\u5b9a\u7684\u5f71 \u54cd\u3002\u84b8\u53d1\u6e29\u5ea6\u548c\u5145\u6ce8\u6d53\u5ea6\u4e4b\u95f4\u8026\u5408\u65f6,\u84b8\u53d1\u6e29\u5ea6\u548c \u5145\u6ce8\u6d53\u5ea6\u5347\u9ad8\u5747\u80fd\u63d0\u9ad8\u5236\u51b7\u91cf\u548cCOP\u503c;\u51b7\u5374\u6c34 \u5165\u53e3\u6e29\u5ea6\u548c\u5145\u6ce8\u6d53\u5ea6\u4e4b\u95f4\u8026\u5408\u65f6,\u63d0\u9ad8\u5145\u6ce8\u6d53\u5ea6\u964d \u4f4e\u51b7\u5374\u6c34\u5165\u53e3\u6e29\u5ea6\u53ef\u4ee5\u63d0\u9ad8\u5236\u51b7\u91cf\u548cCOP\u503c;\u5438 \u6536\u538b\u529b\u548c\u5145\u6ce8\u6d53\u5ea6\u4e4b\u95f4\u8026\u5408\u65f6,\u589e\u52a0\u5438\u6536\u538b\u529b\u53ef\u4ee5 \u5927\u5e45\u5ea6\u63d0\u9ad8\u5236\u51b7\u91cf\u548cCOP\u503c,\u9002\u5f53\u5730\u63d0\u9ad8\u5145\u6ce8\u6d53 \u5ea6\u548c\u5438\u6536\u538b\u529b\u53ef\u4ee5\u63d0\u9ad8\u5236\u51b7\u91cf\u548cCOP\u503c;\u5438\u6536\u538b \u529b\u548c\u84b8\u53d1\u6e29\u5ea6\u4e4b\u95f4\u8026\u5408\u65f6,\u9002\u5f53\u5730\u63d0\u9ad8\u5438\u6536\u538b\u529b\u548c \u84b8\u53d1\u6e29\u5ea6\u53ef\u4ee5\u63d0\u9ad8\u5236\u51b7\u91cf\u548cCOP\u503c\u3002", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[5, [258.20001220703125, 439.70001220703125, 502.0, 646.9000244140625]]]}, {"citation_id": 5, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 23, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u729a\u72b2\u72b3\u72b2\u72c9\u72b2\u72c0\u72ae\u72b2\u72ca\n[1]PengOizhen(\u5f6d\u9f50\u73cd),FangGuoyuan(\u65b9\u56fd\u8fdc),Yu Shumei(\u4e8e\u6dd1\u6885).Necessitytodevelopcombinedcycleplant andcountermeasuresforfurtherdevelopment[J].\u7298\u72c5\u72d1\u72b2\u72c9 \u729b\u72d4\u72ca\u72cb\u72b2\u72bf\u7288\u72c0\u72b5\u72bb\u72c0\u72b2\u72b2\u72c9\u72bb\u72c0\u72b5(\u7535\u7ad9\u7cfb\u7edf\u5de5\u7a0b),2004,20(3):46", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[5, [260.3999938964844, 650.2000122070312, 502.20001220703125, 724.9000244140625]]]}, {"citation_id": 6, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 1, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "# \u6b90 \u6b90 \u6b90 \u7814\u7a76\u8bba\u6587 \u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e \u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408 \u738b\u521a,\u89e3\u56fd\u73cd,\u738b\u4eae\u4eae (\u5317\u4eac\u5efa\u7b51\u5de5\u7a0b\u5b66\u9662,\u5317\u4eac100044)\n", "content_type": "Title", "section": "", "bbox": [[0, [13.199999809265137, 68.30000305175781, 404.6000061035156, 155.39999389648438]]]}, {"citation_id": 7, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 11, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "conducting oil high voltage generator low voltage generator condenser cooling tower high temperature heat exchanger low temperature pump conducting oil heat exchanger evaporator turbocharger cooling water pump refrigerant coolant water absorber water mixed tank refrigerant pump solution pump refrigerant pump refrigerant pump absorber circulation pump\n\u00b74\u00b7 \u5316\u5de5\u5b66\u62a5 \u7b2c63\u5377 storage tank cooling tower absorber m evaporator ixed tank flowmeter flowmeter condenser flowmeter flowmeter", "content_type": "Figure", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[2, [53.79999923706055, 453.5, 441.0, 644.2000122070312]], [3, [15.100000381469727, 15.100000381469727, 491.29998779296875, 194.0]]]}, {"citation_id": 8, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 12, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "3\u8bd5\u9a8c\u7ed3\u679c\u4e0e\u5206\u6790 \u57fa\u4e8e\u6eb4\u5316\u9502\u6c34\u6eb6\u6db2\u7684\u6c14\u6db2\u7279\u6027,\u5229\u7528\u8bbe\u8ba1\u6539\u9020 \u7684\u6eb4\u5316\u9502\u589e\u538b\u5236\u51b7\u673a\u7ec4\u8fdb\u884c\u8bd5\u9a8c\u7814\u7a76,\u63a7\u5236\u4e0d\u540c\u7684 \u5236\u51b7\u5de5\u51b5,\u5206\u6790\u4e0d\u540c\u7684\u70ed\u7269\u7406\u53c2\u6570\u8026\u5408\u540e\u5bf9\u5236\u51b7\u91cf \u548cCOP\u503c\u7684\u5f71\u54cd\u3002 31\u84b8\u53d1\u6e29\u5ea6\u4e0e\u5145\u6ce8\u6d53\u5ea6\u8026\u5408\u5f71\u54cd \u5438\u6536\u5668\u5185\u5145\u6ce8\u8d28\u91cf\u5206\u6570\u5206\u522b\u4e3a50%\u300152%\u3001 54%\u300156%\u548c58%\u7684\u6eb6\u6db2;\u51b7\u5374\u6c34\u8fdb\u51fa\u53e3\u6d41\u91cf\u4fdd \u6301\u4e0d\u53d8,\u51b7\u51dd\u6e29\u5ea6\u4e3a32\u2103,\u51b7\u51dd\u538b\u529b\u4fdd\u6301\u4e0d\u53d8; \u9ad8\u6e29\u70ed\u6e90\u5bfc\u70ed\u6cb9\u8fdb\u53e3\u6e29\u5ea6\u4fdd\u6301140\u2103;\u51b7\u5a92\u6c34\u7684\u6d41 \u91cf\u4fdd\u6301\u4e00\u5b9a,\u5206\u522b\u8c03\u8282\u51b7\u5a92\u6c34\u5165\u53e3\u6e29\u5ea6,\u4f7f\u5f97\u84b8\u53d1 \u6e29\u5ea6\u5206\u522b\u4e3a13\u300115\u300117\u2103,\u5206\u6790\u4e0d\u540c\u5145\u6ce8\u6d53\u5ea6\u548c \u84b8\u53d1\u6e29\u5ea6\u5bf9\u5236\u51b7\u91cf\u548cCOP\u503c\u7684\u8026\u5408\u5f71\u54cd\u3002", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[3, [6.699999809265137, 271.79998779296875, 254.5, 497.0]]]}, {"citation_id": 9, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 18, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u673a\u7ec4\u7684\u5236\u51b7\u91cf\u968f\u7740\u5438\u6536\u538b\u529b\u7684\u589e\u52a0\u800c\u589e\u5927,\u5176\u589e\u5e45 \u572855.8%~115%;\u540c\u6837,COP\u503c\u4e5f\u968f\u5145\u6ce8\u6d53\u5ea6\u5347 \u9ad8\u800c\u589e\u5927,\u5176\u589e\u5e45\u8303\u56f4\u4e3a5.9%~15.9%,\u968f\u5438\u6536 \u538b\u529b\u589e\u52a0\u800c\u589e\u5927,\u5176\u589e\u5e45\u8303\u56f4\u4e3a54.6%~ 113.5%\u3002\u673a\u7ec4COP\u503c\u662f\u673a\u7ec4\u5236\u51b7\u91cf\u4e0e\u8017\u70ed\u91cf\u548c\u8865 \u5145\u7684\u673a\u68b0\u529f\u5171\u540c\u4f5c\u7528\u7684\u7ed3\u679c\u3002\u5f53\u5438\u6536\u5668\u4e2d\u7684\u5438\u6536\u538b \u529b\u589e\u52a0\u65f6,\u6eb6\u6db2\u7684\u5438\u6536\u80fd\u529b\u589e\u5f3a,\u5438\u6536\u70ed\u8d1f\u8377\u589e \u52a0,\u56e0\u6b64,\u673a\u7ec4\u7684\u5236\u51b7\u80fd\u529b\u4e5f\u968f\u7740\u63d0\u9ad8;\u76f8\u540c\u7684\u5438 \u6536\u538b\u529b\u4e0b,\u5145\u6ce8\u6d53\u5ea6\u9ad8\u7684\u6eb6\u6db2\u7684\u5236\u51b7\u91cf\u9ad8\u4e8e\u5145\u6ce8\u6d53 \u5ea6\u4f4e\u7684\u6eb6\u6db2\u7684\u5236\u51b7\u91cf\u503c,\u56e0\u6b64,\u5728\u53d1\u751f\u70ed\u8d1f\u8377\u548c\u673a \u68b0\u529f\u53d8\u5316\u4e0d\u5927\u7684\u60c5\u51b5\u4e0b,\u5438\u6536\u6d53\u5ea6\u9ad8\u7684\u6eb6\u6db2\u7684 COP\u503c\u9ad8\u4e8e\u5438\u6536\u6d53\u5ea6\u4f4e\u7684\u6eb6\u6db2\u7684COP\u503c,\u5728\u538b\u529b 2.5kPa\u4ee5\u540e,\u673a\u68b0\u529f\u589e\u52a0\u8f83\u5927,\u5236\u51b7\u91cf\u7684\u589e\u52a0\u5e45 \u5ea6\u4f4e\u4e8e\u673a\u68b0\u529f\u589e\u52a0\u5e45\u5ea6,\u6240\u4ee5,COP\u503c\u589e\u52a0\u7f13\u6162, \u5f53\u673a\u68b0\u529f\u589e\u52a0\u5e45\u5ea6\u8fdc\u5927\u4e8e\u5236\u51b7\u91cf\u7684\u589e\u52a0\u5e45\u5ea6\u65f6, COP\u503c\u6709\u4e0b\u964d\u8d8b\u52bf\u3002 34\u5438\u6536\u538b\u529b\u4e0e\u84b8\u53d1\u6e29\u5ea6\u8026\u5408\u5f71\u54cd \u9ad8\u538b\u53d1\u751f\u5668\u5185\u7684\u9a71\u52a8\u70ed\u6e90\u7684\u6e29\u5ea6\u4e3a140\u2103,\u5438 \u6536\u5668\u5185\u7684\u5145\u6ce8\u6eb6\u6db2\u7684\u6d53\u5ea6\u4e3a56%;\u51b7\u5374\u6c34\u7684\u6d41\u91cf \u4fdd\u6301\u4e0d\u53d8,\u51b7\u51dd\u6e29\u5ea6\u4e3a32\u2103\u00b11\u2103;\u8c03\u8282\u51b7\u5a92\u6c34\u589e \u538b\u524d\u540e\u6d41\u91cf,\u5206\u522b\u8c03\u8282\u51b7\u5a92\u6c34\u5165\u53e3\u6e29\u5ea6\u548c\u5438\u6536\u538b \u529b,\u4f7f\u84b8\u53d1\u6e29\u5ea6\u5206\u522b\u4e3a13\u300115\u300117\u2103,\u5438\u6536\u538b\u529b \u4ece1.7kPa\u589e\u81f32.7kPa,\u5206\u6790\u84b8\u53d1\u6e29\u5ea6\u548c\u5438\u6536\u538b \u529b\u5bf9\u5236\u51b7\u91cf\u548cCOP\u503c\u7684\u8026\u5408\u5f71\u54cd\u3002", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[5, [7.599999904632568, 41.70000076293945, 254.5, 431.1000061035156]]]}, {"citation_id": 10, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 19, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u7531\u56fe11\u3001\u56fe12\u53ef\u4ee5\u770b\u51fa,\u76f8\u540c\u5438\u6536\u538b\u529b\u4e0b\u84b8 \u53d1\u6e29\u5ea6\u5206\u522b\u4e3a13\u300115\u300117\u2103\u65f6,\u5236\u51b7\u91cf\u968f\u84b8\u53d1\u6e29 \u5ea6\u7684\u5347\u9ad8\u800c\u589e\u52a0,\u5176\u589e\u5e45\u57281.3%~10.8%;\u76f8\u540c \u84b8\u53d1\u6e29\u5ea6\u65f6,\u5438\u6536\u538b\u529b\u75311.7kPa\u589e\u81f32.7kPa, \u673a\u7ec4\u7684\u5236\u51b7\u91cf\u968f\u7740\u5438\u6536\u538b\u529b\u7684\u589e\u52a0\u800c\u589e\u5927,\u5176\u589e\u5e45 \u572857.9%~103.2%;\u540c\u6837COP\u503c\u4e5f\u968f\u84b8\u53d1\u6e29\u5ea6", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[5, [10.199999809265137, 425.5, 254.5, 527.5]]]}, {"citation_id": 11, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 20, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "8000 9000 10000 11000 12000 13000 14000 15000 16000 17000 18000 cooling capacity/W13 15 17 1.5 1.7 1.9 2.1 2.3 2.5 2.7 absorption pressure/kPa \u56fe11\u5236\u51b7\u91cf\u968f\u5438\u6536\u538b\u529b\u7684\u53d8\u5316 Fig.11Coolingcapacityvariedwithabsorptionpressure atdifferentevaporationtemperature\n\u00b76\u00b7 \u5316\u5de5\u5b66\u62a5 \u7b2c63\u5377 0.4 0.5 0.6 0.7 0.8 0.9 COP13 15 17 1.5 1.7 1.9 2.1 2.3 2.5 2.7 absorption pressure/kPa", "content_type": "Figure", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[5, [14.600000381469727, 529.2000122070312, 245.89999389648438, 721.0]], [5, [15.100000381469727, 15.100000381469727, 491.29998779296875, 34.70000076293945]], [5, [271.70001220703125, 62.599998474121094, 470.8999938964844, 201.1999969482422]]]}, {"citation_id": 12, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 10, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "2\u8bd5\u9a8c\u673a\u7ec4\u4ecb\u7ecd \u8bd5\u9a8c\u673a\u7ec4\u5728\u666e\u901a\u53cc\u6548\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u673a\u7ec4 \u7684\u57fa\u7840\u4e0a\u8fdb\u884c\u6539\u9020,\u6210\u4e3a\u5177\u6709\u5438\u6536\u538b\u529b\u53ef\u8c03\u8282\u3001 \u51b7\u5a92\u6c34\u548c\u51b7\u5374\u6c34\u4e2d\u548c\u7b49\u529f\u80fd\u7684\u65b0\u578b\u53cc\u6548\u6eb4\u5316\u9502\u5438 \u6536\u5f0f\u5236\u51b7\u673a\u7ec4,\u5982\u56fe3\u6240\u793a\u3002\u8be5\u8bd5\u9a8c\u673a\u7ec4\u8fd0\u884c\u65f6 \u4e3b\u8981\u7531\u9ad8\u6e29\u70ed\u6e90\u5faa\u73af\u3001\u51b7\u5374\u6c34\u5faa\u73af\u3001\u51b7\u5a92\u6c34\u5faa \u73af\u3001\u6eb6\u6db2\u5faa\u73af\u3001\u5236\u51b7\u5242\u5faa\u73af\u3001\u6df7\u5408\u6c34\u5faa\u73af\u7b49\u5faa\u73af \u8fc7\u7a0b\u7ec4\u6210,\u8bd5\u9a8c\u673a\u7ec4\u53c8\u7531\u82e5\u5e72\u63a7\u5236\u8c03\u8282\u7cfb\u7edf\u7ec4 \u6210:\u5bfc\u70ed\u6cb9\u52a0\u70ed\u7cfb\u7edf\u3001\u7535\u6c14\u63a7\u5236\u7cfb\u7edf\u3001\u53d8\u9891\u7cfb \u7edf\u3001\u538b\u529b\u6d4b\u8bd5\u7cfb\u7edf\u3001\u6e29\u5ea6\u6d4b\u8bd5\u7cfb\u7edf\u3001\u6d41\u91cf\u6d4b\u8bd5\u7cfb \u7edf\u7b49\u3002\u673a\u7ec4\u8fd0\u884c\u65f6\u5404\u4e2a\u73af\u8282\u6eb6\u6db2\u7684\u6e29\u5ea6\u7531\u9ad8\u6e29\u52a0 \u70ed\u70ed\u6e90\u548c\u51b7\u5374\u6c34\u6e29\u5ea6\u6765\u8c03\u8282\u5e76\u7531\u6e29\u5ea6\u4f20\u611f\u5668\u6d4b\u91cf \u5404\u73af\u8282\u6e29\u5ea6,\u5438\u6536\u5668\u5185\u7684\u538b\u529b\u7531\u589e\u8bbe\u5728\u84b8\u53d1\u5668\u548c \u5438\u6536\u5668\u4e4b\u95f4\u7684\u589e\u538b\u5668\u8c03\u8282\u5e76\u7531\u538b\u529b\u53d8\u9001\u5668\u6d4b\u91cf, \u6c34\u8def\u5faa\u73af\u7cfb\u7edf\u548c\u6eb6\u6db2\u5faa\u73af\u7cfb\u7edf\u4e2d\u7684\u6d41\u91cf\u7531\u5faa\u73af\u7ba1 \u9053\u4e0a\u7684\u8c03\u8282\u9600\u63a7\u5236\u5e76\u7531\u6d41\u91cf\u8ba1\u6d4b\u51fa\u3002 \u4e0e\u666e\u901a\u53cc\u6548\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u673a\u7ec4\u76f8\u6bd4\u8f83,\u8be5\u8bd5 \u9a8c\u673a\u7ec4\u4e0d\u4ec5\u5728\u84b8\u53d1\u5668\u4e0e\u5438\u6536\u5668\u4e4b\u95f4\u6709\u589e\u538b\u88c5\u7f6e,\u800c\u4e14 \u8bbe\u8ba1\u5e76\u6539\u9020\u4e86\u51b7\u5a92\u6c34\u548c\u51b7\u5374\u6c34\u7684\u6df7\u5408\u6c34\u7cfb\u7edf,\u5982\u56fe4 \u6240\u793a\u3002\u8bbe\u8ba1\u6df7\u6c34\u7cfb\u7edf\u4e0d\u4ec5\u80fd\u591f\u4f7f\u51b7\u5374\u6c34\u56de\u6c34\u6765\u4e2d \u548c\u51b7\u5a92\u6c34\u56de\u6c34\u4e2d\u7684\u51b7\u91cf,\u800c\u4e14\u80fd\u591f\u4f7f\u51b7\u5374\u5854\u4e2d\u98ce", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[2, [258.20001220703125, 77.5, 505.70001220703125, 423.20001220703125]]]}, {"citation_id": 13, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 3, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5\n(\u7285\u72b2\u72bb\u72bc\u72bb\u72c0\u72b5\u729d\u72c0\u72bb\u72cf\u72b2\u72c9\u72ca\u72bb\u72cb\u72d4\u72c5\u72b3\u7286\u72bb\u72cf\u72bb\u72be\u7288\u72c0\u72b5\u72bb\u72c0\u72b2\u72b2\u72c9\u72bb\u72c0\u72b5\u72aa\u72c0\u72b1\u7283\u72c9\u72ae\u72ba\u72bb\u72cb\u72b2\u72ae\u72cb\u72cc\u72c9\u72b2,\u7285\u72b2\u72bb\u72bc\u72bb\u72c0\u72b5100044,\u7286\u72ba\u72bb\u72c0\u72aa)\n\u7283\u72ab\u72ca\u72cb\u72c9\u72aa\u72ae\u72cb:LiBrabsorptionrefrigerationunitsarepaidmoreattentionintheareasofenergysavingand environmentalprotectionbecauseofitszeropollution,lowenergyconsumption,stableoperationand multifunctionenergymodes,\u72b2\u72cb\u72ae.ButLiBrrefrigerationtechnologyapplicationislimitedbyitslow refrigerationefficiency.ThecoolingpropertyofLiBrrefrigerationunitisanalyzedbyexperiments,which isbasedonthebalanceofliquidphaseandvaporphaseintheliquormixedbyLiBrandH2Oaswellasthe parametersoftherefrigerationunitaremodulatedintherefrigerationcircle.Theexperimentsprovethat evaporationtemperature,theconcentrationoftheLiBrliquorandtheabsorptionpressurecouldimprove thecoolingcapacityandtheCOPoftherefrigerationwhichareimpactedmostlybytheabsorptionpressure andtheabsorptionpressurecouldimprovestheCOPby100%,onthecontrary,theuppertemperatureof thecoolingwateroftheLiBrrefrigerationunit,thelowercoolingcapacityandCOP.Therefore,the propersetupofthermalpropertiesintherefrigerationcirclecouldimprovetherefrigerationcharacter.", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[0, [6.599999904632568, 316.5, 505.70001220703125, 612.0999755859375]]]}, {"citation_id": 14, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 4, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u7293\u72b2\u72d4\u72d1\u72c5\u72c9\u72b1\u72ca:LiBrabsorptionrefrigeration;physicalparameters;coupling;coolingcapacity;COP\n\u5f15\u8a00 20\u4e16\u7eaa70\u5e74\u4ee3\u4ee5\u6765,\u4eba\u7c7b\u6b63\u9762\u4e34\u7740\u53ef\u80fd\u51fa\u73b0 \u7684\u80fd\u6e90\u5371\u673a\u4ee5\u53ca\u65e5\u76ca\u4e25\u91cd\u73af\u5883\u7834\u574f[1]\u3002\u4e16\u754c\u5404\u56fd\u666e \u904d\u5f00\u59cb\u5173\u6ce8\u73af\u5883\u4fdd\u62a4\u3001\u8282\u7ea6\u548c\u9ad8\u6548\u5229\u7528\u80fd\u6e90\u4ee5\u53ca\u5f00 \u53d1\u65b0\u80fd\u6e90\u7b49\u95ee\u9898\u3002\u5728\u8fd9\u79cd\u80cc\u666f\u4e0b,\u8282\u80fd\u548c\u73af\u4fdd\u5df2\u7ecf \u6210\u4e3a21\u4e16\u7eaa\u79d1\u5b66\u6280\u672f\u53d1\u5c55\u7684\u4e24\u5927\u91cd\u8981\u8bae\u9898\u3002\u6eb4\u5316 \u9502\u5438\u6536\u5f0f\u5236\u51b7\u6280\u672f,\u4ee5\u5176\u65e0\u6c61\u67d3\u3001\u4f4e\u6d88\u8017\u3001\u8fd0\u884c\u5e73 \u7a33\u3001\u7528\u80fd\u6a21\u5f0f\u591a\u7b49\u4f18\u70b9\u5728\u8282\u80fd\u548c\u73af\u4fdd\u9886\u57df\u8d8a\u6765\u8d8a\u53d7 \u5230\u4eba\u4eec\u7684\u91cd\u89c6\u3002 \u57fa\u4e8e\u63d0\u9ad8\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u7cfb\u7edf\u6027\u80fd,\u56fd\u5185\u5916 \u5b66\u8005\u4ece\u4e0d\u540c\u7684\u89d2\u5ea6\u4f5c\u4e86\u5927\u91cf\u7814\u7a76\u3002\u6587\u732e[23]\u4e2d \u4e3b\u8981\u5206\u6790\u4e86\u6eb4\u5316\u9502\u5236\u51b7\u673a\u7ec4\u4e2d\u5438\u6536\u5668\u5404\u79cd\u5f62\u5f0f\u53ca\u7279 \u70b9,\u5e76\u5f97\u51fa\u4f20\u70ed\u4f20\u8d28\u5206\u79bb\u9884\u51b7\u5374\u5438\u6536\u5668\u53ef\u4ee5\u5bf9\u4f20\u70ed \u548c\u4f20\u8d28\u8fc7\u7a0b\u5206\u522b\u8fdb\u884c\u5f3a\u5316,\u63d0\u9ad8\u5438\u6536\u5668\u7684\u5de5\u4f5c\u6548 \u7387\u3002\u6587\u732e[4]\u901a\u8fc7\u6539\u53d8\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u673a\u7ec4\u5438 \u6536\u5668\u5185\u6eb6\u6db2\u7684\u521d\u59cb\u6d53\u5ea6\u3001\u55b7\u6dcb\u5bc6\u5ea6\u3001\u51b7\u5374\u6c34\u6e29\u5ea6\u5f97 \u5230\u5b9e\u9a8c\u7ed3\u679c,\u5e76\u5206\u6790\u4e86\u5bf9\u5236\u51b7\u6548\u679c\u7684\u5f71\u54cd\u3002\u6587\u732e\n[5]\u62a5\u9053\u4e86\u5355\u3001\u53cc\u6548\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u673a\u7ec4\u8fd0\u884c\u65f6 \u53d1\u751f\u5668\u3001\u84b8\u53d1\u5668\u548c\u70ed\u4ea4\u6362\u5668\u7684\u80fd\u91cf\u548c!\u53d8\u5316\u3002\u6587\u732e\n[6]\u4e2d\u5206\u6790\u4e86\u5e38\u538b\u4e0b\u6dfb\u52a0\u5728\u6eb4\u5316\u9502\u6eb6\u6db2\u4e2d\u7684\u7eb3\u7c73\u9897 \u7c92\u6709\u6548\u5730\u964d\u4f4e\u4e86\u6eb6\u6db2\u7684\u53d1\u751f\u6e29\u5ea6,\u4f7f\u673a\u7ec4\u80fd\u591f\u8fdb\u4e00 \u6b65\u5229\u7528\u4f4e\u54c1\u4f4d\u70ed\u6e90\u3002Marina\u7b49[7]\u901a\u8fc7\u5b9e\u9a8c\u7814\u7a76\u4e86 \u6eb4\u5316\u9502\u6eb6\u6db2\u548c\u6709\u673a\u76d0\u6eb6\u6db2\u6df7\u5408\u540e\u6709\u6548\u6539\u5584\u4e86\u5355\u4e00\u6eb4 \u5316\u9502\u6eb6\u6db2\u5728\u5236\u51b7\u673a\u7ec4\u8fd0\u884c\u4e2d\u7684\u7f3a\u70b9\u3002\u89e3\u56fd\u73cd\u7b49[8]\u57fa \u4e8e\u4e8c\u5143\u6eb6\u6db2\u4e9a\u5e73\u8861\u539f\u7406,\u901a\u8fc7\u589e\u52a0\u5438\u6536\u538b\u529b\u5927\u5927\u63d0 \u9ad8\u4e86\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5236\u51b7\u673a\u7ec4\u7684\u6027\u80fd\u3002\u672c\u6587\u57fa\u4e8e\u6eb4\u5316 \u9502\u6c34\u6eb6\u6db2\u6c14\u6db2\u7279\u6027\u4e2d\u6c7d\u6db2\u76f8\u5e73\u8861\u548c\u6eb6\u6db2\u6df7\u5408\u4e0e\u5206\u79bb \u7684\u539f\u7406,\u901a\u8fc7\u8c03\u8282\u673a\u7ec4\u5faa\u73af\u8fc7\u7a0b\u4e2d\u5185\u90e8\u548c\u5916\u90e8\u7684\u53c2 \u6570,\u5b9e\u9a8c\u5206\u6790\u5bf9\u5236\u51b7\u673a\u7ec4\u5236\u51b7\u7279\u6027\u7684\u8026\u5408\u5f71\u54cd\u3002", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[0, [9.100000381469727, 611.7999877929688, 469.8999938964844, 633.2999877929688]], [1, [10.0, 46.0, 250.5, 517.5999755859375]]]}, {"citation_id": 15, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 5, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "1\u6eb4\u5316\u9502\u6c34\u6eb6\u6db2\u6c14\u6db2\u7279\u6027 \u6839\u636e\u5eb7\u8bfa\u74e6\u7f57\u592b\u5b9a\u5f8b[2],\u7406\u60f3\u6eb6\u6db2\u4e2d\u6db2\u76f8\u548c\u6c14 \u76f8\u4e2d\u7684\u6210\u5206\u662f\u4e0d\u540c\u7684\u3002\u5728\u7ed9\u5b9a\u6e29\u5ea6\u4e0b,\u5c06\u4e24\u79cd\u4e0d\u540c \u84b8\u6c14\u538b\u529b\u7684\u7eaf\u6db2\u4f53\u6df7\u5408\u6210\u4e8c\u5143\u6eb6\u6db2,\u6c14\u76f8\u548c\u6db2\u76f8\u91cc \u7684\u6469\u5c14\u5206\u6570\u4e0d\u76f8\u540c,\u5bf9\u4e8e\u5177\u6709\u8f83\u9ad8\u84b8\u6c14\u538b\u529b\u7684\u7ec4 \u5206,\u5b83\u5728\u6c14\u76f8\u91cc\u7684\u6469\u5c14\u5206\u6570\u5927\u4e8e\u5728\u6db2\u76f8\u91cc\u7684\u6469\u5c14 \u5206\u6570\u3002 11\u6c7d\u6db2\u76f8\u5e73\u8861 \u7531\u5eb7\u8bfa\u74e6\u7f57\u592b\u5b9a\u5f8b\u53ef\u4ee5\u5f97\u5230,\u6eb4\u5316\u9502\u6c34\u6eb6\u6db2\u662f \u7531\u6eb4\u5316\u9502\u6eb6\u6db2\u548c\u6c34\u7ec4\u5408\u6210\u7684\u4e8c\u5143\u6eb6\u6db2,\u56e0\u6b64,\u5728\u6c14 \u76f8\u548c\u6db2\u76f8\u91cc\u7684\u6210\u5206\u662f\u4e0d\u540c\u7684\u3002\u5982\u56fe1\u6240\u793a,\u66f2\u7ebf \u7283\u7285\u7286\u4e3a\u6db2\u76f8\u9971\u548c\u66f2\u7ebf,\u66f2\u7ebf\u7283\u7285\u2032\u7286\u4e3a\u5e72\u9971\u548c\u84b8\u6c14 \u7ebf,\u6db2\u76f8\u9971\u548c\u66f2\u7ebf\u4ee5\u4e0a\u533a\u57df\u4e3a\u6db2\u4f53\u533a,\u5e72\u9971\u548c\u84b8\u6c14 \u7ebf\u4ee5\u4e0b\u4e3a\u8fc7\u70ed\u84b8\u6c14\u533a,\u4e24\u8005\u4e4b\u95f4\u4e3a\u6e7f\u84b8\u6c14\u533a\u3002\u56e0\u4e3a \u84b8\u53d1\u8fc7\u7a0b\u662f\u5728\u7b49\u538b\u4e0b\u8fdb\u884c\u7684,\u4e3a\u4e86\u65b9\u4fbf\u7814\u7a76\u84b8\u53d1\u8fc7 \u7a0b,\u91c7\u7528\u729c\u72d3\u56fe(\u56fe2)\u3002\u56fe\u4e2d\u66f2\u7ebf\u72aa\u72ab\u72ae\u4e3a\u6db2\u76f8\u9971 \u548c\u66f2\u7ebf,\u66f2\u7ebf\u72aa\u72ab\u2032\u72ae\u4e3a\u5e72\u9971\u548c\u84b8\u6c14\u7ebf,\u5b83\u4eec\u6784\u6210\u7684 \u533a\u57df\u6b63\u597d\u4e0e\u7298\u72d3\u56fe\u76f8\u53cd\u3002", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[1, [6.699999809265137, 517.5999755859375, 250.5, 722.2000122070312]], [1, [261.70001220703125, 41.599998474121094, 501.8999938964844, 140.3000030517578]]]}, {"citation_id": 16, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 17, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "18500 15500 cooling capacity/W50%\n54%\n58%\n12500 9500 1.7 1.9 2.1 2.3 2.5 2.7 6500 absorption pressure/kPa \u56fe9\u5236\u51b7\u91cf\u968f\u5438\u6536\u538b\u529b\u7684\u53d8\u5316 Fig.9Coolingcapacityvariedwithabsorptionpressure atdifferentfillingconcentration 1.7 1.9 2.1 2.3 2.5 2.7 absorption pressure/kPa 0.4 0.5 0.6 0.7 0.8 0.9 1.0 1.1 COP\n50% 54% 58%", "content_type": "Figure", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[4, [258.5, 306.70001220703125, 495.20001220703125, 516.2000122070312]], [4, [264.5, 515.4000244140625, 475.5, 668.0999755859375]]]}, {"citation_id": 17, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 13, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "48 50 52 54 56 58 60 12000 12500 13000 13500 14000 14500 15000 15500 16000 16500 cooling capacity/W13 15 17 filling concentration/%\n0.90 0.95 0.85 COP\n13 0.80 15 17 48 50 52 54 56 58 60 0.70 0.75 filling concentration/%", "content_type": "Figure", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[3, [15.899999618530273, 531.2999877929688, 234.89999389648438, 668.0999755859375]], [3, [265.8999938964844, 49.5, 488.20001220703125, 200.60000610351562]]]}, {"citation_id": 18, "collection_type": "private", "collection_id": "6656f05dc349ccbde6011ca9", "doc_id": 7203709868404903936, "block_id": 14, "title": "\u6eb4\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af\u7684\u5185\u5916\u70ed\u7269\u7406\u53c2\u6570\u4e0e\u673a\u7ec4\u5236\u51b7\u7279\u6027\u8026\u5408", "authors": ["\u738b\u521a", " \u89e3\u56fd\u73cd", " \u738b\u4eae\u4eae"], "content": "\u56fe6COP\u503c\u968f\u5145\u6ce8\u6d53\u5ea6\u7684\u53d8\u5316 Fig.6COPvariedwithfillingconcentrationat differentevaporationtemperature \u5347\u9ad8\u800c\u589e\u5927,\u5176\u589e\u5e45\u57281.3%~5.7%;\u76f8\u540c\u84b8\u53d1 \u6e29\u5ea6\u4e0b,\u5145\u6ce8\u6d53\u5ea6\u753150%\u589e\u81f358%\u673a\u7ec4\u7684\u5236\u51b7\u91cf \u968f\u7740\u5145\u6ce8\u6d53\u5ea6\u7684\u589e\u52a0\u800c\u589e\u5927,\u5176\u589e\u5e45\u57289.1%~ 17.55%;\u540c\u6837COP\u503c\u4e5f\u968f\u84b8\u53d1\u6e29\u5ea6\u548c\u5145\u6ce8\u6d53\u5ea6\u5347 \u9ad8\u800c\u589e\u52a0,\u5176\u589e\u5e45\u8303\u56f4\u5206\u522b\u4e3a1.14%~6.17%\u548c 9.6%~18.2%\u3002\u673a\u7ec4COP\u503c\u5728\u8017\u70ed\u91cf\u53d8\u5316\u4e0d\u5927\u7684 \u60c5\u51b5\u4e0b,\u968f\u7740\u5236\u51b7\u91cf\u7684\u53d8\u5316\u800c\u53d8\u5316\u3002\u5145\u6ce8\u6d53\u5ea6\u589e \u52a0,\u6eb6\u6db2\u7684\u9971\u548c\u84b8\u6c14\u538b\u529b\u4e0b\u964d,\u7531\u4e8e\u84b8\u53d1\u6e29\u5ea6\u4e0d \u53d8,\u5438\u6536\u5668\u5185\u7684\u5438\u6536\u538b\u529b\u4e0d\u53d8,\u4ece\u800c\u5bfc\u81f4\u6c34\u84b8\u6c14\u538b \u529b\u4e0e\u6eb6\u6db2\u9971\u548c\u84b8\u6c14\u538b\u529b\u4e4b\u5dee\u589e\u5927,\u589e\u5f3a\u4f20\u8d28\u80fd\u529b, \u6700\u7ec8\u5bfc\u81f4\u5236\u51b7\u91cf\u4e0a\u5347\u3002\u4f46\u662f,\u53d7\u5230\u673a\u7ec4\u51b7\u51dd\u5668\u51b7\u51dd \u6362\u70ed\u9762\u79ef\u548c\u53d1\u751f\u9762\u79ef\u7684\u9650\u5236,\u968f\u7740\u5145\u6ce8\u6d53\u5ea6\u7684\u589e \u52a0,\u5236\u51b7\u91cf\u589e\u52a0\u4e00\u5b9a\u7684\u503c\u540e\u5f00\u59cb\u4e0b\u964d;\u84b8\u53d1\u6e29\u5ea6\u5347 \u9ad8,\u84b8\u53d1\u5668\u4e2d\u7684\u84b8\u53d1\u538b\u529b\u589e\u52a0,\u4e0e\u5176\u8fde\u901a\u7684\u5438\u6536\u5668 \u5185\u5438\u6536\u538b\u529b\u589e\u52a0,\u589e\u5f3a\u4e86\u6eb6\u6db2\u7684\u4f20\u8d28\u63a8\u52a8\u529b,\u6eb4\u5316 \u9502\u6eb6\u6db2\u7684\u5438\u6536\u80fd\u529b\u589e\u5f3a,\u56e0\u6b64,\u5236\u51b7\u91cc\u5448\u73b0\u51fa\u968f\u84b8 \u53d1\u6e29\u5ea6\u5347\u9ad8\u800c\u589e\u5927\u7684\u8d8b\u52bf\u3002 32\u51b7\u5374\u6c34\u5165\u53e3\u6e29\u5ea6\u4e0e\u5145\u6ce8\u6d53\u5ea6\u8026\u5408\u5f71\u54cd \u5438\u6536\u5668\u5185\u5145\u6ce8\u4e0d\u540c\u6d53\u5ea6\u7684\u6eb6\u6db2,\u5176\u6d53\u5ea6\u5206\u522b\u4e3a 50%\u300152%\u300154%\u300156%\u548c58%;\u51b7\u5a92\u6c34\u7684\u8fdb\u51fa \u53e3\u6d41\u91cf\u4fdd\u6301\u4e0d\u53d8,\u4f7f\u84b8\u53d1\u5668\u5185\u7684\u84b8\u53d1\u6e29\u5ea6\u4fdd\u6301\u5728 15\u2103\u00b11\u2103;\u53d1\u751f\u5668\u5185\u9ad8\u6e29\u70ed\u6e90\u5165\u53e3\u6e29\u5ea6\u4e3a140\u2103;\n\u673a\u7ec4\u51b7\u5374\u6c34\u7684\u6d41\u91cf\u4fdd\u6301\u4e0d\u53d8,\u8c03\u8282\u51b7\u5374\u6c34\u8fdb\u53e3\u6e29 \u5ea6,\u4f7f\u8fdb\u53e3\u51b7\u5374\u6c34\u6e29\u5ea6\u5206\u522b\u4e3a28\u300130\u300132\u2103,\u5206 \u6790\u4e0d\u540c\u51b7\u5374\u6c34\u5165\u53e3\u6e29\u5ea6\u548c\u5145\u6ce8\u6d53\u5ea6\u5bf9\u5236\u51b7\u91cf\u548c COP\u503c\u7684\u8026\u5408\u5f71\u54cd\u3002 \u7531\u56fe7\u3001\u56fe8\u53ef\u4ee5\u770b\u51fa,\u76f8\u540c\u5145\u6ce8\u6d53\u5ea6\u4e0b\u51b7\u5374 \u6c34\u5165\u53e3\u6e29\u5ea6\u5206\u522b\u4e3a28\u300130\u300132\u2103\u65f6,\u5236\u51b7\u91cf\u968f\u51b7 \u5374\u6c34\u5165\u53e3\u6e29\u5ea6\u5347\u9ad8\u800c\u51cf\u5c0f,\u5176\u964d\u5e45\u57283.13%~ 13.5%;\u76f8\u540c\u51b7\u5374\u6c34\u5165\u53e3\u6e29\u5ea6\u4e0b,\u5145\u6ce8\u6d53\u5ea6\u7531", "content_type": "Text-Fragment", "section": "\u7286\u72c5\u72cc\u72c6\u72be\u72bb\u72c0\u72b5\u72c5\u72b3\u72be\u72bb\u72cb\u72ba\u72bb\u72cc\u72bf\u72ab\u72c9\u72c5\u72bf\u72bb\u72b1\u72b2\u72aa\u72ab\u72ca\u72c5\u72c9\u72c6\u72cb\u72bb\u72c5\u72c0\u72ae\u72d4\u72ae\u72be\u72b2\u72bb\u72c0\u72ca\u72bb\u72b1\u72b2\u72aa\u72c0\u72b1\u72c5\u72cc\u72cb\u72ca\u72bb\u72b1\u72b2\u72cb\u72ba\u72b2\u72c9\u72bf\u72aa\u72be \u72c6\u72ba\u72d4\u72ca\u72bb\u72ae\u72aa\u72be\u72c6\u72aa\u72c9\u72aa\u72bf\u72b2\u72cb\u72b2\u72c9\u72ca\u72aa\u72c0\u72b1\u72c9\u72b2\u72b3\u72c9\u72bb\u72b5\u72b2\u72c9\u72aa\u72cb\u72bb\u72c5\u72c0\u72cc\u72c0\u72bb\u72cb\u72ae\u72ba\u72aa\u72c9\u72aa\u72ae\u72cb\u72b2\u72c9\u72bb\u72ca\u72cb\u72bb\u72ae\u72ca \u72a0\u7283\u7296\u728c\u728c\u72aa\u72c0\u72b5,\u72a1\u7290\u7288\u728c\u72cc\u72c5\u72d5\u72ba\u72b2\u72c0,\u72a0\u7283\u7296\u728c\u7294\u72bb\u72aa\u72c0\u72b5\u72be\u72bb\u72aa\u72c0\u72b5", "bbox": [[3, [259.1000061035156, 201.60000610351562, 506.0, 723.2999877929688]]]}], "chunk": null, "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u8fd9\u7bc7\u6587\u732e\u7684", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u8be6\u7ec6\u4fe1\u606f\u5982\u4e0b\uff1a\n\n", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "- **", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u6807\u9898**: \u6eb4", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u5316\u9502\u5438\u6536\u5f0f\u5faa\u73af", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u7684\u5185\u5916\u70ed\u7269\u7406", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u53c2\u6570\u4e0e\u673a\u7ec4", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": "\u7814\u7a76\u5185\u5bb9\u7684\u6982\u8ff0\u3002", "statistics": null, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "27784f8a-5388-4ee2-b35f-f80d84bbd372", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-4o", "input_tokens": 12388, "output_tokens": 431}, "metadata": {"session_id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "conversation", "name": null, "run_id": null, "id": "299439b0-2e2d-45ba-b54d-b590dbecb2a3", "question_id": "9e1cae29-ebf3-469a-812f-52fd6c449848"}
                        
                        ''',
                    ),
                ],
            ),
            (400, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL', 'source': f'''curl --request POST \\
    "{OPENAPI_BASE_URL}/openapi/v1/chat" \\
    --header 'Content-Type: application/json' \\
    --header 'X-API-KEY: ••••••' \\
    --data '{{
        "content": "what is LLM",
        "conversation_id": "d02df0c9-9df2-4d3b-9c32-2cc3ab27f726",
        "topic_id": "367a4c84-8738-444b-856d-90e6196c6fe6"
    }}' 
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
