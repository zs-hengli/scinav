import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)


@csrf_exempt
@api_view(http_method_names=['GET'])
@permission_classes([AllowAny])
def index(request):
    # raise MyAPIException('aaaaaa', status=200)
    # raise ValidationError('aaaaaa', status=200)
    # raise NotFound('aaaaa', 200)
    return HttpResponse("Hello, world. You're at the polls index.")
