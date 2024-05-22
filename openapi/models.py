from django.db import models

from django.utils.translation import gettext_lazy as _

from core.utils.common import str_hash
from core.utils.utils import random_str
from user.models import MyUser


# Create your models here.


class OpenapiKey(models.Model):
    user = models.ForeignKey(
        MyUser, db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    title = models.CharField(max_length=256, blank=True)
    api_key = models.CharField(max_length=128, unique=True)
    api_key_show = models.CharField(max_length=128)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=False, auto_now_add=True)

    class Meta:
        db_table = 'openapi_key'
        verbose_name = 'openapi_key'

    def gen_real_key(self):
        return f"sk-{self.id:010d}-{random_str(48)}"

    @staticmethod
    def gen_show_key(key):
        return f"{key[:3]}****{key[-4:]}"

    @staticmethod
    def gen_salt():
        return random_str(22)

    @staticmethod
    def encode(salt, key, algorithm='sha256'):
        hash_str = str_hash(f"{salt}{key.strip()}", algorithm)
        return f"{algorithm}${salt}${hash_str}"

    @staticmethod
    def decode(encoded):
        algorithm, salt, hash_str = encoded.strip().split('$')
        return {
            "algorithm": algorithm,
            "hash": hash_str,
            "salt": salt,
        }

    @staticmethod
    def key_check(encoded, key):
        decoded = OpenapiKey.decode(encoded.strip())
        encoded_2 = OpenapiKey.encode(salt=decoded['salt'], key=key, algorithm=decoded['algorithm'])
        return encoded == encoded_2


class OpenapiLog(models.Model):
    """
    openapi日志
    """
    class Status(models.IntegerChoices):
        UNKNOWN = 0
        SUCCESS = 1
        FAILED = 2

    class Api(models.IntegerChoices):
        SEARCH = 1
        CONVERSATION = 2
        UPLOAD_PAPER = 3
        LIST_BOTS = 4
        LIST_MY_BOTS = 5
        LIST_MY_DOC_LIBS = 6

    user = models.ForeignKey(
        MyUser, db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    openapi_key = models.ForeignKey(
        OpenapiKey, db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    model = models.CharField(max_length=256, null=False, blank=True, default='', db_default='')
    api = models.IntegerField(choices=Api, db_index=True)
    obj_id1 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id2 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id3 = models.BigIntegerField(null=True, db_index=True, default=None, db_default=None)
    status = models.IntegerField(choices=Status, default=Status.UNKNOWN, db_default=Status.UNKNOWN)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=False, db_index=True, auto_now_add=True)

    class Meta:
        db_table = 'openapi_log'
        verbose_name = 'openapi_log'


class OpenapiUsage(models.Model):
    """
    openapi用量
    """
    user = models.ForeignKey(
        MyUser, db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    openapi_key = models.ForeignKey(
        OpenapiKey, db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    model = models.CharField(max_length=256, null=False, blank=True, default='', db_default='')
    api = models.IntegerField(choices=OpenapiLog.Api, db_index=True)
    date = models.DateField(null=False, db_index=True)
    total = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=False, db_index=True, auto_now_add=True)

    class Meta:
        unique_together = ['user', 'openapi_key', 'model', 'api', 'date']
        db_table = 'openapi_usage'
        verbose_name = 'openapi_usage'