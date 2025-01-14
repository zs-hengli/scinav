import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


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

    class LLMModel(models.TextChoices):

        GPT_4O = 'gpt-4o', 'GPT-4o'
        # GPT_4O_MINI = "gpt-4o-mini", "GPT-4o-mini"
        # CLAUDE_3_5_SONNET = "claude-3.5-sonnet", "Claude-3.5-Sonnet"
        BASIC = "basic", "Basic"
        ADVANCED = "advanced", "Advanced"

    class OpenapiLLMModel(models.TextChoices):
        GPT_4O = 'gpt-4o', 'GPT-4o'
        GPT_4O_MINI = "gpt-4o-mini", "GPT-4o-mini"
        CLAUDE_3_5_SONNET = "claude-3.5-sonnet", "Claude-3.5-Sonnet"

    class AllLLMModel(models.TextChoices):
        GPT_4O = 'gpt-4o', 'GPT-4o'
        GPT_4O_MINI = "gpt-4o-mini", "GPT-4o-mini"
        CLAUDE_3_5_SONNET = "claude-3.5-sonnet", "Claude-3.5-Sonnet"
        GPT_4 = 'gpt-4', 'GPT-4'
        GPT_3_5 = 'gpt-3.5', 'GPT-3.5'
        GPT_3_5_TURBO = 'gpt-3.5-turbo', 'GPT-3.5-Turbo'
        BASIC = "basic", "Basic"
        ADVANCED = "advanced", "Advanced"

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    title = models.CharField(null=True, blank=True, max_length=200, default=None, db_default=None)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    share = models.ForeignKey(
        'chat.ConversationShare', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='share_id',
        default=None, db_default=None, related_name='share_conversations'
    )
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
    is_api = models.BooleanField(default=False, db_default=False)
    source = models.CharField(null=True, blank=True, max_length=1024, default=None, db_default=None)
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
    content = models.TextField(null=True)
    answer = models.TextField(null=True, blank=True, db_default=None)
    is_like = models.BooleanField(null=True, default=None, db_default=None)
    stream = models.JSONField(null=True, blank=True, db_default=None)
    model = models.CharField(null=True, blank=True, max_length=64, default=None, db_default=None)
    input_tokens = models.IntegerField(null=True, default=None, db_default=None)
    output_tokens = models.IntegerField(null=True, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    is_stop = models.BooleanField(default=False, db_default=False)
    source = models.CharField(null=True, blank=True, max_length=512, default=None, db_default=None)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'question'
        verbose_name = 'question'


class ConversationShare(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    conversation = models.ForeignKey(
        Conversation, db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='conversation_id'
    )
    title = models.CharField(null=True, blank=True, max_length=200, default=None, db_default=None)
    bot_id = models.CharField(null=True, blank=True, max_length=36, default=None, db_default=None)
    collections = models.JSONField(null=True)
    documents = models.JSONField(null=True)
    model = models.CharField(null=True, blank=True, max_length=64, default=None, db_default=None)
    content = models.JSONField(null=True, blank=True, db_default=None)
    num = models.IntegerField(null=True, default=None, db_default=None)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'conversation_share'
        verbose_name = 'conversation_share'
