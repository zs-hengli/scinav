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
                        value='''{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "4d1fe262-5b43-4b63-90b8-816c428f5e76", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-4o", "input_tokens": 736, "output_tokens": 22}, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "tool_start", "name": "paper_content_search", "run_id": "2020e2e7-a4cf-4677-ab29-1e569c164984", "input": {"queries": ["The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems"]}, "output": null, "chunk": null, "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event":"tool_end","name":"paper_content_search","run_id":"2020e2e7-a4cf-4677-ab29-1e569c164984","input":{"queries":["The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems"]},"output":[{"citation_id":1,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":6,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"2 The Deep Ritz Method An explicit example of the kind of variational problems we are interested in is [8]","content_type":"Text-Fragment","section":"2 The Deep Ritz Method","bbox":[[1,[68.03099822998047,197.17543029785156,501.6908264160156,239.37269592285156]]]},{"citation_id":2,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":13,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"then we are left with the optimization problem:","content_type":"Text-Fragment","section":"2.1 Building trial functions","bbox":[[3,[68.03099822998047,104.01663208007812,311.9171447753906,115.9837875366211]]]},{"citation_id":3,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":14,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"2.2 The stochastic gradient descent algorithm and the quadrature rule To finish describing the algorithm, we need to furnish the remaining two components: the optimization algorithm and the discretization of the integral in $I$ in (2) or $L$ in (8). ","content_type":"Formula","section":"2.2 The stochastic gradient descent algorithm and the quadrature rule","bbox":[[3,[68.031005859375,171.19232177734375,527.3961181640625,413.1190490722656]]]},{"citation_id":4,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":null,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"","content_type":"Abstract","section":"Abstract","bbox":null},{"citation_id":5,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":42,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"In this case, we can simply use","content_type":"Text-Fragment","section":"3.3 An example with the Neumann boundary condition","bbox":[[7,[85.5899658203125,480.86358642578125,243.54209899902344,492.83074951171875]]]},{"citation_id":6,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":43,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"$$I(u)=\\int_{\\Omega}\\left(\\frac{1}{2}\\left(|\\nabla u(x)|^{2}+\\pi^{2}u(x)^{2}\\right)-f(x)u(x)\\right)dx$$\\n\\nwithout any penalty function for the boundary.","content_type":"Formula","section":"3.3 An example with the Neumann boundary condition","bbox":[[7,[68.03097534179688,496.3545837402344,527.2374877929688,586.9447631835938]]]},{"citation_id":7,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":0,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"# The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm For Solving Variational Problems\\n","content_type":"Title","section":"","bbox":[[0,[80.83399963378906,145.810302734375,514.6018676757812,191.37879943847656]]]},{"citation_id":8,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":7,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"Problems of this type are fairly common in physical sciences. The Deep Ritz method is based on the following set of ideas:","content_type":"Formula","section":"2 The Deep Ritz Method","bbox":[[1,[68.031005859375,277.1044616699219,527.2748413085938,375.5457763671875]]]},{"citation_id":9,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":8,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"1. Deep neural network based approximation of the trial function. 2. A numerical quadrature rule for the functional. 3. An algorithm for solving the final optimization problem.","content_type":"List-item","section":"2 The Deep Ritz Method","bbox":[[1,[82.33900451660156,386.2306213378906,422.0820007324219,444.6417541503906]]]},{"citation_id":10,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":9,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"2.1 Building trial functions The basic component of the Deep Ritz method is a nonlinear transformation ","content_type":"Formula","section":"2.1 Building trial functions","bbox":[[1,[68.03085327148438,464.9293518066406,527.302001953125,701.8250122070312]]]},{"citation_id":11,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":59,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"$$L_{0}(x)={\\frac{\\int_{\\Omega}|\\nabla u|^{2}d x+\\int_{\\Omega}v u^{2}d x}{\\int_{\\Omega}u^{2}d x}}+\\beta\\int_{\\partial\\Omega}u(x)^{2}d x$$","content_type":"Formula","section":"3.5 Eigenvalue problems","bbox":[[9,[175.53099060058594,428.9057312011719,419.74127197265625,475.69439697265625]]]},{"citation_id":12,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":60,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"In practice, we use","content_type":"Text-Fragment","section":"3.5 Eigenvalue problems","bbox":[[9,[68.03094482421875,575.2076416015625,163.6845245361328,587.1748046875]]]},{"citation_id":13,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":61,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"$$L(u(x;\\theta))=\\frac{\\int_{\\Omega}|\\nabla u|^{2}dx+\\int_{\\Omega}vu^{2}dx}{\\int_{\\Omega}u^{2}dx}+\\beta\\int_{\\partial\\Omega}u(x)^{2}dx+\\gamma\\left(\\int_{\\Omega}u^{2}dx-1\\right)^{2}\\tag{23}$$\\n\\nOne might suggest that with the last penalty term ","content_type":"Formula","section":"3.5 Eigenvalue problems","bbox":[[9,[68.0308837890625,591.0936279296875,527.3019409179688,684.3797607421875]]]},{"citation_id":14,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":1,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"Weinan E1 and Bing Yu2\\n1The Beijing Institute of Big Data Research, ","content_type":"Text-Fragment","section":"","bbox":[[0,[68.031005859375,205.734375,527.3258666992188,449.98077392578125]]]},{"citation_id":15,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":2,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"We illustrate the method on several problems including some eigenvalue problems.","content_type":"Text-Fragment","section":"","bbox":[[0,[68.031005859375,438.01361083984375,527.2659912109375,464.4267883300781]]]},{"citation_id":16,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":3,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"Keywords Deep Ritz Method · Variational problems · PDE · Eigenvalue problems Mathematical Subject Classification 35Q68","content_type":"Text-Fragment","section":"","bbox":[[0,[68.03097534179688,481.0517272949219,494.86376953125,522.209716796875]]]},{"citation_id":17,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":58,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"To avoid getting the trivial optimizer u = 0, instead of using the functional","content_type":"Text-Fragment","section":"3.5 Eigenvalue problems","bbox":[[9,[85.58999633789062,413.8927307128906,471.3498229980469,425.8598937988281]]]},{"citation_id":18,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":74,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"The results in different dimensions are shown in Table 3.","content_type":"Text-Fragment","section":"Example 1: Infinite potential well Consider the potential function","bbox":[[11,[85.59004974365234,400.4656677246094,376.6036682128906,412.4328308105469]]]},{"citation_id":19,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":75,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"\\nTable:\\n| Dimension | d | Exact | λ |\\n|-------------|-------|---------|-------|\\n| 0 | | | |\\n| Approximate | Error | | |","content_type":"Table","section":"Example 1: Infinite potential well Consider the potential function","bbox":[[11,[176.5570068359375,458.7546081542969,418.7225036621094,515.2547607421875]]]},{"citation_id":20,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":66,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"The remaining components of the algorithm are very much the same as before.","content_type":"Text-Fragment","section":"3.5 Eigenvalue problems","bbox":[[10,[85.58999633789062,576.5526123046875,490.32147216796875,588.519775390625]]]},{"citation_id":21,"collection_type":"s2","collection_id":"s2","doc_id":2988078,"block_id":67,"title":"The Deep Ritz Method: A Deep Learning-Based Numerical Algorithm for Solving Variational Problems","authors":["E. Weinan"," Ting Yu"],"content":"Example 1: Infinite potential well Consider the potential function $$v(x)=\\left\\{\\begin{array}{ll}0,&x\\in[0,1]^{d}\\\\ \\infty,&x\\notin[0,1]^{d}\\end{array}\\right.\\tag{26}$$","content_type":"Formula","section":"Example 1: Infinite potential well Consider the potential function","bbox":[[10,[68.03099822998047,598.1995849609375,266.7502746582031,624.61181640625]],[10,[234.19000244140625,628.1366577148438,527.2479858398438,678.7610473632812]]]}],"chunk":null,"statistics":null,"metadata":{"session_id":"60f45d73-7958-4581-9c39-6c581df16480","user_id":"6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": "Here are the", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " key points of the", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " paper \"The Deep", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " Ritz Method: A", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " Deep Learning-Based Numerical", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " Algorithm for Solving", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " Variational Problems\":\\n\\n", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": "1. **Introduction", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " of the Deep Ritz", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " Method**:\\n  ", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " - The paper introduces", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_stream", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": " a deep learning-based", "statistics": null, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "model_statistics", "name": "BatchedChatOpenAI", "run_id": "b440ef6f-400f-4104-9438-0d689398e2b9", "input": null, "output": null, "chunk": null, "statistics": {"model_name": "gpt-4o", "input_tokens": 2826, "output_tokens": 419}, "metadata": {"session_id": "60f45d73-7958-4581-9c39-6c581df16480", "user_id": "6656f05dc349ccbde6011ca9"}}
{"event": "conversation", "name": null, "run_id": null, "id": "60f45d73-7958-4581-9c39-6c581df16480", "question_id": "65a11725-e99a-4b27-a755-9ce903f2a277"}

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
