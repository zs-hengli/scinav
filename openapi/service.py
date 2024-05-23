import io
import logging

import requests
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q

from document.service import presigned_url, document_personal_upload
from openapi.models import OpenapiKey
from openapi.serializers import OpenapiKeyDetailSerializer, OpenapiKeyCreateDetailSerializer

logger = logging.getLogger(__name__)


def upload_paper(user_id, file: InMemoryUploadedFile):
    ret = presigned_url(user_id, file.name)
    url = ret['presigned_url']
    object_path = ret['object_path']
    headers = {
        'Content-Type': 'application/octet-stream',
        'x-ms-blob-type': 'BlockBlob',
    }

    res = requests.put(url, data=file.file, headers=headers)

    if res.status_code != 201:
        logger.warning(f'upload_paper res.content: {res.content}')
        return 100000, 'upload paper failed', {}
    doc_person_lib_data = {
        'user_id': user_id,
        'files': [{
            'object_path': object_path,
            'filename': file.name,
        }],
    }
    logger.info(f'upload paper, info: {doc_person_lib_data}')
    document_personal_upload(doc_person_lib_data)
    return 0, '', {'object_path': object_path}



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