import json
import logging

from django.conf import settings
from wechatpayv3 import WeChatPay, WeChatPayType

logger = logging.getLogger(__name__)

wechat_pay_config = {
    'wechatpay_type': WeChatPayType.NATIVE,
    'mchid': settings.WEIXIN_PAY_MCHID,
    'private_key': settings.WEIXIN_PAY_MCH_PRIVATE_KEY,
    'cert_serial_no': settings.WEIXIN_PAY_MCH_CERT_SERIAL_NO,
    'apiv3_key': settings.WEIXIN_PAY_APIV3_KEY,
    'appid': settings.WEIXIN_PAY_APPID,
    'notify_url': settings.WEIXIN_PAY_NOTIFY_URL,
    'cert_dir': '.cache/cert',  # 微信支付平台证书缓存目录，减少证书下载调用次数，首次使用确保此目录为空目录.
    'logger': logger,
    'partner_mode': False,  # 接入模式:False=直连商户模式，True=服务商模式
    'proxy': None,
    'timeout': (10, 30)  # 建立连接最大超时时间是10s，读取响应的最大超时时间是30s
}
logger.debug(f"wechat pay config: {wechat_pay_config}")
wxpay = WeChatPay(**wechat_pay_config)


def native_pay(out_trade_no, description, amount):
    # 以native下单为例，下单成功后即可获取到'code_url'，将'code_url'转换为二维码，并用微信扫码即可进行支付测试。
    #  200, '{"code_url":"weixin://wxpay/bizpayurl?pr=xv8DZTCz3"}'
    code, message = wxpay.pay(
        description=description,
        out_trade_no=out_trade_no,
        amount={'total': amount},
        pay_type=WeChatPayType.NATIVE
    )
    data = {}
    if code == 200:
        data = json.loads(message)
    return code, message, data


def pay_status(out_trade_no=None, transaction_id=None):
    """
    :param out_trade_no:
    :param transaction_id:
    :return:
        trade_state:
            SUCCESS：支付成功
            REFUND：转入退款
            NOTPAY：未支付
            CLOSED：已关闭
    """
    code, msg = wxpay.query(mchid=settings.WEIXIN_PAY_MCHID, out_trade_no=out_trade_no, transaction_id=transaction_id)
    if code == 200:
        data = json.loads(msg)
    else:
        logger.warning(f"query pay status error:{msg}, code: {code}")
        data = {}
    return data


def weixin_notify(request):
    headers = {
        'Wechatpay-Signature': request.META.get('HTTP_WECHATPAY_SIGNATURE'),
        'Wechatpay-Timestamp': request.META.get('HTTP_WECHATPAY_TIMESTAMP'),
        'Wechatpay-Nonce': request.META.get('HTTP_WECHATPAY_NONCE'),
        'Wechatpay-Serial': request.META.get('HTTP_WECHATPAY_SERIAL')
    }
    result = wxpay.callback(headers=headers, body=request.body)
    if result and result.get('event_type') == 'TRANSACTION.SUCCESS':
        logger.info(f"weixin pay notify success:{result}")
        resp = result.get('resource')
        data = {
            'appid': resp.get('appid'),
            'mchid': resp.get('mchid'),
            'out_trade_no': resp.get('out_trade_no'),
            'transaction_id': resp.get('transaction_id'),
            'trade_type': resp.get('trade_type'),
            'trade_state': resp.get('trade_state'),
            'trade_state_desc': resp.get('trade_state_desc'),
            'bank_type': resp.get('bank_type'),
            'attach': resp.get('attach'),
            'success_time': resp.get('success_time'),
            'payer': resp.get('payer'),
            'amount': resp.get('amount').get('total'),
        }
        return data
    else:
        logger.warning(f"weixin pay notify failed:{result}, headers:{headers}, request_data:{request.body}")
        return False