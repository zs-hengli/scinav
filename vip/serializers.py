import datetime
import logging

from django.db import models
from rest_framework import serializers

from django.utils.translation import gettext_lazy as _

from customadmin.models import GlobalConfig
from vip.models import TokensHistory, Member, MemberUsageLog


logger = logging.getLogger(__name__)


# generate_pay_qrcode
class PayQrcodeQuerySerializer(serializers.Serializer):
    out_trade_no = serializers.CharField(required=False, default=None)
    description = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True)


class MemberInfoSerializer(serializers.Serializer):
    """
    member  账户信息
        余额
        账户类型 剩余天数
        问题使用量
        文件解析量
    """

    class Type(models.TextChoices):
        FREE = 'member_free', _('member_free')
        STANDARD = 'member_standard', _('member_standard')
        PREMIUM = 'member_premium', _('member_premium')
        VIP = 'vip', _('vip')

    amount = serializers.IntegerField(default=0)
    member_type = serializers.ChoiceField(choices=Type, default=Type.FREE)
    expire_days = serializers.IntegerField(allow_null=True, default=None)
    chat_used_day = serializers.IntegerField(allow_null=True, default=None)
    limit_chat_daily = serializers.IntegerField(allow_null=True, default=None)
    embedding_used_month = serializers.IntegerField(allow_null=True, default=None)
    limit_embedding_monthly = serializers.IntegerField(allow_null=True, default=None)

    @staticmethod
    def get_member_type(member: Member | None):
        if not member:
            member_type = MemberInfoSerializer.Type.FREE
        elif member.is_vip:
            member_type = MemberInfoSerializer.Type.VIP
        elif member.premium_end_date and member.premium_end_date > datetime.date.today():
            member_type = MemberInfoSerializer.Type.PREMIUM
        elif member.standard_end_date and member.standard_end_date > datetime.date.today():
            member_type = MemberInfoSerializer.Type.STANDARD
        else:
            member_type = MemberInfoSerializer.Type.FREE
        return member_type


class ExchangeQuerySerializer(serializers.Serializer):
    """
    member_type（member_standard, member_premium）
    duration:（30,90,360）
    """

    class Type(models.TextChoices):
        STANDARD = 'member_standard', _('member_standard')
        PREMIUM = 'member_premium', _('member_premium')

    class Duration(models.IntegerChoices):
        THIRTY = 30, _('30')
        NINETY = 90, _('90')
        THREE_SIXTY = 360, _('360')

    member_type = serializers.ChoiceField(choices=Type, default=Type.STANDARD)
    duration = serializers.ChoiceField(choices=Duration, default=Duration.THIRTY)


class TokensHistoryListSerializer(serializers.ModelSerializer):
    used_info = serializers.SerializerMethodField()
    status_desc = serializers.SerializerMethodField()

    @staticmethod
    def get_used_info(obj: TokensHistory):
        data = {}
        if obj.type in [
            TokensHistory.Type.EXCHANGE_STANDARD_30, TokensHistory.Type.EXCHANGE_STANDARD_90,
            TokensHistory.Type.EXCHANGE_STANDARD_360, TokensHistory.Type.EXCHANGE_PREMIUM_30,
            TokensHistory.Type.EXCHANGE_PREMIUM_90, TokensHistory.Type.EXCHANGE_PREMIUM_360
        ]:
            if obj.status == TokensHistory.Status.FREEZING:
                if not obj.freezing_date or obj.freezing_date < obj.start_date:
                    data['remain_days'] = (obj.end_date - obj.start_date).days + 1
                else:
                    data['remain_days'] = (obj.end_date - obj.freezing_date).days + 1
            elif obj.end_date >= datetime.date.today():
                data['remain_days'] = (obj.end_date - datetime.date.today()).days + 1
            else:
                data['end_date'] = obj.end_date
        elif obj.end_date:
            data['end_date'] = obj.end_date
        return data

    @staticmethod
    def get_status_desc(obj: TokensHistory):
        status_map = {
            0: 'deleted',
            2: 'completed',
            3: 'in_progress',
            4: 'freezing',
        }
        return status_map.get(obj.status, 'completed')

    class Meta:
        model = TokensHistory
        fields = ['id', 'trade_no', 'amount', 'type', 'pay_amount', 'used_info', 'status', 'status_desc', 'created_at']


class TradesQuerySerializer(serializers.Serializer):
    class Status(models.TextChoices):
        ALL = 'all', _('all')
        COMPLETED = 'completed', _('completed')
        VALID = 'valid', _('valid')
        IN_PROGRESS = 'in_progress', _('in_progress')
        FREEZING = 'freezing', _('freezing')

    status = serializers.ChoiceField(choices=Status, default=Status.ALL)
    page_size = serializers.IntegerField(default=10)
    page_num = serializers.IntegerField(default=1)


class TokensAwardQuerySerializer(serializers.Serializer):
    class Type(models.TextChoices):
        REGISTER_AWARD = 'register_award', _('register_award')
        MONTHLY_AWARD = 'monthly_award', _('monthly_award')
        INVITE_REGISTER = 'invite_register', _('invite_register')
        SUBSCRIBED_BOT = 'subscribed_bot', _('subscribed_bot')

    award_type = serializers.ChoiceField(choices=Type, default=Type.REGISTER_AWARD)
    amount = serializers.IntegerField(default=0)
    bot_id = serializers.CharField(required=False, default=None)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs['award_type'] == TokensAwardQuerySerializer.Type.SUBSCRIBED_BOT:
            if not attrs.get('bot_id'):
                raise serializers.ValidationError('bot_id is required')

        return attrs


class LimitCheckSerializer(serializers.Serializer):
    @staticmethod
    def chat_limit(user_id):
        member = Member.objects.filter(user_id=user_id).first()
        member_type = MemberInfoSerializer.get_member_type(member)
        chat_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.CHAT)
        chat_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING)
        if member_type in [
            MemberInfoSerializer.Type.FREE, MemberInfoSerializer.Type.STANDARD, MemberInfoSerializer.Type.PREMIUM
        ]:
            limit_config = GlobalConfig.get_limit(member_type, ['limit_chat_daily', 'limit_chat_monthly'])
            limit_info = {
                'daily': limit_config['limit_chat_daily'],
                'monthly': limit_config['limit_chat_monthly'],
                'used_day': chat_static_day,
                'used_month': chat_static_monty,
            }
        else:
            limit_info = {
                'daily': None,
                'monthly': None,
                'used_day': chat_static_day,
                'used_month': chat_static_monty,
            }
        return limit_info

    @staticmethod
    def embedding_limit(user_id):
        member = Member.objects.filter(user_id=user_id).first()
        member_type = MemberInfoSerializer.get_member_type(member)
        embedding_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.EMBEDDING)
        embedding_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING)
        if member_type in [
            MemberInfoSerializer.Type.FREE, MemberInfoSerializer.Type.STANDARD, MemberInfoSerializer.Type.PREMIUM
        ]:
            limit_config = GlobalConfig.get_limit(member_type, ['limit_embedding_daily', 'limit_embedding_monthly'])
            limit_info = {
                'daily': limit_config['limit_embedding_daily'],
                'monthly': limit_config['limit_embedding_monthly'],
                'used_day': embedding_static_day,
                'used_month': embedding_static_monty,
            }
        else:
            limit_info = {
                'daily': None,
                'monthly': None,
                'used_day': embedding_static_day,
                'used_month': embedding_static_monty,
            }
        return limit_info