import logging
import uuid

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import extract_json, my_json_response
from vip.pay.wxpay import weixin_notify, native_pay, wxpay, pay_status

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'user index'}
        out_trade_no = 'e08-4b02-a8ac-b7b5694042e0'
        data = pay_status(out_trade_no)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class Pay(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        out_trade_no = str(uuid.uuid4())[10:]
        code, message, data = native_pay(out_trade_no=out_trade_no, description='支付测试', amount=1)
        logger.info(f'native_pay: {data}')
        return my_json_response(data, code=code, msg=message)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class WeixinNotify(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        data = weixin_notify(request)
        logger.info(f'weixin_notify: {data}')
        if data:
            return JsonResponse({'code': 'SUCCESS', 'message': '成功'})
        else:
            return JsonResponse({'code': 'FAIL', 'message': '失败'}, status=400)
