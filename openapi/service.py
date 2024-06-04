import datetime
import io
import logging

import requests
from dateutil.relativedelta import relativedelta
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q

from chat.models import Conversation
from document.service import presigned_url, document_personal_upload
from openapi.models import OpenapiKey, OpenapiLog
from openapi.serializers import OpenapiKeyDetailSerializer, OpenapiKeyCreateDetailSerializer, UsageBaseSerializer, \
    UsageChatQuerySerializer

logger = logging.getLogger(__name__)


def get_request_openapi_key_id(request):
    headers = request.headers
    openapi_key = headers.get('X-API-KEY', '')
    _, openapi_key_id, openapi_key_str = openapi_key.split('-')
    return int(openapi_key_id)


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
    doc_libs = document_personal_upload(doc_person_lib_data)
    task_id = doc_libs[0].task_id
    return 0, '', {'object_path': object_path, 'task_id': task_id}


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


def list_openapi_key(user_id, page_size, page_num, is_all=False, is_used=None):
    if is_all:
        filter_query = Q(user_id=user_id)
    else:
        filter_query = Q(user_id=user_id, del_flag=False)
    if is_used is not None:
        temp_Q = Q(id__in=OpenapiLog.objects.filter(
            user_id=user_id,
            api__in=[OpenapiLog.Api.UPLOAD_PAPER, OpenapiLog.Api.CONVERSATION],
            created_at__gt=datetime.datetime.now() - relativedelta(year=1)
        ).values_list('openapi_key_id', flat=True))
        if is_used:
            filter_query &= temp_Q
        else:
            filter_query &= ~temp_Q
    start_num = page_size * (page_num - 1)
    query_set = OpenapiKey.objects.filter(filter_query).order_by('-created_at')
    openapi_keys = query_set[start_num:start_num + page_size]
    total = query_set.count()
    data = OpenapiKeyDetailSerializer(openapi_keys, many=True).data
    return {
        'list': data,
        'total': total,
    }


def usage_document_extract(user_id, validated_data):
    vd = validated_data
    schedule_type = vd['schedule_type']
    parts_info = UsageBaseSerializer.get_schedule_parts_info(schedule_type)
    api = OpenapiLog.Api.UPLOAD_PAPER
    statis_data = {}
    for part_info in parts_info:
        total_list = []
        if part_info['part_type'] == 'day':
            static = OpenapiLog.static_by_day(user_id, api, part_info['min_date'], vd['openapi_key_id'])
        else:
            static = OpenapiLog.static_by_month(user_id, api, part_info['min_date'], vd['openapi_key_id'])
        static_dict = {s['date']:s for s in static}
        for part in part_info['part_list']:
            if part in static_dict:
                total_list.append(static_dict[part]['count'])
            else:
                total_list.append(0)
        statis_data[part_info['part_type']] = {
            'label': part_info['part_list'],
            'value': total_list
        }
    return statis_data


def usage_conversation(user_id, validated_data):
    vd = validated_data
    model = vd['model']
    schedule_type = vd['schedule_type']
    parts_info = UsageBaseSerializer.get_schedule_parts_info(schedule_type)
    api = OpenapiLog.Api.CONVERSATION
    statis_data = {}
    for part_info in parts_info:
        part_type = part_info['part_type']
        total_list = []
        if part_type == 'day':
            static = OpenapiLog.static_by_day(user_id, api, part_info['min_date'], vd['openapi_key_id'], model)
        else:
            static = OpenapiLog.static_by_month(user_id, api, part_info['min_date'], vd['openapi_key_id'], model)
        if model:
            static_dict = {s['date']:s for s in static}
            for part in part_info['part_list']:
                if part in static_dict:
                    total_list.append(static_dict[part]['count'])
                else:
                    total_list.append(0)
            statis_data[part_type] = {
                'label': part_info['part_list'],
                model: total_list
            }
        else:
            temp_data = {
                'label': part_info['part_list'],
            }
            for m in Conversation.LLMModel.values:
                temp_data[m] = []
                static_dict = {s['date']:s for s in static if s['model'] == m}
                for part in part_info['part_list']:
                    if part in static_dict:
                        temp_data[m].append(static_dict[part]['count'])
                    else:
                        temp_data[m].append(0)
            statis_data[part_type] = temp_data
    return statis_data