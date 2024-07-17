import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.views import APIView

from core.utils.authentication import del_auth_cache
from core.utils.views import extract_json, my_json_response
from customadmin.models import GlobalConfig
from customadmin.serializers import GlobalConfigPostQuerySerializer, MembersQuerySerializer, \
    MembersAwardQuerySerializer, UpdateMembersQuerySerializer, MembersTradesQuerySerializer
from customadmin.service import get_global_configs, set_global_configs, get_members, members_admin_award, \
    update_member_vip, get_trades
from user.models import MyUser
from vip.models import Member

logger = logging.getLogger(__name__)


class IsAdminUser(BasePermission):
    """
    Allows access only to superusers.
    """
    def has_permission(self, request, view=None):
        logger.debug(f'dddddddd IsAdminUser {request.user}')
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
        data = get_trades(vd['keyword'], vd['page_size'], vd['page_num'])

        return my_json_response(data)