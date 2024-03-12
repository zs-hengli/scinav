import json
import logging

from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_dysmsapi20170525.client import \
    Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
# from alibabacloud_tea_console.client import Client as ConsoleClient
from alibabacloud_tea_util.client import Client as UtilClient
from django.conf import settings

logger = logging.getLogger(__name__)


template_code = {
    'signup': 'SMS_251006482',  # 您的校验码：${code}，您正在注册成为会员，感谢您的支持！
    'check': 'SMS_251015846',  # 您的验证码为：${code}，请勿泄露于他人！
    'forgot_pwd': 'SMS_250941526',  # 您的验证码为：${code}，仅用于密码找回，请勿泄露给他人！
}


class AliSms:
    def __init__(self):
        pass

    @staticmethod
    def signup(mobile: str, code: int) -> dict:
        sms_request = {
            'phone_numbers': mobile,
            'sign_name': '治数科技',
            'template_code': template_code['signup'],
            'template_param': f'{{"code":"{code}"}}',
        }
        return AliSms.send(sms_request)

    @staticmethod
    def check(mobile: str, code: int) -> dict:
        sms_request = {
            'phone_numbers': mobile,
            'sign_name': '治数科技',
            'template_code': template_code['check'],
            'template_param': f'{{"code":"{code}"}}',
        }
        return AliSms.send(sms_request)

    @staticmethod
    def forgot_pwd(mobile: str, code: int) -> dict:
        sms_request = {
            'phone_numbers': mobile,
            'sign_name': '治数科技',
            'template_code': template_code['forgot_pwd'],
            'template_param': f'{{"code":"{code}"}}',
        }
        return AliSms.send(sms_request)

    @staticmethod
    def create_client() -> Dysmsapi20170525Client:
        """
        使用AK&SK初始化账号Client
        @return: Client
        @throws Exception
        """
        config = open_api_models.Config(
            # 必填，您的 AccessKey ID,
            access_key_id=settings.ALI_SMS_ACCESS_KEY,
            # 必填，您的 AccessKey Secret,
            access_key_secret=settings.ALI_SMS_ACCESS_KEY_SECRET
        )
        # 访问的域名
        config.endpoint = 'dysmsapi.aliyuncs.com'
        return Dysmsapi20170525Client(config)

    @staticmethod
    def send(sms_request) -> dict:
        # 工程代码泄露可能会导致AccessKey泄露，并威胁账号下所有资源的安全性。以下代码示例仅供参考，建议使用更安全的 STS 方式，
        # 更多鉴权访问方式请参见：https://help.aliyun.com/document_detail/378659.html
        client = AliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(**sms_request)
        resp = UtilClient.to_jsonstring(client.send_sms(send_sms_request))
        logger.debug(resp)
        return json.loads(resp).get('body', {'Code': 'Unknown', 'Message': '未知错误'})

    @staticmethod
    def create_client_with_sts(
        access_key_id: str,
        access_key_secret: str,
        security_token: str,
    ) -> Dysmsapi20170525Client:
        """
        使用STS鉴权方式初始化账号Client，推荐此方式。本示例默认使用AK&SK方式。
        @param access_key_id:
        @param access_key_secret:
        @param security_token:
        @return: Client
        @throws Exception
        """
        config = open_api_models.Config(
            # 必填，您的 AccessKey ID,
            access_key_id=access_key_id,
            # 必填，您的 AccessKey Secret,
            access_key_secret=access_key_secret,
            # 必填，您的 Security Token,
            security_token=security_token,
            # 必填，表明使用 STS 方式,
            type='sts'
        )
        # 访问的域名
        config.endpoint = 'dysmsapi.aliyuncs.com'
        return Dysmsapi20170525Client(config)

    @staticmethod
    async def send_async(sms_request) -> None:
        # 工程代码泄露可能会导致AccessKey泄露，并威胁账号下所有资源的安全性。以下代码示例仅供参考，建议使用更安全的 STS 方式，
        # 更多鉴权访问方式请参见：https://help.aliyun.com/document_detail/378659.html
        client = AliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(**sms_request)
        runtime = util_models.RuntimeOptions()
        resp = await client.send_sms_with_options_async(send_sms_request, runtime)
        logger.debug(UtilClient.to_jsonstring(resp))


if __name__ == '__main__':
    client_main = AliSms.create_client()
    sms_request_main = {
        'phone_numbers': '18201510785',
        'sign_name': '治数科技',
        'template_code': 'SMS_251006482',
        'template_param': '{"code":"1112"}',
    }
    send_sms_request_main = dysmsapi_20170525_models.SendSmsRequest(**sms_request_main)
    resp_main = client_main.send_sms(send_sms_request_main)
    print(UtilClient.to_jsonstring(resp_main))
    logger.debug(UtilClient.to_jsonstring(resp_main))
