import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# class Agent(models.Model):
#     id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
#     user = models.ForeignKey(
#         'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
#     version = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None)
#     questions = models.JSONField(null=True, default=None, db_default=None)
#     public_collection_ids = models.JSONField(null=True, blank=True, db_default=None)
#     paper_ids = models.JSONField(null=True, blank=True, db_default=None)
#     spec = models.JSONField(null=True)
#     del_flag = models.BooleanField(default=False, db_default=False)
#     updated_at = models.DateTimeField(null=True, auto_now=True)
#     created_at = models.DateTimeField(null=True, auto_now_add=True)
#
#     class Meta:
#         db_table = 'agent'
#         verbose_name = 'agent'


class Conversation(models.Model):
    class TypeChoices(models.TextChoices):
        BOT_COV = 'bot', _('bot')
        DOC_COV = 'doc', _('doc')
        DOCS_COV = 'docs', _('docs')
        DOC_LIB_COV = 'doc_lib', _('doc_lib')
        COLLECTION_COV = 'collection', _('collection')
        COLLECTIONS_COV = 'collections', _('collections')
        MIX_COV = 'mix', _('mix')
        SIMPLE_COV = 'simple', _('simple')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    title = models.CharField(null=True, blank=True, max_length=200, default=None, db_default=None)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    agent_id = models.CharField(null=True, blank=True, max_length=36, default=None, db_default=None)
    public_collection_ids = models.JSONField(null=True, blank=True, db_default=None)
    paper_ids = models.JSONField(null=True, blank=True, db_default=None)
    type = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None, choices=TypeChoices)
    bot_id = models.CharField(null=True, blank=True, max_length=36, default=None, db_default=None)
    collections = models.JSONField(null=True)
    documents = models.JSONField(null=True)
    model = models.CharField(null=True, blank=True, max_length=64, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    last_used_at = models.DateTimeField(null=True, auto_now=True)
    is_named = models.BooleanField(default=False, db_default=False)
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
    content = models.TextField()
    answer = models.TextField(null=True, blank=True, db_default=None)
    is_like = models.BooleanField(null=True, default=None, db_default=None)
    stream = models.JSONField(null=True, blank=True, db_default=None)
    input_tokens = models.IntegerField(null=True, default=None, db_default=None)
    output_tokens = models.IntegerField(null=True, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'question'
        verbose_name = 'question'
