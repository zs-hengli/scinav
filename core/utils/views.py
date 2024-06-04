import datetime
import json
import logging
import time
import traceback
import uuid
from functools import wraps

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from rest_framework.exceptions import APIException
from rest_framework.renderers import BaseRenderer

from core.utils.exceptions import ValidationError
from log_request_id.middleware import local

logger = logging.getLogger(__name__)


class APIError(BaseException):
    def __init__(self, msg, status=200, details=None):
        self.message = msg
        self.status = status
        self.details = details


def send_and_response(url, data_json, params=None, headers=None, method='POST', timeout=60):
    data_json_str = json.dumps(data_json)
    log_str = data_json_str if len(data_json_str) < 800 else f"{data_json_str[:200]} -- {data_json_str[-100:]}"
    logger.info(f'method: {method}, data_json: {log_str}, params: {params}, headers: {headers}')
    try:
        start_time = time.time()
        if method == 'POST':
            res = requests.post(url, json=data_json, params=params, headers=headers, verify=False, timeout=timeout)
        elif method == 'GET':
            res = requests.get(url, data=data_json, params=params, headers=headers, verify=False, timeout=timeout)
        elif method == 'DELETE':
            res = requests.delete(url, data=data_json, params=params, headers=headers, verify=False, timeout=timeout)
        elif method == 'PATCH':
            res = requests.patch(url, json=data_json, params=params, headers=headers, verify=False, timeout=timeout)
        elif method == 'PUT':
            res = requests.put(url, json=data_json, params=params, headers=headers, verify=False, timeout=timeout)
        else:
            raise ValueError(f'method:{method} not support')
        result_byte = res.content
        logger.info(f"query done , result : {len(result_byte) if len(result_byte) > 500 else result_byte}")
        end_time = time.time()
        logger.info(f"{url}: {res.status_code} tttttttttt 耗时: {(end_time - start_time):.8f}秒 time: {str(end_time)}")
        return json.loads(result_byte)
    except:  # noqa
        logger.error(f"query exceptions: {traceback.format_exc()}")
        return None


def get_post_json(request):
    try:
        body = json.loads(request.body.decode())
    except:  # noqa
        raise APIException(f'post数据，json格式化失败，请确认数据格式 {request.body}')
    logger.info(f'get_post_json: {request.body.decode()}')
    return body


def get_query(request):
    query = {}
    for d in request.GET:
        # logger.debug(f'request.get one:{d},{request.GET.getlist(d)}')
        one_value = request.GET.getlist(d)
        if d.endswith('[]'):
            d = d[:-2]
            if len(one_value) == 1 and one_value[0].find(',') > -1:
                one_value = one_value[0].split(',')
        if len(one_value) == 1:
            query[d] = one_value[0]
        elif len(one_value) > 1:
            query[d] = one_value
        else:
            raise ValidationError(f'get query error: {request.GET}, one_value:{one_value}')
    return query


def my_json_response(data=None, code=0, msg='', status=200, set_cookie=None):
    if data is None: data = {}
    res_data = {
        'code': code,
        'msg': msg,
        'data': data,
        'request_id': datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:8],
    }
    logger.info(f'response data: {res_data}')
    response = JsonResponse(res_data, status=status)
    if set_cookie: response.set_cookie(**set_cookie)
    return response


def openapi_response(data, status=200, set_cookie=None):
    logger.info(f'openapi response data: {data}')
    if not data:
        response = HttpResponse(status=200)
    else:
        response = JsonResponse(data, status=status, safe=False)
    if set_cookie: response.set_cookie(**set_cookie)
    return response


def openapi_exception_response(error_code, error_msg, status=422, detail=None, set_cookie=None):
    data = {
        'error_code': error_code,
        'error_message': error_msg,
        'request_id': datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:8],
        'details': detail,
    }
    logger.info(f'openapi response data: {data}')
    response = JsonResponse(data, status=status)
    if set_cookie: response.set_cookie(**set_cookie)
    return response


def streaming_response(data_iter):
    # return StreamingHttpResponse(data_iter, content_type='application/octet-stream')
    response = StreamingHttpResponse(data_iter, content_type='text/event-stream')
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    response['Cache-Control'] = 'no-cache'
    return response


def missed_key(sub_keys: dict, keys: set):
    for key in keys:
        if key not in sub_keys:
            return key


def check_keys(dict_like, keys):
    missed = missed_key(dict_like, keys)
    if missed:
        raise ValidationError('参加校验失败： %s 不存在！' % missed, 200)

    return True


def extract_json(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, request_data=_extract_json(request), **kwargs)

    return wrapper


def _extract_json(request):
    data = {'GET': {}, 'POST': {}, 'JSON': {}}
    settings.REQUEST_ID = request.id
    settings.NO_REQUEST_ID = request.id
    try:
        # 简单点只支持一个值
        # https://docs.djangoproject.com/en/3.0/ref/request-response/#django.http.QueryDict.dict  # noqa
        if request.method == 'GET':
            pass
        elif request.method in ['POST', 'DELETE', 'PUT']:
            data['POST'] = request.POST.dict()
        data['GET'] = get_query(request)

    except Exception:  # noqa
        logger.exception('get request data error')
    # 考虑 request.body的各种异常
    # 1 文件上传的时候抛异常：You cannot access body after reading from request's data stream
    # 2 content_type != 'application/json'  抛异常： Expecting value: line 1 column 1 (char 0)
    # 3 GET 请求 抛异常： Expecting value: line 1 column 1 (char 0)
    if request.method != 'GET' and not request.FILES and request.content_type.find('application/json') != -1:
        try:
            body_data = json.loads(request.body)
            data['JSON'] = body_data
        except Exception:  # noqa
            logger.exception('load request.body error')
    logger.info(f"request_data: {data}")
    return data


def respond(content=None, status=200, response_class=HttpResponse):
    if content is None:
        content = ''
    return response_class(content, status=status)


def respond_json(content, status=200):
    return respond(content or {}, status, JsonResponse)


def wrap_api_errors(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except APIError as err:
            resp = {'message': err.message}  # noqa: B306
            if err.details:
                resp['errors'] = err.details
            return respond_json(resp, err.status)

    return wrapper


class ServerSentEventRenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data