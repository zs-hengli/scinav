import logging
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

logger = logging.getLogger(__name__)


class Conversation(models.Model):
    AGENT_COV = 'bot'
    DOC_COV = 'doc'
    DOCS_COV = 'docs'
    DOC_LIB_COV = 'doc_lib'
    COLLECTION_COV = 'collection'
    COLLECTIONS_COV = 'collections'
    MIX_COV = 'mix'
    TYPE_CHOICE = {
        AGENT_COV: 'bot',
        DOC_COV: 'doc',
        DOCS_COV: 'docs',
        DOC_LIB_COV: 'doc_lib',
        MIX_COV: 'mix',
        COLLECTION_COV: 'collection',
        COLLECTIONS_COV: 'collections',
    }

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    title = models.CharField(null=True, blank=True, max_length=200, default=None, db_default=None)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot = models.ForeignKey(
        'bot.Bot', db_constraint=False, on_delete=models.DO_NOTHING, null=True, related_name='conv'
    )
    type = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None)
    docs = models.JSONField(null=True)
    model = models.CharField(null=True, blank=True, max_length=64, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'conversation'
        verbose_name = 'conversation'


class Question(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    conversation = models.ForeignKey(
        Conversation, db_constraint=False, on_delete=models.DO_NOTHING, null=True, related_name='question'
    )
    prompt = models.TextField()
    answer = models.TextField(null=True, blank=True, db_default=None)
    docs = models.JSONField(null=True)
    is_like = models.BooleanField(null=True, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'question'
        verbose_name = 'question'
