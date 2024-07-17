import json
import logging
import os
import time

import binascii

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from openapi.models import OpenapiKey
from user.authing_service import get_user_by_id_token
from user.models import MyUser
from user.service import save_auth_user_info
from vip.base_service import tokens_award
from vip.models import TokensHistory

logger = logging.getLogger(__name__)


class MyAuthentication(BaseAuthentication):

    def authenticate(self, request):
        path = request.path
        if path.startswith('/api/v1'):
            user, token = check_token(request)
        elif path.startswith('/openapi/v1'):
            user, _ = check_openapi_key(request)
        elif path.startswith('/api/admin'):
            user, _ = check_admin_token(request)
        else:
            user = None
        if user:
            return user, None


def check_token(request):
    token = request.headers.get('Authorization')
    if token:
        logger.debug(f'token: {token}')
        user_info = get_user_by_id_token(id_token=token)
        logger.debug(f'user_info: {user_info}')
        if user_info and user_info.get('sub') and time.time() < user_info['exp']:
            if user := _get_my_user(user_info['sub']):
                if (
                    user.email != user_info['email']
                    or user.phone != user_info['phone_number']
                    or user.nickname != user_info['nickname']
                    # or user.avatar != user_info['picture']
                ):
                    user = save_auth_user_info(user_info)
            else:
                # invite register and new user award
                user = save_auth_user_info(user_info)
                invite_code = request.COOKIES.get('X-INVITE-CODE')
                if invite_code:
                    tokens_award(user_id=invite_code, award_type=TokensHistory.Type.INVITE_REGISTER)
                tokens_award(user_id=user.id, award_type=TokensHistory.Type.NEW_USER_AWARD)
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
        if not (openapi := _get_openapi_key(openapi_key_id)):
            logger.info(f"not found openapi_key record by api_key: {openapi_key}")
            return None, False
        user = _get_my_user(openapi.user_id)
        check_res = OpenapiKey.key_check(openapi.api_key, openapi_key)
        if not user or not check_res:
            logger.warning(f'Invalid access_token, request.headers: {request.headers}')
            raise exceptions.AuthenticationFailed(gettext_lazy('Invalid access_token.'))
        return user, openapi.id
    else:
        logger.info(f'no X-API-KEY in headers, headers: {request.headers}')
    return None, False


def check_admin_token(request):
    token = request.headers.get('Authorization')
    api_key = request.headers.get('X-ADMIN-API-KEY')
    if api_key:
        logger.debug(f'api_key: {api_key}')
        if api_key == settings.ADMIN_API_KEY:
            user = MyUser(
                id=api_key[:36],
                username=api_key[:150],
                email='admin@example.com',
                phone='12345678900',
                nickname='admin',
                is_superuser=True,
                is_staff=True,
                is_active=True,
            )
            return user, api_key
        else:
            logger.warning(f'Invalid access_token., request.headers: {request.headers}')
            raise exceptions.AuthenticationFailed(gettext_lazy('Invalid access_token.'))
    elif token:
        return check_token(request)
    else:
        return None, None


def _get_my_user(user_id) -> MyUser | None:
    user_info_key = f'scinav:auth:user_info:{user_id}'
    user = cache.get(user_info_key)
    expire = 86400 * 2
    if not user:
        user = MyUser.objects.filter(id=user_id).first()
        if user:
            cache.set(user_info_key, user, expire)
    else:
        cache.expire(user_info_key, expire)
    return user


def _get_openapi_key(openapi_key_id) -> OpenapiKey | None:
    redis_key = f'scinav:auth:openapi_key_info:{openapi_key_id}'
    openapi = cache.get(redis_key)
    expire = 86400 * 2
    if not openapi:
        openapi = OpenapiKey.objects.filter(pk=openapi_key_id, del_flag=False).first()
        if openapi:
            cache.set(redis_key, openapi, expire)
    else:
        cache.expire(redis_key, expire)
    return openapi


def generate_token():
    """
    生成唯一token
    示例：b8f216af64963ac338f21bccf6b9eeca613b24e7
    :return:
    """
    return binascii.hexlify(os.urandom(20)).decode()


def del_auth_cache(user_id):
    user_info_key = f'scinav:auth:user_info:{user_id}'
    cache.delete(user_info_key)