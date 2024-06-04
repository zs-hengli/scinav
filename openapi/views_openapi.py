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
from bot.service import bot_list_all, bot_list_my
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
    DocumentLibraryPersonalSerializer
from openapi.serializers_openapi import SearchQuerySerializer, ExceptionResponseSerializer, TopicListSerializer
from openapi.service import upload_paper, get_request_openapi_key_id
from openapi.service_openapi import search

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
        # return openapi_exception_response(100000, '系统内部错误 请联系管理员', status=400)


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
        description='search papers',
        tags=['Papers'],
        parameters=[SearchQuerySerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(SearchDocumentResultSerializer(many=True)),
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    'http://localhost:8300/openapi/v1/papers/search?content=LLM&limit=100' \\
    --header 'X-API-KEY: ••••••'
\n'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import requests

headers = {
  'X-API-KEY': '••••••'
}
url = "http://localhost:8300/openapi/v1/papers/search?content=LLM&limit=100"

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
            return openapi_exception_response(100001, error_msg, status=422)
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
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL', 'source': '''curl --request PUT \\
    -T '<path>/xxx.pdf' \\
    'http://<host>/openapi/v1/papers/upload/xxx.pdf' \\
    --header 'Content-Type: application/octet-stream' \\
    --header 'X-API-KEY: ••••••'\n
'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import requests

headers = {
  'Content-Type': 'application/octet-stream',
  'X-API-KEY': '••••••'
}
file_path = '<path>/xxx.pdf'
url = "http://<host>/openapi/v1/papers/upload/xxx.pdf"
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
            return openapi_exception_response(100001, error_msg, status=422)

        if not file:
            error_msg = 'file not found'
            return openapi_exception_response(100001, error_msg, status=422)
        # logger.debug(f'ddddddddd file: {file.name}, {file.file}')
        code, msg, data = upload_paper(user_id, file)

        record_openapi_log(
            user_id, openapi_key_id, OpenapiLog.Api.UPLOAD_PAPER, OpenapiLog.Status.SUCCESS, obj_id1=data['task_id']
        )
        if code != 0:
            return openapi_exception_response(code, msg, status=422)
        return openapi_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class PersonalLibrary(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List Personal Library',
        description='list personal library, list order by updated_at desc',
        tags=['PersonalLibrary'],
        parameters=[PersonalLibraryRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(DocumentLibraryPersonalSerializer(many=True),),
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    'http://<host>/openapi/v1/personal/library?status=completed&limit=100' \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import requests
            
headers = {
  'X-API-KEY': '••••••'
}
url = "http://<host>/openapi/v1/personal/library?status=completed&limit=100"

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
            return openapi_exception_response(100001, error_msg, status=422)
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
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class TopicPlaza(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List Topic Plaza',
        description='List Topic Plaza',
        tags=['Topics'],
        parameters=[TopicListRequestSerializer],
        # request={''},
        responses={
            (200, 'application/json'): OpenApiResponse(TopicListSerializer,),
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    'http://<host>/openapi/v1/topics/plaza?limit=100' \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import requests
            
headers = {
  'X-API-KEY': '••••••'
}
url = "http://<host>/openapi/v1/topics/plaza?limit=100"

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
            return openapi_exception_response(100001, error_msg, status=422)
        vd = serial.validated_data
        data = bot_list_all(request.user.id, vd['limit'])
        return openapi_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@throttle_classes([UserRateThrottle])
class MyTopics(APIView):
    @staticmethod
    @extend_schema(
        operation_id='List My Topics',
        description='List My Topics',
        tags=['Topics'],
        parameters=[TopicListRequestSerializer],
        responses={
            (200, 'application/json'): OpenApiResponse(TopicListSerializer,),
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL',
             'source': '''curl -X GET \\
    'http://<host>/openapi/v1/topics/my?limit=100' \\
    --header 'X-API-KEY: ••••••'
'''
             },
            {'lang': 'python', 'label': 'Python', 'source': '''import requests
            
headers = {
  'X-API-KEY': '••••••'
}
url = "http://<host>/openapi/v1/topics/my?limit=100"

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
            return openapi_exception_response(100001, error_msg, status=422)
        vd = serial.validated_data
        data = bot_list_my(request.user.id, vd['limit'])
        return openapi_response(data['list'])


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
            ),
            (422, 'application/json'): OpenApiResponse(ExceptionResponseSerializer),
        },
        extensions={'x-code-samples': [
            {'lang': 'curl', 'label': 'cURL', 'source': '''curl --request POST \\
    'http://<host>/openapi/v1/chat' \\
    --header 'Content-Type: application/json' \\
    --header 'X-API-KEY: ••••••' \\
    --data '{
        "content": "what is LLM",
        "conversation_id": "d02df0c9-9df2-4d3b-9c32-2cc3ab27f726",
        "topic_id": "367a4c84-8738-444b-856d-90e6196c6fe6"
    }' 
\n'''},
            {'lang': 'python', 'label': 'Python', 'source': '''import requests
import json

url = "http://<host>/openapi/v1/chat"

payload = json.dumps({
  "content": "what is LLM",
  "conversation_id": "d02df0c9-9df2-4d3b-9c32-2cc3ab27f726",
  "topic_id": "367a4c84-8738-444b-856d-90e6196c6fe6"
})
headers = {
  'Content-Type': 'application/json',
  'X-API-KEY': '••••••'
}

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
