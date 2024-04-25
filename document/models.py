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
        UNDONE = 'undone', _('undone')
        PARSING = 'in_progress', _('in_progress')
        COMPLETED = 'completed', _('completed')
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
    title = models.CharField(null=True, blank=True, db_index=True, max_length=512, default=None, db_default=None)
    abstract = models.TextField(null=True, blank=True, db_default=None)
    authors = models.JSONField(null=True)
    doi = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    categories = models.JSONField(null=True)
    pages = models.IntegerField(null=True)
    year = models.IntegerField(null=True)
    pub_date = models.DateField(null=True)
    pub_type = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None)
    venue = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    journal = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    conference = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    keywords = models.JSONField(null=True)
    full_text_accessible = models.BooleanField(null=True, default=None, db_default=None)
    citation_count = models.IntegerField(null=True)
    reference_count = models.IntegerField(null=True)
    citations = models.JSONField(null=True)
    references = models.JSONField(null=True)
    state = models.CharField(
        null=True, blank=True, max_length=32, default=StateChoices.UNDONE, db_default=StateChoices.UNDONE)
    object_path = models.CharField(null=True, blank=True, max_length=256)
    source_url = models.CharField(null=True, blank=True, max_length=256)
    checksum = models.CharField(null=True, blank=True, db_index=True, max_length=64)
    ref_collection_id = models.CharField(null=True, blank=True, db_index=True, max_length=36)
    ref_doc_id = models.BigIntegerField(null=True)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    @staticmethod
    def raw_by_docs(docs, fileds='*', where=None):
        if fileds != '*' and isinstance(fileds, list):
            fileds = ','.join(fileds)
        doc_ids_str = ','.join([f"('{d['collection_id']}', {d['doc_id']})" for d in docs])
        sql = f"SELECT {fileds} FROM document WHERE (collection_id, doc_id) IN ({doc_ids_str})"
        if where:
            sql += f"and {where}"
        return Document.objects.raw(sql)

    @staticmethod
    def difference_docs(docs1, docs2):
        docs1_dict = {f"{d['collection_id']}-{d['doc_id']}": d for d in docs1}
        docs2_dict = {f"{d['collection_id']}-{d['doc_id']}": d for d in docs2}
        diff_docs = []
        for k, v in docs1_dict.items():
            if k not in docs2_dict:
                diff_docs.append(v)
        return diff_docs

    class Meta:
        unique_together = ['collection_id', 'doc_id']
        db_table = 'document'
        verbose_name = 'document'


class DocumentLibrary(models.Model):
    class TaskStatusChoices(models.TextChoices):
        PENDING = 'pending', _('pending')
        QUEUEING = 'queueing', _('queueing')
        IN_PROGRESS = 'in_progress', _('in_progress')
        COMPLETED = 'completed', _('completed')
        ERROR = 'error', _('error')
        # CANCELED = 'canceled', _('canceled')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    document = models.ForeignKey(
        Document, db_constraint=False, on_delete=models.DO_NOTHING, db_column='document_id', related_name='doc_lib',
        null=True,
    )
    task_id = models.CharField(null=True, blank=True, max_length=36)
    task_status = models.CharField(
        null=True, blank=True, max_length=32, db_index=True, default=TaskStatusChoices.PENDING)
    error = models.JSONField(null=True)
    filename = models.CharField(null=True, blank=True, max_length=512)
    object_path = models.CharField(null=True, blank=True, max_length=512)
    folder = models.ForeignKey(
        'DocumentLibraryFolder', db_constraint=False, on_delete=models.DO_NOTHING, db_column='folder_id',
        related_name='doc_lib_folder', null=True, default=None
    )
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'document_library'
        verbose_name = 'document_library'


class DocumentLibraryFolder(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    name = models.CharField(null=False, blank=False, max_length=200)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot = models.ForeignKey(
        'bot.Bot', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='bot_id')
    collection = models.ForeignKey(
        'collection.Collection', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='collection_id')
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'document_library_folder'
        verbose_name = 'document_library_folder'
