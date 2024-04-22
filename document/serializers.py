import logging
import os

from django.conf import settings
from django.db import models
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from bot.rag_service import Document as RagDocument

from collection.models import Collection
from document.models import Document

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class DocumentApaListSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        # 作者1,作者2;标题.期刊 时间
        authors = ','.join(obj.authors)
        title = obj.title
        year = obj.year
        source = obj.journal if obj.journal else obj.conference if obj.conference else ''
        return f'{authors};{title}.{source} {year}'  # noqa

    class Meta:
        model = Document
        fields = ['id', 'doc_apa']


class DocumentApcReadListSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        # 作者1,作者2;标题.期刊 时间
        authors = ','.join(obj.authors)
        title = obj.title
        year = obj.year
        source = obj.journal if obj.journal else obj.conference if obj.conference else ''
        return f'{authors};{title}.{source} {year}'  # noqa

    class Meta:
        model = Document
        fields = ['id', 'doc_apa', 'full_text_accessible', 'object_path', 'ref_collection_id', 'ref_doc_id']



class CollectionDocumentListCollectionSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        # 作者1,作者2;标题.期刊 时间
        authors = ','.join(obj.authors)
        title = obj.title
        year = obj.year
        source = obj.journal if obj.journal else obj.conference if obj.conference else ''
        return f'{authors};{title}.{source} {year}'  # noqa

    @staticmethod
    def get_type(obj: Document):
        if obj.collection_type == Document.TypeChoices.PUBLIC:
            return obj.collection_id
        else:
            return obj.collection_type

    class Meta:
        model = Document
        fields = ['id', 'doc_apa', 'title', 'type']


class DocumentUpdateFilenameQuerySerializer(BaseModelSerializer):
    filename = serializers.CharField(required=True, allow_blank=False, allow_null=False)


class DocumentRagUpdateSerializer(BaseModelSerializer):
    doc_id = serializers.IntegerField(required=True)
    collection_type = serializers.ChoiceField(required=True, choices=Document.TypeChoices)
    collection_id = serializers.CharField(required=True)

    class Meta:
        model = Document
        fields = ['id', 'doc_id', 'title', 'collection_type', 'collection_id', 'updated_at', 'created_at']


class DocumentUploadFileSerializer(serializers.Serializer):
    object_path = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    filename = serializers.CharField(required=True, allow_blank=False, allow_null=False)

    def validate(self, attrs):
        filename = attrs.get('filename')
        basename = os.path.basename(filename)
        attrs['name'] = os.path.splitext(basename)[0]
        return attrs


class DocumentUploadQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    files = DocumentUploadFileSerializer(many=True, required=True, allow_null=False)


class DocumentRagCreateSerializer(BaseModelSerializer):
    id = serializers.CharField(read_only=True)
    user_id = serializers.CharField(required=False, allow_null=False)
    doc_id = serializers.IntegerField(required=True, allow_null=True)
    collection_type = serializers.ChoiceField(required=True, choices=Document.TypeChoices)
    collection_id = serializers.CharField(required=True, allow_null=False)
    title = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    abstract = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    authors = serializers.ListField(required=True, child=serializers.CharField(allow_blank=True), allow_null=True)
    doi = serializers.CharField(required=True, allow_null=True)
    categories = serializers.JSONField(required=True, allow_null=True)
    pages = serializers.IntegerField(required=False, allow_null=True, default=None)
    year = serializers.IntegerField(required=True, allow_null=True)
    pub_date = serializers.DateField(required=True, allow_null=True)
    pub_type = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    venue = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)  # todo rag 发布后有这个字段
    journal = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    conference = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    keywords = serializers.JSONField(required=True, allow_null=True)
    full_text_accessible = serializers.BooleanField(required=True, allow_null=True)
    citation_count = serializers.IntegerField(required=True, allow_null=True)
    reference_count = serializers.IntegerField(required=True, allow_null=True)
    state = serializers.ChoiceField(required=False, choices=Document.StateChoices)
    object_path = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    source_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    checksum = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    ref_collection_id = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    ref_doc_id = serializers.IntegerField(required=True, allow_null=True)

    class Meta:
        model = Document
        fields = ['id', 'doc_id', 'user_id', 'collection_type', 'collection_id', 'title', 'abstract', 'authors', 'doi',
                  'categories', 'pages', 'year', 'pub_date', 'pub_type', 'venue', 'journal', 'conference',
                  'keywords', 'full_text_accessible', 'citation_count', 'reference_count',
                  'state', 'object_path', 'source_url', 'checksum', 'ref_collection_id', 'ref_doc_id']


class DocumentRagGetSerializer(serializers.ModelSerializer):
    citations = serializers.JSONField(required=True, allow_null=True)
    references = serializers.JSONField(required=True, allow_null=True)

    class Meta:
        model = Document
        fields = ['id', 'doc_id', 'user_id', 'collection_type', 'collection_id', 'title', 'abstract', 'authors', 'doi',
                  'categories', 'pages', 'year', 'pub_date', 'pub_type', 'venue', 'journal', 'conference',
                  'keywords', 'full_text_accessible', 'citation_count', 'reference_count', 'citations', 'references',
                  'state', 'object_path', 'source_url', 'checksum', 'ref_collection_id', 'ref_doc_id']


class DocumentDetailSerializer(BaseModelSerializer):
    citations = serializers.SerializerMethodField()
    references = serializers.SerializerMethodField()

    @staticmethod
    def get_citations(obj: Document):
        if obj.collection_type == Document.TypeChoices.PERSONAL:
            if obj.ref_doc_id:
                citations = RagDocument.citations('public', obj.ref_collection_id, obj.ref_doc_id)
            else:
                citations = []
        else:
            citations = RagDocument.citations(obj.collection_type, obj.collection_id, obj.doc_id)
        if citations:
            ret_data = []
            for i, c in enumerate(citations):
                authors = ','.join(c['authors'])
                title = c['title']
                year = c['year']
                source = c['journal'] if c['journal'] else c['conference'] if c['conference'] else c['venue']
                doc_apa = f'[{i + 1}] {authors};{title}.{source} {year}'  # noqa
                ret_data.append({
                    'doc_id': c['doc_id'],
                    'doc_apa': doc_apa
                })
            return ret_data
        return None

    @staticmethod
    def get_references(obj: Document):
        if obj.collection_type == Document.TypeChoices.PERSONAL:
            if obj.ref_doc_id:
                references = RagDocument.references('public', obj.ref_collection_id, obj.ref_doc_id)
            else:
                references = []
        else:
            references = RagDocument.references(obj.collection_type, obj.collection_id, obj.doc_id)
        if references:
            ret_data = []
            for i, r in enumerate(references):
                authors = ','.join(r['authors'])
                title = r['title']
                year = r['year']
                source = r['journal'] if r['journal'] else r['conference'] if r['conference'] else r['venue']
                doc_apa = f'[{i + 1}] {authors};{title}.{source} {year}'  # noqa
                ret_data.append({
                    'doc_id': r['doc_id'],
                    'doc_apa': doc_apa
                })
            return ret_data
        return None

    class Meta:
        model = Document
        fields = '__all__'


class DocumentUrlResSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    url = serializers.CharField(required=True)


class GenPresignedUrlQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    filename = serializers.CharField(required=True, allow_blank=False, allow_null=False)


class DocumentLibraryListQuerySerializer(serializers.Serializer):
    class ListTypeChoices(models.TextChoices):
        ALL = 'all', _('all')
        IN_PROGRESS = 'in_progress', _('in_progress')
        COMPLETED = 'completed', _('completed')
        ERROR = 'error', _('error')
        FAILED = 'failed', _('failed')

    list_type = serializers.ChoiceField(required=False, choices=ListTypeChoices, default=ListTypeChoices.ALL)
    page_size = serializers.IntegerField(required=True)
    page_num = serializers.IntegerField(required=True)


class DocumentLibraryPersonalSerializer(serializers.Serializer):
    id = serializers.CharField(required=True, allow_null=True)
    filename = serializers.CharField(required=True)
    document_title = serializers.CharField(required=True)
    document_id = serializers.CharField(required=True, allow_null=True)
    pages = serializers.IntegerField(required=False, allow_null=True, default=None)
    record_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", allow_null=True)
    type = serializers.CharField(required=False, default=Collection.TypeChoices.PUBLIC)
    reference_type = serializers.CharField(required=False, allow_null=True, default=None)
    status = serializers.CharField(required=False, default='-')


class DocumentLibrarySubscribeSerializer(DocumentLibraryPersonalSerializer):
    bot_id = serializers.CharField(required=True)


class DocLibUpdateNameQuerySerializer(serializers.Serializer):
    filename = serializers.CharField(required=True, allow_null=False, allow_blank=False)


class DocLibAddQuerySerializer(serializers.Serializer):
    class AddTypeChoices(models.TextChoices):
        COLLECTION_ARXIV = 'collection_arxiv'
        COLLECTION_S2 = 'collection_s2'
        COLLECTION_SUBSCRIBE_FULL_TEXT = 'collection_subscribe_full_text'
        COLLECTION_DOCUMENT_LIBRARY = 'collection_document_library'
        COLLECTION_ALL = 'collection_all'
        DOCUMENT_SEARCH = 'document_search'

    document_ids = serializers.ListField(
        required=False, child=serializers.CharField(allow_null=False, allow_blank=False), default=None)
    collection_id = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    bot_id = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    add_type = serializers.ChoiceField(required=False, choices=AddTypeChoices, default=None)
    search_content = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)

    def validate(self, attrs):
        if (
            not attrs.get('add_type') and not attrs.get('document_ids')
            and not attrs.get('collection_id') and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('document_ids or collection_id or bot_id is required')
        if attrs.get('collection_id') and attrs.get('bot_id'):
            raise serializers.ValidationError('collection_id and bot_id cannot be set at the same time')
        if (
            attrs.get('add_type') and not attrs.get('collection_id')
            and not attrs.get('bot_id') and not attrs.get('search_content')
        ):
            raise serializers.ValidationError('collection_id or bot_id or search_content is required')

        if (
            attrs.get('add_type') == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_SUBSCRIBE_FULL_TEXT
            and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('bot_id is required')

        return attrs


class DocLibDeleteQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(
        required=False, allow_null=True, child=serializers.CharField(allow_null=False, allow_blank=False))
    is_all = serializers.BooleanField(required=False, default=False)
    # list_type = serializers.ChoiceField(required=True, choices=['all', 'in_progress', 'completed'], default='all')

    def validate(self, attrs):
        if attrs.get('ids'):
            attrs['ids'] = [i for i in attrs['ids'] if i]
        if not attrs.get('ids') and not attrs.get('is_all'):
            raise serializers.ValidationError('ids or is_all is required')
        return attrs


class DocLibCheckQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(
        required=False, allow_null=True, child=serializers.CharField(allow_null=True, allow_blank=False))
    is_all = serializers.BooleanField(required=False, default=False)
    list_type = serializers.ChoiceField(
        required=False, choices=['all', 'in_progress', 'completed'], default='all')

    def validate(self, attrs):
        if attrs.get('ids'):
            attrs['ids'] = [i for i in attrs['ids'] if i]
        if not attrs.get('ids') and not attrs.get('is_all'):
            raise serializers.ValidationError('ids or is_all is required')
        return attrs


class ImportPapersToCollectionSerializer(serializers.Serializer):
    collection_id = serializers.CharField(required=True)
    collection_type = serializers.ChoiceField(required=True, choices=['public', 'personal'])
    personal_collection_id = serializers.CharField(required=True)
    doc_ids = serializers.ListField(
        required=True, child=serializers.IntegerField(required=True, allow_null=False)
    )

    def validate(self, attrs):
        personal_collection_id = attrs.get('personal_collection_id')
        if not Collection.objects.filter(id=personal_collection_id).exists():
            raise serializers.ValidationError('personal_collection_id is not exist')

        return attrs
