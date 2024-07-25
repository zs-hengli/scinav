
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import extract_json, my_json_response
from customadmin.service import Notice
from user.serializers import UserSyncQuerySerializer, UserSyncRespSerializer
from user.service import sync_user_info

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'user index'}

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
# @permission_classes([AllowAny])
class Users(APIView):

    @staticmethod
    def put(request, *args, **kwargs):
        data = {}
        query = request.data
        serial = UserSyncQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, 100001, f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        user = sync_user_info(request.user, vd)
        return my_json_response(UserSyncRespSerializer(user).data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
# @permission_classes([AllowAny])
class Callback(APIView):

    def get(self, request, app_id=None, *args, **kwargs):  # noqa
        logger.debug(f'app_id: {app_id}, kwargs: {kwargs}')
        logger.debug(f'request.headers: {request.headers}')
        data = {'desc': 'user Callback'}

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class Notices(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        data = Notice.get_active_notice()
        return my_json_response(data)


class ApiT(APIView):

    def get(self, request, app_id=None, *args, **kwargs):  # noqa
        logger.debug(f'app_id: {app_id}, kwargs: {kwargs}')
        logger.debug(f'request.headers: {request.headers}')
        data = {'desc': 'user ApiT'}

        return my_json_response(data)
