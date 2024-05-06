import logging
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class MyUser(AbstractUser):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(null=True, max_length=254, unique=True, default=None, db_default=None)
    phone = models.CharField(null=True, max_length=14, unique=True, default=None, db_default=None)
    nickname = models.CharField(null=True, max_length=128, default=None, db_default=None)
    avatar = models.CharField(null=True, max_length=256, default=None, db_default=None)
    first_name = models.CharField(null=True, max_length=150, verbose_name='first name')
    last_name = models.CharField(null=True, max_length=150, verbose_name='last name')
    password = models.CharField(null=True, max_length=128, verbose_name='password')
    is_superuser = models.BooleanField(default=False, db_default=False, verbose_name='superuser status')
    is_staff = models.BooleanField(default=False, db_default=False, verbose_name='staff status')
    is_active = models.BooleanField(default=True, db_default=True, verbose_name='active')
    last_login = models.DateTimeField(null=True, verbose_name='last login')
    updated_at = models.DateTimeField(null=True, auto_now=True, verbose_name='Last update time')
    date_joined = models.DateTimeField(null=True, auto_now_add=True, verbose_name='date joined')
    description = models.TextField(null=True, db_default=None)

    class Meta:
        db_table = 'my_user'
        verbose_name = 'user'
        verbose_name_plural = verbose_name


class UserOperationLog(models.Model):
    class OperationType(models.TextChoices):
        SEARCH = 'search', _('search')
        DOCUMENT_DETAIL = 'document_detail', _('document_detail')
        DOCUMENT_URL = 'document_url', _('document_url')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        MyUser, db_constraint=False, on_delete=models.DO_NOTHING, null=True, related_name='user_operation_log'
    )
    operation_type = models.CharField(null=False, db_index=True, max_length=32)
    obj_id1 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id2 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id3 = models.IntegerField(null=True, db_index=True, default=None, db_default=None)
    operation_content = models.TextField(null=True, default=None, db_default=None)
    created_at = models.DateTimeField(null=False, auto_now_add=True)

    class Meta:
        db_table = 'user_operation_log'
        verbose_name = 'user operation log'