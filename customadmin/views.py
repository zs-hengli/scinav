import logging

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import extract_json, my_json_response
from customadmin.models import GlobalConfig
from customadmin.serializers import GlobalConfigPostQuerySerializer
from customadmin.service import get_global_configs, set_global_configs

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'admin index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class GlobalConfigs(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()

        if query.get('config_types'):
            config_types = query['config_types'].split(',')
        else:
            config_types = [
                GlobalConfig.ConfigType.MEMBER_FREE,
                GlobalConfig.ConfigType.MEMBER_STANDARD,
                GlobalConfig.ConfigType.MEMBER_PREMIUM,
                GlobalConfig.ConfigType.AWARD
            ]
        data = get_global_configs(config_types)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = GlobalConfigPostQuerySerializer(data=query, many=True)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error')
        date = set_global_configs(request.user.id, serial.data)
        return my_json_response(date)