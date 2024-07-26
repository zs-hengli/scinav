import datetime
import logging

from django.db import models
from rest_framework import serializers

from django.utils.translation import gettext_lazy as _

from customadmin.models import GlobalConfig
from vip.base_service import MemberTimeClock
from vip.models import TokensHistory, Member, MemberUsageLog


logger = logging.getLogger(__name__)


# generate_pay_qrcode
class PayQrcodeQuerySerializer(serializers.Serializer):
    out_trade_no = serializers.CharField(required=False, default=None)
    description = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True, min_value=1)


class MemberInfoSerializer(serializers.Serializer):
    """
    member  账户信息
        余额
        账户类型 剩余天数
        问题使用量
        文件解析量
    """

    amount = serializers.IntegerField(default=0)
    member_type = serializers.ChoiceField(choices=Member.Type, default=Member.Type.FREE)
    expire_days = serializers.IntegerField(allow_null=True, default=None)
    chat_used_day = serializers.IntegerField(allow_null=True, default=None)
    limit_chat_daily = serializers.IntegerField(allow_null=True, default=None)
    embedding_used_month = serializers.IntegerField(allow_null=True, default=None)
    limit_embedding_monthly = serializers.IntegerField(allow_null=True, default=None)


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
    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    @staticmethod
    def get_used_info(obj: TokensHistory):
        data = {}
        if obj.type in TokensHistory.TYPE_EXCHANGE:
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


class TokensHistoryListFormatSerializer(serializers.Serializer):
    id = serializers.CharField()
    trade_no = serializers.CharField()
    amount = serializers.IntegerField()
    type = serializers.CharField()
    pay_amount = serializers.IntegerField()
    used_info = serializers.JSONField()
    status = serializers.IntegerField()
    status_desc = serializers.CharField()
    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    @classmethod
    def get_member_type(cls, obj, today):
        if obj['is_vip']:
            member_type = Member.Type.VIP
        elif obj['premium_end_date'] and obj['premium_end_date'] >= today:
            member_type = Member.Type.PREMIUM
        elif obj['standard_end_date'] and obj['standard_end_date'] >= today:
            member_type = Member.Type.STANDARD
        else:
            member_type = Member.Type.FREE
        return member_type

    @classmethod
    def format_used_info(cls, obj, today):
        data = {}
        if obj['type'] in TokensHistory.TYPE_EXCHANGE:
            if obj['status'] == TokensHistory.Status.FREEZING and obj['freezing_date']:
                start_date = max(obj['freezing_date'], obj['start_date'])
                data['remain_days'] = (obj['end_date'] - start_date).days + 1
            elif obj['start_date'] > today:
                data['remain_days'] = (obj['end_date'] - obj['start_date']).days + 1
            elif obj['end_date'] >= today:
                data['remain_days'] = (obj['end_date'] - today).days + 1
            else:
                data['end_date'] = obj['end_date']
        elif obj['end_date']:
            data['end_date'] = obj['end_date']
        obj['used_info'] = data
        return obj

    @classmethod
    def format_status(cls, obj, today):
        status_map = {
            0: 'deleted',
            2: 'completed',
            3: 'in_progress',
            4: 'freezing',
        }
        member_type = cls.get_member_type(obj, today)
        is_expire = obj['end_date'] and obj['end_date'] < today and not obj['freezing_date']
        if obj['type'] not in TokensHistory.TYPE_EXCHANGE or is_expire:
            obj['status'] = TokensHistory.Status.COMPLETED
        else:
            if member_type == Member.Type.VIP:
                obj['status'] = TokensHistory.Status.FREEZING
            elif member_type == Member.Type.PREMIUM:
                if obj['type'] in TokensHistory.TYPE_EXCHANGE_STANDARD:
                    obj['status'] = TokensHistory.Status.FREEZING
                else:
                    obj['status'] = (
                        TokensHistory.Status.IN_PROGRESS if obj['start_date'] <= today <= obj['end_date']
                        else TokensHistory.Status.FREEZING
                    )
            else:
                if obj['type'] in TokensHistory.TYPE_EXCHANGE_PREMIUM:
                    obj['status'] = TokensHistory.Status.COMPLETED
                else:
                    obj['status'] = (
                        TokensHistory.Status.IN_PROGRESS if obj['start_date'] <= today <= obj['end_date']
                        else TokensHistory.Status.FREEZING
                    )
        obj['status_desc'] = status_map.get(obj['status'], 'completed')
        return obj


class TradesQuerySerializer(serializers.Serializer):
    class Status(models.TextChoices):
        ALL = 'all', _('all')
        COMPLETED = 'completed', _('completed')
        VALID = 'valid', _('valid')
        # IN_PROGRESS = 'in_progress', _('in_progress')
        # FREEZING = 'freezing', _('freezing')

    status = serializers.ChoiceField(choices=Status, default=Status.ALL)
    page_size = serializers.IntegerField(default=10)
    page_num = serializers.IntegerField(default=1)


class TokensAwardQuerySerializer(serializers.Serializer):
    class Type(models.TextChoices):
        NEW_USER_AWARD = 'new_user_award', _('new_user_award')
        DURATION_AWARD = 'duration_award', _('duration_award')
        INVITE_REGISTER = 'invite_register', _('invite_register')
        SUBSCRIBED_BOT = 'subscribed_bot', _('subscribed_bot')

    award_type = serializers.ChoiceField(choices=Type, default=Type.NEW_USER_AWARD)
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
        clock_time = MemberTimeClock.get_member_time_clock(user_id)
        if clock_time:
            today = clock_time.date()
        else:
            today = datetime.date.today()
        member = Member.objects.filter(user_id=user_id).first()
        member_type = member.get_member_type(today) if member else Member.Type.FREE
        chat_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.CHAT)
        chat_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING)
        if member_type in [
            Member.Type.FREE, Member.Type.STANDARD, Member.Type.PREMIUM
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
        clock_time = MemberTimeClock.get_member_time_clock(user_id)
        if clock_time:
            today = clock_time.date()
        else:
            today = datetime.date.today()
        member = Member.objects.filter(user_id=user_id).first()
        member_type = member.get_member_type(today) if member else Member.Type.FREE
        embedding_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.EMBEDDING)
        embedding_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING)
        if member_type in [Member.Type.FREE, Member.Type.STANDARD, Member.Type.PREMIUM]:
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