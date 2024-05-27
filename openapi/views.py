import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import extract_json, my_json_response
from document.service import get_url_by_object_path
from openapi.models import OpenapiKey
from openapi.serializers import OpenapiKeyCreateQuerySerializer, OpenapiKeyUpdateQuerySerializer, \
    OpenapiListQuerySerializer, UsageBaseSerializer, UsageChatQuerySerializer
from openapi.service import create_openapi_key, update_openapi_key, delete_openapi_key, list_openapi_key, \
    usage_document_extract, usage_conversation

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'openapi index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
class ApiKey(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = OpenapiListQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = list_openapi_key(request.user.id, vd['page_size'], vd['page_num'], vd['is_all'], vd['is_used'])
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        request_data = request.data
        serial = OpenapiKeyCreateQuerySerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, msg=f'validate error, {list(serial.errors.keys())}')
        if OpenapiKey.objects.filter(user_id=request.user.id, del_flag=False).count() >= 100:
            return my_json_response({}, 150001, msg='openapi key number limit')
        data = create_openapi_key(request.user.id, serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def put(request, openapi_id, *args, **kwargs):
        request_data = request.data
        openapi_key = OpenapiKey.objects.filter(id=openapi_id, del_flag=False, user_id = request.user.id).first()
        if not openapi_key:
            return my_json_response({}, 100001, msg='openapi key not found')
        serial = OpenapiKeyUpdateQuerySerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, msg=f'validate error, {list(serial.errors.keys())}')
        data = update_openapi_key(openapi_key, serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def delete(request, openapi_id, *args, **kwargs):
        openapi_key = OpenapiKey.objects.filter(id=openapi_id, del_flag=False, user_id=request.user.id).first()
        if not openapi_key:
            return my_json_response({}, 100001, msg='openapi key not found')
        delete_openapi_key(openapi_key)
        return my_json_response({'id': openapi_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentExtractUsage(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = UsageBaseSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, msg=f'validate error, {list(serial.errors.keys())}')
        data = usage_document_extract(request.user.id, serial.validated_data)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class ConversationUsage(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = UsageChatQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, msg=f'validate error, {list(serial.errors.keys())}')
        data = usage_conversation(request.user.id, serial.validated_data)
        return my_json_response(data)