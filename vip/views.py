import datetime
import logging
import uuid

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.common import get_client_ip
from core.utils.views import extract_json, my_json_response
from vip.base_service import tokens_award, daily_duration_award, MemberTimeClock
from vip.models import Pay
from vip.serializers import PayQrcodeQuerySerializer, ExchangeQuerySerializer, TradesQuerySerializer, \
    TokensAwardQuerySerializer
from vip.service import generate_pay_qrcode, pay_notify, get_member_info, tokens_expire_list, exchange_member, \
    tokens_history_list, pay_trade_state, generate_pay_h5_url, format_history_list

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'index'}
        daily_duration_award()
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class Members(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        data = get_member_info(request.user.id)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class PayQrcode(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        # code, message, data = native_pay(out_trade_no=out_trade_no, description='支付测试', amount=1)
        serial = PayQrcodeQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=10001, msg='参数错误')
        vd = serial.validated_data
        if not vd['out_trade_no']:
            vd['out_trade_no'] = str(uuid.uuid4())[10:]
        img = generate_pay_qrcode(request.user.id, vd['out_trade_no'], vd['description'], vd['amount'])
        if not img:
            return my_json_response(code=100000, msg='系统错误，请联系管理员')
        return my_json_response(img)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class PayH5(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        # code, message, data = native_pay(out_trade_no=out_trade_no, description='支付测试', amount=1)
        serial = PayQrcodeQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=10001, msg='参数错误')
        client_ip = get_client_ip(request)
        vd = serial.validated_data
        if not vd['out_trade_no']:
            vd['out_trade_no'] = str(uuid.uuid4())[10:]
        h5_url = generate_pay_h5_url(request.user.id, vd['out_trade_no'], vd['description'], vd['amount'], client_ip)
        if not h5_url:
            return my_json_response(code=100000, msg='系统错误，请联系管理员')
        return my_json_response(h5_url)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class WeixinNotify(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        res = pay_notify(request)
        if res:
            return JsonResponse({'code': 'SUCCESS', 'message': '成功'})
        else:
            return JsonResponse({'code': 'FAIL', 'message': '失败'}, status=400)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class PayStatus(APIView):

    def get(self, request, out_trade_no, *args, **kwargs):  # noqa
        pay = Pay.objects.filter(out_trade_no=out_trade_no).first()
        if not pay:
            return my_json_response(code=100001, msg='pay trade not exist')
        data = pay_trade_state(out_trade_no, pay)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class TokensExpire(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        data = tokens_expire_list(request.user.id)
        return my_json_response({'list': data})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class Exchange(APIView):

    def post(self, request, *args, **kwargs):  # noqa
        post_data = request.data
        serial = ExchangeQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        code, msg, data = exchange_member(request.user.id, vd['member_type'], vd['duration'])
        return my_json_response(data, code=code, msg=msg)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class Trades(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        user_id = request.user.id
        query = request.query_params.dict()
        serial = TradesQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        clock_time = MemberTimeClock.get_member_time_clock(user_id)
        if clock_time:
            today = clock_time.date()
        else:
            today = datetime.date.today()
        total, histories = tokens_history_list(user_id, vd['status'], vd['page_size'], vd['page_num'], today)
        # histories = TokensHistoryListSerializer(histories, many=True).data
        histories = format_history_list(user_id, histories)
        data = {
            'list': histories,
            'total': total,
        }
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class TokensAward(APIView):

    def post(self, request, *args, **kwargs):  # noqa
        post_data = request.data
        serial = TokensAwardQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = tokens_award(request.user.id, vd['award_type'], vd['amount'], vd['bot_id'])
        return my_json_response(data)
