import logging
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

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