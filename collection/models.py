import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Collection(models.Model):
    class TypeChoices(models.TextChoices):
        PERSONAL = 'personal', _('personal'),
        PUBLIC = 'public', _('public')
        Bot = 'bot', _('bot')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    title = models.CharField(null=True, blank=True, max_length=128, default=None, db_default=None)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot_id = models.CharField(null=True, blank=True, max_length=36, default=None, db_default=None)
    type = models.CharField(null=True, blank=True, max_length=32, default=TypeChoices.PERSONAL,
                            db_default=TypeChoices.PERSONAL)
    total = models.IntegerField(default=0, db_default=0)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'collection'
        verbose_name = 'collection'


class CollectionDocument(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    collection = models.ForeignKey(
        Collection, db_constraint=False, on_delete=models.DO_NOTHING, null=True, related_name='collection_doc'
    )
    document = models.ForeignKey(
        'document.Document', db_constraint=False, on_delete=models.DO_NOTHING, db_column='document_id')
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'collection_document'
        verbose_name = 'collection_document'
