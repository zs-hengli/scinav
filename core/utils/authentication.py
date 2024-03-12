import binascii
import json
import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from user.models import MyUser

logger = logging.getLogger(__name__)


class MyAuthentication(BaseAuthentication):

    def authenticate(self, request):
        token_str = request.headers.get('Authorization')
        token = None
        if token_str:
            token = token_str.lstrip('token ')
        if token is not None:
            username = self.check_token(token)
            if username is not None:
                redis_key = f'my_auth token: {token}'
                cache.set(redis_key, token, settings.AUTH_TOKEN_EXPIRES)
                return MyUser.objects.get(username=username), token
            else:
                logger.warning(f'get headers.Authorization empty, request.headers: {request.headers}')
                raise exceptions.AuthenticationFailed(gettext_lazy('Invalid token.'))

        # todo user login
        token_str = '618ddd2c4e0eda29cf74b7eb8563ba957b3227de'
        return MyUser.objects.get(username='admin'), token_str

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
