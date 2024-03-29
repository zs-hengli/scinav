import logging

from django.conf import settings
from rest_framework import serializers

from document.models import Document

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class DocumentListSerializer(serializers.ModelSerializer):
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


class DocumentUpdateSerializer(BaseModelSerializer):
    doc_id = serializers.IntegerField(required=True)
    collection_type = serializers.ChoiceField(required=True, choices=Document.TypeChoices)
    collection_id = serializers.CharField(required=True)

    class Meta:
        model = Document
        fields = ['id', 'doc_id', 'title', 'collection_type', 'collection_id', 'updated_at', 'created_at']


class DocumentRagGetSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    user_id = serializers.CharField(required=False, allow_null=False)
    doc_id = serializers.IntegerField(required=True, allow_null=True)
    collection_type = serializers.ChoiceField(required=True, choices=Document.TypeChoices)
    collection_id = serializers.CharField(required=True, allow_null=False)
    title = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    abstract = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    authors = serializers.ListField(required=True, child=serializers.CharField(allow_blank=False), allow_null=True)
    doi = serializers.CharField(required=True, allow_null=True)
    categories = serializers.JSONField(required=True, allow_null=True)
    page_num = serializers.IntegerField(required=False, allow_null=True, default=None)
    year = serializers.IntegerField(required=True, allow_null=True)
    pub_date = serializers.DateField(required=True, allow_null=True)
    pub_type = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    venue = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)  # todo rag 发布后有这个字段
    journal = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    conference = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    keywords = serializers.JSONField(required=True, allow_null=True)
    is_open_access = serializers.BooleanField(required=True, allow_null=True)
    citation_count = serializers.IntegerField(required=True, allow_null=True)
    reference_count = serializers.IntegerField(required=True, allow_null=True)
    citations = serializers.JSONField(required=True, allow_null=True)
    references = serializers.JSONField(required=True, allow_null=True)
    state = serializers.ChoiceField(
        required=False, choices=Document.StateChoices, default=Document.StateChoices.COMPLETE)
    object_path = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    source_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    checksum = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    ref_collection_id = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    ref_doc_id = serializers.IntegerField(required=True, allow_null=True)

    class Meta:
        model = Document
        fields = ['id', 'doc_id', 'user_id', 'collection_type', 'collection_id', 'title', 'abstract', 'authors', 'doi',
                  'categories', 'page_num', 'year', 'pub_date', 'pub_type', 'venue', 'journal', 'conference',
                  'keywords', 'is_open_access', 'citation_count', 'reference_count', 'citations', 'references', 'state',
                  'object_path', 'source_url', 'checksum', 'ref_collection_id', 'ref_doc_id']


class DocumentDetailSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    @staticmethod
    def get_url(obj):
        return f'{settings.OBJECT_PATH_URL_HOST}/{obj.object_path}' if obj.object_path else None

    class Meta:
        model = Document
        fields = '__all__'


class DocumentUrlSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    url = serializers.SerializerMethodField()

    @staticmethod
    def get_url(obj):
        return f'{settings.OBJECT_PATH_URL_HOST}/{obj.object_path}' if obj.object_path else None

    class Meta:
        model = Document
        fields = ['id', 'url']