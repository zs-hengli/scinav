import datetime
import logging

from django.db import models
from rest_framework import serializers

from bot.models import Bot, HotBot
from customadmin.models import GlobalConfig, Notification
from vip.models import Member, TokensHistory
from vip.serializers import TokensHistoryListSerializer


logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class BotsPublishListRespSerializer(BaseModelSerializer):
    user_info = serializers.SerializerMethodField()
    bot_id = serializers.CharField(source='id')

    @staticmethod
    def get_user_info(obj: Bot) -> dict:
        return {
            'id': obj.user.id,
            'email': obj.user.email,
            'phone': obj.user.phone
        }

    class Meta:
        model = Bot
        fields = ['id', 'bot_id', 'title', 'order', 'user_info', 'type', 'pub_date', 'updated_at']


class BotsUpdateOrderQuerySerializer(serializers.Serializer):
    bot_id = serializers.CharField(required=True)
    order = serializers.IntegerField(required=True)


class BotsPublishQuerySerializer(serializers.Serializer):
    bot_ids = serializers.ListSerializer(child=serializers.CharField(required=True))


class HotBotAdminListSerializer(BaseModelSerializer):
    title = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    user_info = serializers.SerializerMethodField()
    pub_date = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", source='created_at')

    @staticmethod
    def get_user_info(obj: HotBot) -> dict:
        bot_user = obj.bot.user
        return {
            'id': bot_user.id,
            'email': bot_user.email,
            'phone': bot_user.phone
        }

    @staticmethod
    def get_title(obj: HotBot):
        return obj.bot.title

    @staticmethod
    def get_order(obj: HotBot):
        return obj.order_num

    class Meta:
        model = HotBot
        fields = ['bot_id', 'order', 'order_num', 'title', 'updated_at', 'created_at', 'pub_date', 'user_info',]


class ConfigValueMemberLimitCheckSerializer(serializers.Serializer):
    limit_chat_daily = serializers.IntegerField(required=True, allow_null=True)
    limit_chat_monthly = serializers.IntegerField(required=True, allow_null=True)
    limit_embedding_daily = serializers.IntegerField(required=True, allow_null=True)
    limit_embedding_monthly = serializers.IntegerField(required=True, allow_null=True)
    limit_advanced_share = serializers.IntegerField(required=False, default=0)  # 高级分享个数配置
    limit_max_file_size = serializers.IntegerField(required=False, default=0)  # 文件最大大小单位M


class ConfigValueMemberVipLimitCheckSerializer(serializers.Serializer):
    limit_advanced_share = serializers.IntegerField(required=False, default=0, allow_null=True)  # 高级分享个数配置


class ConfigValueMemberExchangeCheckSerializer(serializers.Serializer):
    days_30 = serializers.IntegerField(required=True)
    days_90 = serializers.IntegerField(required=True)
    days_360 = serializers.IntegerField(required=True)


class ConfigValueAwardCheckSerializer(serializers.Serializer):
    per = serializers.IntegerField(required=True)
    limit = serializers.IntegerField(required=True, allow_null=True)
    period_of_validity = serializers.IntegerField(required=False, default=0, allow_null=True)  # 有效期


class ConfigValueDurationAwardCheckSerializer(serializers.Serializer):
    duration = serializers.IntegerField(required=True, allow_null=True)
    per = serializers.IntegerField(required=True, allow_null=True)
    period_of_validity = serializers.IntegerField(required=False, default=0, allow_null=True)  # 有效期


class GlobalConfigPostQuerySerializer(serializers.Serializer):
    id = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    config_type = serializers.ChoiceField(required=False, choices=GlobalConfig.ConfigType)
    sub_type = serializers.ChoiceField(required=False, choices=GlobalConfig.SubType)
    value = serializers.JSONField(required=False)
    order = serializers.IntegerField(required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('config_type') and attrs.get('config_type') in [
            GlobalConfig.ConfigType.MEMBER_FREE, GlobalConfig.ConfigType.MEMBER_STANDARD,
            GlobalConfig.ConfigType.MEMBER_PREMIUM
        ]:
            if not attrs.get('sub_type') or attrs.get('sub_type') not in [
                GlobalConfig.SubType.LIMIT, GlobalConfig.SubType.EXCHANGE
            ]:
                raise serializers.ValidationError('sub_type is invalid must in [limit, exchange]')
            if attrs['sub_type'] == GlobalConfig.SubType.LIMIT:
                value_serial = ConfigValueMemberLimitCheckSerializer(data=attrs.get('value'))
            else:
                value_serial = ConfigValueMemberExchangeCheckSerializer(data=attrs.get('value'))
            if not value_serial.is_valid():
                raise serializers.ValidationError(value_serial.errors)

        # award
        if attrs.get('config_type') and attrs.get('config_type') == GlobalConfig.ConfigType.AWARD:
            if not attrs.get('sub_type') or attrs.get('sub_type') not in [
                GlobalConfig.SubType.SUBSCRIBED_BOT, GlobalConfig.SubType.INVITE_REGISTER,
                GlobalConfig.SubType.NEW_USER_AWARD, GlobalConfig.SubType.DURATION
            ]:
                raise serializers.ValidationError({
                    'sub_type': 'award config sub_type is invalid must in [subscribed_bot, invite_register, '
                                'new_user_award, duration_award]'
                })
            if attrs.get('sub_type') == GlobalConfig.SubType.DURATION:
                award_serial = ConfigValueDurationAwardCheckSerializer(data=attrs.get('value'))
                if not award_serial.is_valid():
                    errors = award_serial.errors
                    errors[f'{GlobalConfig.SubType.DURATION}.value'] = \
                        f'check error'
                    raise serializers.ValidationError(errors)
            else:
                award_serial = ConfigValueAwardCheckSerializer(data=attrs.get('value'))
                if not award_serial.is_valid():
                    raise serializers.ValidationError(award_serial.errors)
        return attrs


class GlobalConfigDetailSerializer(BaseModelSerializer):

    class Meta:
        model = GlobalConfig
        fields = ['id', 'name', 'config_type', 'sub_type', 'value', 'order', 'updated_at', 'created_at']


class MembersQuerySerializer(serializers.Serializer):
    keyword = serializers.CharField(required=False, allow_null=True, default=None, allow_blank=True)
    page_size = serializers.IntegerField(required=False, default=10)
    page_num = serializers.IntegerField(required=False, default=1)


class UpdateMembersQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    is_vip = serializers.BooleanField(default=None)


class MembersListSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    user_id = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True)
    is_vip = serializers.BooleanField(required=True)
    email = serializers.CharField(required=True, allow_null=True)
    phone = serializers.CharField(required=True, allow_null=True)
    premium_end_date = serializers.DateField(required=True, allow_null=True)
    standard_end_date = serializers.DateField(required=True, allow_null=True)
    member_type = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(required=True, format='%Y-%m-%d %H:%M:%S')

    @staticmethod
    def get_member_type(obj, today=None):
        if not today:
            today = datetime.date.today()
        if obj['is_vip']:
            member_type = Member.Type.VIP
        elif obj['premium_end_date'] and obj['premium_end_date'] >= today:
            member_type = Member.Type.PREMIUM
        elif obj['standard_end_date'] and obj['standard_end_date'] >= today:
            member_type = Member.Type.STANDARD
        else:
            member_type = Member.Type.FREE
        return member_type


class MembersAwardQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True)
    period_of_validity = serializers.IntegerField(allow_null=True, default=None)


class MembersTradesQuerySerializer(serializers.Serializer):
    class Type(models.TextChoices):
        WXPAY = 'wxpay'
        AWARD = 'award'
        EXCHANGE = 'exchange'
    keyword = serializers.CharField(required=False, allow_null=True, default=None, allow_blank=True)
    types = serializers.CharField(required=False, default=None, allow_blank=True)
    page_size = serializers.IntegerField(required=False, default=10)
    page_num = serializers.IntegerField(required=False, default=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('types'):
            types = attrs.get('types').split(',')
            choices = [c[0] for c in self.Type.choices]
            for t in types:
                if t not in choices:
                    raise serializers.ValidationError(f'{t} is invalid must in {choices}')
        return attrs


class TokensHistoryAdminListSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    trade_no = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True)
    type = serializers.ChoiceField(choices=TokensHistory.Type)
    pay_amount = serializers.IntegerField(required=True, allow_null=True)
    used_info = serializers.SerializerMethodField()
    status_desc = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')
    user_id = serializers.CharField()
    email = serializers.CharField(allow_null=True, default=None)
    phone = serializers.CharField(allow_null=True, default=None)

    @staticmethod
    def get_used_info(obj):
        data = {}
        if obj['type'] in TokensHistory.TYPE_EXCHANGE:
            if obj['status'] == TokensHistory.Status.FREEZING:
                if not obj['freezing_date'] or obj['freezing_date'] < obj['start_date']:
                    data['remain_days'] = (obj['end_date'] - obj['start_date']).days + 1
                else:
                    data['remain_days'] = (obj['end_date'] - obj['freezing_date']).days + 1
            elif obj['end_date'] >= datetime.date.today():
                data['remain_days'] = (obj['end_date'] - datetime.date.today()).days + 1
            else:
                data['end_date'] = obj['end_date']
        elif obj['end_date']:
            data['end_date'] = obj['end_date']
        return data

    @staticmethod
    def get_status_desc(obj):
        status_map = {
            0: 'deleted',
            2: 'completed',
            3: 'in_progress',
            4: 'freezing',
        }
        return status_map.get(obj['status'], 'completed')


class MembersClockUpdateQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    clock_time = serializers.DateTimeField(required=True)


class NoticesQuerySerializer(serializers.Serializer):
    page_num = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=10)


class NoticesDetailSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = Notification
        fields = ['id', 'title', 'content', 'en_title', 'en_content', 'is_active', 'created_at']


class NoticesCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, allow_blank=True)
    content = serializers.CharField(required=True, allow_blank=True)
    en_title = serializers.CharField(required=True, allow_blank=True)
    en_content = serializers.CharField(required=True, allow_blank=True)
    is_active = serializers.BooleanField(default=True)


class NoticesUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False)
    content = serializers.CharField(required=False)
    en_title = serializers.CharField(required=False)
    en_content = serializers.CharField(required=False)


class NoticesActiveSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    is_active = serializers.BooleanField(default=True)