import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Document(models.Model):
    class TypeChoices(models.TextChoices):
        PERSONAL = 'personal', _('personal')
        PUBLIC = 'public', _('public')

    class StateChoices(models.TextChoices):
        # UPLOADING = 'uploading', _('uploading')
        PARSING = 'in_progress', _('in_progress')
        COMPLETE = 'complete', _('complete')
        FAILED = 'error', _('error')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    doc_id = models.BigIntegerField(null=True)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    collection_type = models.CharField(
        null=True, blank=True, max_length=32, default=TypeChoices.PERSONAL, db_default=TypeChoices.PERSONAL)
    collection = models.ForeignKey(
        'collection.Collection', db_constraint=False, on_delete=models.DO_NOTHING, null=True,
        db_column='collection_id')
    title = models.CharField(null=True, blank=True, db_index=True, max_length=200, default=None, db_default=None)
    abstract = models.TextField(null=True, blank=True, db_default=None)
    authors = models.JSONField(null=True)
    doi = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    categories = models.JSONField(null=True)
    page_num = models.IntegerField(null=True)
    year = models.IntegerField(null=True)
    pub_date = models.DateField(null=True)
    pub_type = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None)
    venue = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    journal = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    conference = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    keywords = models.JSONField(null=True)
    is_open_access = models.BooleanField(null=True, default=False, db_default=False)
    citation_count = models.IntegerField(null=True)
    reference_count = models.IntegerField(null=True)
    citations = models.JSONField(null=True)
    references = models.JSONField(null=True)
    state = models.CharField(
        null=True, blank=True, max_length=32, default=StateChoices.COMPLETE, db_default=StateChoices.COMPLETE)
    object_path = models.CharField(null=True, blank=True, max_length=256)
    source_url = models.CharField(null=True, blank=True, max_length=256)
    checksum = models.CharField(null=True, blank=True, db_index=True, max_length=64)
    ref_collection_id = models.CharField(null=True, blank=True, db_index=True, max_length=36)
    ref_doc_id = models.BigIntegerField(null=True)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'document'
        verbose_name = 'document'


class IngestDocument(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    url = models.CharField(null=True, blank=True, max_length=256)
    task_id = models.CharField(null=True, blank=True, max_length=36)
    task_status = models.CharField(null=True, blank=True, max_length=32, db_index=True)
    doc_id = models.BigIntegerField(null=True, default=None, db_default=None)
    collection_type = models.CharField(null=True, blank=True, max_length=32)
    collection_id = models.CharField(null=True, blank=True, max_length=36)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)


class DocumentLibrary(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    document = models.ForeignKey(
        Document, db_constraint=False, on_delete=models.DO_NOTHING, db_column='document_id', related_name='doc_lib'
    )
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'document_library'
        verbose_name = 'document_library'
