import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Bot(models.Model):
    class TypeChoices(models.TextChoices):
        PERSONAL = 'personal', _('personal'),
        IN_PROGRESS = 'in_progress', _('in_progress'),
        PUBLIC = 'public', _('public')
        SHARE = 'share', _('share')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    agent_id = models.CharField(null=True, blank=True, max_length=36)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    author = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    title = models.CharField(null=True, blank=True, max_length=200, default=None, db_default=None)
    prompt = models.JSONField(null=True, blank=True, db_default=None)
    description = models.TextField(null=True, blank=True, db_default=None)
    questions = models.JSONField(null=True, default=None, db_default=None)
    llm = models.JSONField(null=True, default=None, db_default=None)
    tools = models.JSONField(null=True, default=None, db_default=None)
    cover_url = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    type = models.CharField(null=True, blank=True, max_length=32, default=TypeChoices.PERSONAL,
                            db_default=TypeChoices.PERSONAL, choices=TypeChoices)
    pub_date = models.DateField(null=True)
    order = models.IntegerField(null=False, default=0, db_default=0)
    extension = models.JSONField(null=True)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'bot'
        verbose_name = 'bot'


class HotBot(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    bot = models.ForeignKey(
        Bot, db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='bot_id')
    order_num = models.IntegerField()
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'hot_bot'
        verbose_name = 'hot_bot'


class BotCollection(models.Model):
    class CollectionTypeChoices(models.TextChoices):
        PERSONAL = 'personal', _('personal'),
        PUBLIC = 'public', _('public')
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    bot = models.ForeignKey(
        Bot, db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='bot_id',
        related_name='bot_collection')
    collection = models.ForeignKey(
        'collection.Collection', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='collection_id',
        related_name='bot_collection'
    )
    collection_type = models.CharField(
        null=True, blank=True, max_length=32, default=CollectionTypeChoices.PERSONAL,
        db_default=CollectionTypeChoices.PERSONAL, choices=CollectionTypeChoices)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'bot_collection'
        verbose_name = 'bot_collection'


class BotSubscribe(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot = models.ForeignKey(
        Bot, on_delete=models.CASCADE, null=True, db_column='bot_id', related_name='bot_subscribe')
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True,    auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'bot_subscribe'
        verbose_name = 'bot_subscribe'


class BotTools(models.Model):
    class AuthType(models.TextChoices):
        Basic = 'basic', _('basic'),
        BEARER = 'bearer', _('bearer'),
        API_KEY = 'api_key', _('api_key'),
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot = models.ForeignKey(
        Bot, db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='bot_id',
        related_name='bot_tools')
    name = models.CharField(blank=True)
    url = models.CharField(null=True, blank=True)
    openapi_json_path = models.CharField(null=True, blank=True)
    auth_type = models.CharField(null=True, choices=AuthType, default=None, db_default=None)
    username_password_base64 = models.CharField(null=True, blank=True)
    token = models.CharField(null=True, blank=True)
    api_key = models.CharField(null=True, blank=True)
    custom_header = models.CharField(null=True, blank=True)
    endpoints = models.JSONField(null=True)
    description = models.TextField(null=True, blank=True)
    checked = models.BooleanField(default=False, db_default=False)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True,    auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'bot_tools'
        verbose_name = 'bot_tools'
