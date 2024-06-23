import json
import logging
import os
import time

import binascii
# from django.core.cache import cache
from django.utils.translation import gettext_lazy
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from openapi.models import OpenapiKey
from user.authing_service import get_user_by_id_token
from user.models import MyUser
from user.service import save_auth_user_info

logger = logging.getLogger(__name__)


class MyAuthentication(BaseAuthentication):

    def authenticate(self, request):
        path = request.path
        if path.startswith('/api/v1'):
            user, token = check_token(request)
            if user:
                return user, token
        if path.startswith('/openapi/v1'):
            user, _ = check_openapi_key(request)
            if user:
                return user, None


def check_token(request):
    token = request.headers.get('Authorization')
    if token:
        logger.debug(f'token: {token}')
        user_info = get_user_by_id_token(id_token=token)
        logger.debug(f'user_info: {user_info}')
        if user_info and user_info.get('sub') and time.time() < user_info['exp']:
            if user := MyUser.objects.filter(id=user_info['sub']).first():
                if (
                    user.email != user_info['email']
                    or user.phone != user_info['phone_number']
                    or user.nickname != user_info['nickname']
                    or user.avatar != user_info['picture']
                ):
                    user = save_auth_user_info(user_info)
            else:
                user = save_auth_user_info(user_info)
            return user, token
        else:
            logger.warning(f'Invalid access_token., request.headers: {request.headers}')
            raise exceptions.AuthenticationFailed(gettext_lazy('Invalid access_token.'))
    else:
        return None, None


def check_openapi_key(request):
    openapi_key = request.headers.get('X-API-KEY')
    if openapi_key:
        patt = '-'
        if openapi_key.count(patt) != 2:
            logger.info(f"openapi_key format error: {openapi_key}")
            return None, False
        _, openapi_key_id, openapi_key_str = openapi_key.split(patt)
        logger.debug(f'openapi_key: {openapi_key}')
        openapi_key_id = int(openapi_key_id)
        openapi = OpenapiKey.objects.filter(pk=openapi_key_id, del_flag=False).first()
        if not openapi:
            logger.info(f"not found openapi_key record by api_key: {openapi_key}")
            return None, False
        user = MyUser.objects.filter(pk=openapi.user_id).first()
        check_res = OpenapiKey.key_check(openapi.api_key, openapi_key)
        if not user or not check_res:
            logger.warning(f'Invalid access_token, request.headers: {request.headers}')
            raise exceptions.AuthenticationFailed(gettext_lazy('Invalid access_token.'))
        return user, openapi.id
    else:
        logger.info(f'no X-API-KEY in headers, headers: {request.headers}')
    return None, False


def generate_token():
    """
    生成唯一token
    示例：b8f216af64963ac338f21bccf6b9eeca613b24e7
    :return:
    """
    return binascii.hexlify(os.urandom(20)).decode()