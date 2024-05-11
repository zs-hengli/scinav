"""This file and its contents are licensed under the Apache License 2.0.
Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
import datetime
import logging
import sys
import traceback as tb
import uuid

from django.conf import settings
from django.utils.encoding import force_str
from rest_framework import status as rfd_status
from rest_framework.exceptions import APIException
from rest_framework.views import Response, exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """ Make custom exception treatment in RestFramework

    :param exc: Exception - you can check specific exception
    :param context: context
    :return: response with error msg
    """
    exception_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:8]
    logger.error(f'{exception_id} {exc})', exc_info=True)

    # error body structure
    exception_type = exc.exception_type if hasattr(exc, 'exception_type') else ''
    response_data = {
        'code': 100000,
        'msg': f"{exception_type}:{str(exc)}",
        'data': {},
        'validation_errors': {},
        'request_id': exception_id,
    }
    # try rest framework handler
    response = exception_handler(exc, context)
    if response is not None:
        response_data['code'] = exc.status if getattr(exc, 'status', None) else exc.status_code
        if 'detail' in response.data and 'code' in response.data:
            response_data['msg'] = f"{response.data['code']}: {response.data['detail']}"
        response_data['validation_errors'] = response.data \
            if isinstance(response.data, dict) \
            else {'non_field_errors': response.data}
        response.data = response_data

    # non-standard exception
    else:
        # if sentry_sdk_loaded:
        #     # pass exception to sentry
        #     set_tag('exception_id', exception_id)
        #     capture_exception(exc)

        exc_tb = tb.format_exc()
        logger.debug(exc_tb)
        if not settings.DEBUG_MODAL_EXCEPTIONS:
            exc_tb = 'Tracebacks disabled in settings'
        response_data['validation_errors'] = exc_tb
        response = Response(status=rfd_status.HTTP_500_INTERNAL_SERVER_ERROR, data=response_data)

    return response


class APIError(BaseException):
    def __init__(self, message, status=rfd_status.HTTP_403_FORBIDDEN, details=None):
        self.message = message
        self.status_code = status
        self.status = status
        self.details = details


class MyAPIException(APIException):
    # exception_type = ''
    # status = rfd_status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail=None, exception_type='', status=rfd_status.HTTP_500_INTERNAL_SERVER_ERROR):
        # print(f'MyAPIException __init__: {detail}, {exception_type}, {status}')
        self.exception_type = exception_type
        self.status_code = status
        self.status = rfd_status.HTTP_403_FORBIDDEN
        self.detail = detail


class ValidationError(MyAPIException):
    status_code = rfd_status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid input.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_400_BAD_REQUEST):
        detail = {'detail': detail, 'code': self.exception_type}
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class ParseError(MyAPIException):
    status_code = rfd_status.HTTP_400_BAD_REQUEST
    default_detail = 'Malformed request.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_400_BAD_REQUEST):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class AuthenticationFailed(MyAPIException):
    status_code = rfd_status.HTTP_401_UNAUTHORIZED
    default_detail = 'Incorrect authentication credentials.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_401_UNAUTHORIZED):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class NotAuthenticated(MyAPIException):
    status_code = rfd_status.HTTP_401_UNAUTHORIZED
    default_detail = 'Authentication credentials were not provided.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_401_UNAUTHORIZED):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class PermissionDenied(MyAPIException):
    status_code = rfd_status.HTTP_403_FORBIDDEN
    default_detail = 'You do not have permission to perform this action.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_403_FORBIDDEN):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class NotFound(MyAPIException):
    status_code = rfd_status.HTTP_404_NOT_FOUND
    default_detail = 'Not found.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_404_NOT_FOUND):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class MethodNotAllowed(MyAPIException):
    status_code = rfd_status.HTTP_405_METHOD_NOT_ALLOWED
    default_detail = 'Method "{method}" not allowed.'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, method, detail=None, status=rfd_status.HTTP_405_METHOD_NOT_ALLOWED):
        if detail is None:
            detail = force_str(self.default_detail).format(method=method)
        super().__init__(detail, self.exception_type, status)


class PreconditionFailed(MyAPIException):
    """
    前提条件校验失败
    """
    default_detail = 'Precondition failed'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_400_BAD_REQUEST):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)


class InternalServerError(MyAPIException):
    """
    服务器内部错误，无法完成请求
    """
    status_code = rfd_status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'Internal Server Error'
    exception_type = sys._getframe().f_code.co_name

    def __init__(self, detail=None, status=rfd_status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(detail if detail else self.default_detail, self.exception_type, status)
