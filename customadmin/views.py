import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.views import APIView

from bot.models import Bot, HotBot
from bot.serializers import HotBotListSerializer
from bot.service import bot_publish, add_hot_bot
from core.utils.authentication import del_auth_cache
from core.utils.views import extract_json, my_json_response
from customadmin.models import GlobalConfig, Notification
from customadmin.serializers import GlobalConfigPostQuerySerializer, MembersQuerySerializer, \
    MembersAwardQuerySerializer, UpdateMembersQuerySerializer, MembersTradesQuerySerializer, \
    BotsUpdateOrderQuerySerializer, BotsPublishQuerySerializer, BotsPublishListRespSerializer, \
    MembersClockUpdateQuerySerializer, NoticesQuerySerializer, NoticesCreateSerializer, NoticesUpdateSerializer, \
    NoticesDetailSerializer, NoticesActiveSerializer
from customadmin.service import get_global_configs, set_global_configs, get_members, members_admin_award, \
    update_member_vip, get_trades, bots_publish_list, update_bots_publish_order, update_bots_hot_order, hot_bots_list, \
    Notice
from user.models import MyUser
from vip.base_service import MemberTimeClock
from vip.models import Member

logger = logging.getLogger(__name__)


class IsAdminUser(BasePermission):
    """
    Allows access only to superusers.
    """
    def has_permission(self, request, view=None):
        return bool(request.user and request.user.is_superuser)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'admin index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT', 'POST', 'DELETE']), name='dispatch')
@permission_classes([IsAdminUser])
class BotDetail(APIView):

    @staticmethod
    def get(request, bot_id, *args, **kwargs):  # noqa
        bot = Bot.objects.filter(id=bot_id).first()
        if not bot:
            return my_json_response(code=190001, msg=f'参数错误：此专题不存在')
        return my_json_response(BotsPublishListRespSerializer(bot).data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT', 'POST', 'DELETE']), name='dispatch')
@permission_classes([IsAdminUser])
class BotsPublish(APIView):

    @staticmethod
    def get(request, *args, **kwargs):  # noqa
        bots = bots_publish_list()
        return my_json_response({'list': bots})

    @staticmethod
    def put(request, *args, **kwargs):
        post_data = request.data
        serial = BotsUpdateOrderQuerySerializer(data=post_data, many=True)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        update_bots_publish_order(serial.validated_data)
        return my_json_response({})

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        serial = BotsUpdateOrderQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        code, msg, data = bot_publish(vd['bot_id'], vd['order'])
        return my_json_response(data, code=code, msg=msg)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        code, msg, data = bot_publish(bot_id, 0, action=Bot.TypeChoices.PERSONAL)
        return my_json_response({}, code=code, msg=msg)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT', 'POST', 'DELETE']), name='dispatch')
@permission_classes([IsAdminUser])
class BotsHot(APIView):

    @staticmethod
    def get(request, *args, **kwargs):  # noqa
        bots = hot_bots_list()
        return my_json_response({'list': bots})

    @staticmethod
    def put(request, *args, **kwargs):
        post_data = request.data
        serial = BotsUpdateOrderQuerySerializer(data=post_data, many=True)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error')
        update_bots_hot_order(serial.validated_data)
        return my_json_response({})

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        serial = BotsUpdateOrderQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error')
        vd = serial.validated_data
        hot_bot = add_hot_bot(vd['bot_id'], vd['order'])
        return my_json_response(HotBotListSerializer(hot_bot).data)

    @staticmethod
    def delete(request, bot_id, *args, **kwargs):
        hot_bot = HotBot.objects.filter(bot_id=bot_id).first()
        if not hot_bot:
            return my_json_response(code=100002, msg='hot_bot not found')
        hot_bot.del_flag = True
        hot_bot.save()
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
@permission_classes([IsAdminUser])
class SuperUser(APIView):

    @staticmethod
    def put(request, user_id, is_superuser=1, *args, **kwargs):
        user = MyUser.objects.filter(id=user_id).first()
        if not user:
            return my_json_response(code=100001, msg=f'user {user_id} not found')
        user.is_superuser = True if int(is_superuser) else False
        user.save()
        del_auth_cache(user_id)
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
# @permission_classes([IsAdminUser])
class GlobalConfigs(APIView):
    permission_classes = {"post": [IsAdminUser], "get": [IsAuthenticated]}

    def get_permissions(self):
        # Instances and returns the dict of permissions that the view requires.
        return {key: [permission() for permission in permissions] for key, permissions in self.permission_classes.items()}

    def check_permissions(self, request):
        # Gets the request method and the permissions dict, and checks the permissions defined in the key matching
        method = request.method.lower()
        for permission in self.get_permissions()[method]:
            if not permission.has_permission(request, self):
                self.permission_denied(
                    request, message=getattr(permission, 'message', None)
                )

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()

        if query.get('config_types'):
            config_types = query['config_types'].split(',')
        else:
            config_types = [
                GlobalConfig.ConfigType.MEMBER_FREE,
                GlobalConfig.ConfigType.MEMBER_STANDARD,
                GlobalConfig.ConfigType.MEMBER_PREMIUM,
                GlobalConfig.ConfigType.VIP,
                GlobalConfig.ConfigType.AWARD
            ]
        data = get_global_configs(config_types)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = GlobalConfigPostQuerySerializer(data=query, many=True)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error')
        date = set_global_configs(request.user.id, serial.validated_data)
        return my_json_response(date)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT']), name='dispatch')
@permission_classes([IsAdminUser])
class Members(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = MembersQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = get_members(vd['keyword'], vd['page_size'], vd['page_num'])

        return my_json_response(data)

    @staticmethod
    def put(request, *args, **kwargs):
        post_data = request.data
        serial = UpdateMembersQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        user = MyUser.objects.filter(id=vd['user_id']).first()
        if not user:
            return my_json_response({'user_id': 'user not found'}, code=100001, msg=f'user not found')
        member = Member.objects.filter(user_id=vd['user_id']).first()
        if not member:
            member = Member.objects.create(user=user)
        if vd['is_vip'] is not None:
            update_member_vip(member, request.user.id, vd['is_vip'])
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
@permission_classes([IsAdminUser])
class MembersAward(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        serial = MembersAwardQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        user = MyUser.objects.filter(id=vd['user_id']).first()
        if not user:
            return my_json_response({'user_id': 'user not found'}, code=100001, msg=f'user not found')
        member = Member.objects.filter(user_id=vd['user_id']).first()
        if not member:
            member = Member.objects.create(user=user)
        data = members_admin_award(member, vd['amount'], vd['period_of_validity'], request.user.id)

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([IsAdminUser])
class MembersTrades(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        serial = MembersTradesQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        if vd['types']:
            vd['types'] = vd['types'].split(',') if isinstance(vd['types'], str) else vd['types']
        data = get_trades(vd['keyword'], vd['types'], vd['page_size'], vd['page_num'])

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'DELETE']), name='dispatch')
@permission_classes([IsAdminUser])
class MembersClock(APIView):

    @staticmethod
    def get(request, *args, **kwargs):
        users_clock = MemberTimeClock.get_member_time_clock()
        if users_clock:
            for user_id, clock_time in users_clock.items():
                users_clock[user_id] = clock_time.strftime('%Y-%m-%d %H:%M:%S')
        return my_json_response(users_clock)

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        serial = MembersClockUpdateQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        code, msg = MemberTimeClock.update_member_time_clock(vd['user_id'], vd['clock_time'])
        return my_json_response(code=code, msg=msg)

    @staticmethod
    def delete(request, user_id, *args, **kwargs):
        code, msg = MemberTimeClock.init_member_time_clock(user_id)
        return my_json_response(code=code, msg=msg)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([IsAdminUser])
class MembersClockExpireAward(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        MemberTimeClock.daily_expire_clock_duration_award()
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST', 'DELETE', 'PUT']), name='dispatch')
@permission_classes([IsAdminUser])
class Notices(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query_data = request.query_params.dict()
        serial = NoticesQuerySerializer(data=query_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = Notice.get_notices(vd['page_size'], vd['page_num'])
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        post_data = request.data
        serial = NoticesCreateSerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        data = Notice.create_notice(serial.validated_data, request.user.id)
        data = NoticesDetailSerializer(data).data
        return my_json_response(data)

    @staticmethod
    def put(request, notice_id, *args, **kwargs):
        post_data = request.data
        notice_id = int(notice_id)
        notice = Notification.objects.filter(id=notice_id).first()
        if not notice:
            return my_json_response(code=100001, msg=f'notice not found by id {notice_id}')
        serial = NoticesUpdateSerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        data = Notice.update_notice(notice, admin_id=request.user.id, **serial.validated_data)
        data = NoticesDetailSerializer(data).data
        return my_json_response(data)

    @staticmethod
    def delete(request, notice_id, *args, **kwargs):
        notice_id = int(notice_id)
        notice = Notification.objects.filter(id=notice_id).first()
        if not notice:
            return my_json_response(code=100001, msg=f'notice not found by id {notice_id}')
        notice.del_flag = True
        notice.save()
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
@permission_classes([IsAdminUser])
class NoticesActive(APIView):

    @staticmethod
    def put(request, *args, **kwargs):
        post_data = request.data
        serial = NoticesActiveSerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error {list(serial.errors.keys())}')
        vd = serial.validated_data
        notice = Notification.objects.filter(id=vd['id']).first()
        if not notice:
            return my_json_response(code=100001, msg=f'notice not found by id {serial.validated_data["id"]}')
        data = Notice.active_notice(notice, vd['is_active'], request.user.id)
        return my_json_response(data)