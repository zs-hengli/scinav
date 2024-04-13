import logging

from django.conf import settings

from authing.v2.management import ManagementClient, ManagementClientOptions
from authing.v2.authentication import (AuthenticationClient, AuthenticationClientOptions)


logger = logging.Logger(__name__)


def get_manage_client():
    return ManagementClient(
        options=ManagementClientOptions(
            user_pool_id='',
            secret='',
            host='',
        )
    )


def get_auth_client():
    return AuthenticationClient(
        options=AuthenticationClientOptions(
            app_id=settings.AUTHING_APP_ID,
            secret=settings.AUTHING_APP_SECRET,
            app_host=settings.AUTHING_APP_HOST,
            # redirect_uri=settings.AUTHING_APP_REDIRECT_URI,
        )
    )


def auth_code_to_token(code):
    client = get_auth_client()
    token_info = client.get_access_token_by_code(code)
    logger.debug(f'auth_code_to_token token_info: {token_info}')
    return token_info


def get_user_by_token(token):
    client = get_auth_client()
    user_info = client.get_current_user(token)
    logger.debug(f'user_by_token user_info: {user_info}')
    return user_info


def get_user_by_access_token(access_token):
    client = get_auth_client()
    user_info = client.get_user_info_by_access_token(access_token)
    logger.debug(f'auth_by_token user_info: {user_info}')
    return user_info


def get_user_by_id_token(id_token):
    client = get_auth_client()
    user_info = client.validate_token(id_token)
    logger.debug(f'get_user_by_id_token user_info: {user_info}')
    return user_info