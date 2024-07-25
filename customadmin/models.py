import logging

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# 会员配置： global_config:
class GlobalConfig(models.Model):
    class ConfigType(models.TextChoices):
        MEMBER_FREE = 'member_free', _('member_free')
        MEMBER_STANDARD = 'member_standard', _('member_standard')
        MEMBER_PREMIUM = 'member_premium', _('member_premium')
        VIP = 'vip', _('vip')

        AWARD = 'award', _('award')
        ACTIVITY = 'activity', _('activity')

        TIME_CLOCK = 'time_clock', _('time_clock')

    class SubType(models.TextChoices):
        # member
        LIMIT = 'limit', _('limit')
        EXCHANGE = 'exchange', _('exchange')
        # award
        SUBSCRIBED_BOT = 'subscribed_bot', _('subscribed_bot')
        INVITE_REGISTER = 'invite_register', _('invite_register')
        NEW_USER_AWARD = 'new_user_award', _('new_user_award')
        DURATION = 'duration_award', _('duration_award')
        # activity
        DISCOUNT = 'discount', _('discount')
        # time_clock
        MEMBER = 'member', _('member')

    name = models.CharField(max_length=256, null=True, default=None, db_default=None)
    config_type = models.CharField(max_length=128, null=True, default=None, db_default=None, choices=ConfigType)
    sub_type = models.CharField(max_length=128, null=True, default=None, db_default=None, choices=SubType)
    # value:{
    #   # limit
    #   "limit_chat_daily": "",
    #   "limit_chat_monthly": "",
    #   "limit_embedding_daily": "",
    #   "limit_embedding_monthly": "",
    #   "limit_advanced_share": 3,
    #   "limit_max_file_size": 30,
    #   # exchange
    #   "days_30": 450,
    #   "days_90": 900,
    #   "days_360": 3200,
    #   # award
    #   "per":0,
    #   "limit":0,
    #   "period_of_validity":0,
    # }
    value = models.JSONField(null=True, default=None, db_default=None)
    order = models.IntegerField(default=0, db_default=0)
    updated_by = models.CharField(max_length=36, null=True, default=None, db_default=None)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)
    del_flag = models.BooleanField(default=False, db_default=False)

    @staticmethod
    def get_limit(member_type, limit_types):
        config = GlobalConfig.objects.filter(config_type=member_type, sub_type=GlobalConfig.SubType.LIMIT).first()
        limit = {}
        for limit_type in limit_types:
            limit[limit_type] = config.value.get(limit_type) if config else None
        return limit

    @staticmethod
    def get_award(award_types):
        configs = GlobalConfig.objects.filter(
            config_type=GlobalConfig.ConfigType.AWARD, sub_type__in=award_types).all()
        config = {}
        for c in configs:
            config[c.sub_type] = c.value
        return config

    class Meta:
        db_table = 'global_config'
        verbose_name = 'global config'
        unique_together = ('config_type', 'sub_type')


class Notification(models.Model):
    title = models.CharField(max_length=512, null=True, blank=True)
    en_title = models.CharField(max_length=512, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    en_content = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=False, db_default=False)
    updated_by = models.CharField(max_length=36, null=True, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'notification'
        verbose_name = 'notification'