import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import extract_json, my_json_response

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'chat index'}

        return my_json_response(data)
