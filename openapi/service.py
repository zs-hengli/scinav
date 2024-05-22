import logging

from django.db.models import Q

from openapi.models import OpenapiKey
from openapi.serializers_api import OpenapiKeyDetailSerializer, OpenapiKeyCreateDetailSerializer

logger = logging.getLogger(__name__)


def create_openapi_key(user_id, validated_data):
    vd = validated_data
    title = vd['title']
    openapi_key = OpenapiKey.objects.create(user_id=user_id, title=title)
    api_real_key = openapi_key.gen_real_key()
    openapi_key.api_key_show = openapi_key.gen_show_key(api_real_key)
    openapi_key.api_key = OpenapiKey.encode(OpenapiKey.gen_salt(), api_real_key)
    openapi_key.save()
    detail = OpenapiKeyDetailSerializer(openapi_key).data
    detail['api_key'] = api_real_key
    data = OpenapiKeyCreateDetailSerializer(detail).data
    return data


def update_openapi_key(openapi_key: OpenapiKey, validated_data):
    vd = validated_data
    openapi_key.title = vd['title']
    openapi_key.save()
    data = OpenapiKeyDetailSerializer(openapi_key).data
    return data


def delete_openapi_key(openapi_key: OpenapiKey):
    openapi_key.del_flag = True
    openapi_key.save()


def list_openapi_key(user_id, page_size, page_num):
    filter_query = Q(user_id=user_id, del_flag=False)
    start_num = page_size * (page_num - 1)
    query_set = OpenapiKey.objects.filter(filter_query).order_by('-created_at')
    openapi_keys = query_set[start_num:start_num + page_size]
    total = query_set.count()
    data = OpenapiKeyDetailSerializer(openapi_keys, many=True).data
    return {
        'list': data,
        'total': total,
    }