import json
import logging
import os
import time

import binascii
from django.core.cache import cache
from django.utils.translation import gettext_lazy
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from user.authing_service import get_user_by_id_token
from user.models import MyUser
from user.service import save_auth_user_info

logger = logging.getLogger(__name__)


class MyAuthentication(BaseAuthentication):

    def authenticate(self, request):
        token = request.headers.get('Authorization')
        if token:
            logger.debug(f'token: {token}')
            user_info = get_user_by_id_token(id_token=token)
            logger.debug(f'user_info: {user_info}')
            if user_info and user_info.get('sub') and time.time() < user_info['exp']:
                if user := MyUser.objects.filter(id=user_info['sub']).first():
                    # todo update user_info
                    pass
                else:
                    user = save_auth_user_info(user_info)
                return user, token
            else:
                logger.warning(f'get headers.Authorization empty, request.headers: {request.headers}')
                raise exceptions.AuthenticationFailed(gettext_lazy('Invalid access_token.'))

        # todo user login
        # token_str = '618ddd2c4e0eda29cf74b7eb8563ba957b3227de'
        # return MyUser.objects.get(username='admin'), token_str

    @staticmethod
    def check_token(token):
        # 模拟请求token的验证
        response = cache.get(f'check_token token: {token}')
        # response = requests.get("http://localhost:8000/check_token/" + token)
        logger.debug(f'check_token response: {response}')
        if response:
            return json.loads(response).get("username")


def generate_token():
    """
    生成唯一token
    示例：b8f216af64963ac338f21bccf6b9eeca613b24e7
    :return:
    """
    return binascii.hexlify(os.urandom(20)).decode()

