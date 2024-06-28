import datetime
import logging
import os

from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from collection.models import Collection
from document.models import Document, DocumentLibrary

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class SearchQuerySerializer(serializers.Serializer):
    class OrderBy(models.TextChoices):
        RELEVANCY = 'relevancy', _('relevancy')
        PUB_DATE = 'pub_date', _('pub_date')
    content = serializers.CharField(required=True, max_length=4096, allow_blank=True, trim_whitespace=False)
    page_size = serializers.IntegerField(default=10)
    page_num = serializers.IntegerField(default=1)
    limit = serializers.IntegerField(default=100)
    begin_date = serializers.CharField(required=False, default=None, allow_blank=True)
    end_date = serializers.CharField(required=False, default=None, allow_blank=True)
    order_by = serializers.ChoiceField(required=False, choices=OrderBy.choices, default=OrderBy.RELEVANCY)
    sources = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=1024), default=None)
    authors = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=512), default=None)

    def validate(self, attrs):
        year = datetime.datetime.now().year
        if attrs.get('begin_date'):
            mini_year = 1900
            max_year = 2099
            mini_date = datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
            try:
                attrs['begin_date'] = datetime.datetime.strptime(attrs.get('begin_date'), '%Y-%m-%d').date()
                if attrs['begin_date'].year < mini_year:
                    attrs['begin_date'] = mini_date
                elif attrs['begin_date'].year > max_year:
                    attrs['begin_date'] = datetime.datetime.strptime(
                        f'{year}-01-01', '%Y-%m-%d').date()
            except:
                attrs['begin_date'] = mini_date

        if attrs.get('end_date'):
            try:
                attrs['end_date'] = datetime.datetime.strptime(attrs.get('end_date'), '%Y-%m-%d').date()
            except:
                attrs['end_date'] = datetime.datetime.strptime(f'{year}-12-31', '%Y-%m-%d').date()
        return super().validate(attrs)


class SearchDocuments4AddQuerySerializer(serializers.Serializer):
    content = serializers.CharField(required=False, max_length=4096, allow_blank=True, trim_whitespace=False)
    author_id = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(default=None)
    begin_date = serializers.CharField(required=False, default=None, allow_blank=True)
    end_date = serializers.CharField(required=False, default=None, allow_blank=True)
    sources = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=1024), default=None)
    authors = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=512), default=None)

    def validate(self, attrs):
        # if attrs.get('content') is None and not attrs.get('author_id'):
        #     raise serializers.ValidationError('content and author_id cannot be empty at the same time')
        if attrs.get('content') is not None and not attrs.get('limit'):
            attrs['limit'] = 100
        if attrs.get('author_id') and not attrs.get('limit'):
            attrs['limit'] = 1000

        year = datetime.datetime.now().year
        if attrs.get('begin_date'):
            mini_year = 1900
            max_year = 2099
            mini_date = datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
            try:
                attrs['begin_date'] = datetime.datetime.strptime(attrs.get('begin_date'), '%Y-%m-%d').date()
                if attrs['begin_date'].year < mini_year:
                    attrs['begin_date'] = mini_date
                elif attrs['begin_date'].year > max_year:
                    attrs['begin_date'] = datetime.datetime.strptime(
                        f'{year}-01-01', '%Y-%m-%d').date()
            except:
                attrs['begin_date'] = mini_date

        if attrs.get('end_date'):
            try:
                attrs['end_date'] = datetime.datetime.strptime(attrs.get('end_date'), '%Y-%m-%d').date()
            except:
                year = datetime.datetime.now().year
                attrs['end_date'] = datetime.datetime.strptime(f'{year}-12-31', '%Y-%m-%d').date()

        return super().validate(attrs)


class AuthorsSearchQuerySerializer(serializers.Serializer):
    content = serializers.CharField(required=True, max_length=4096, allow_blank=True, trim_whitespace=False)
    page_size = serializers.IntegerField(default=10)
    page_num = serializers.IntegerField(default=1)
    limit = serializers.IntegerField(default=100)


class AuthorsDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    name = serializers.CharField(required=True, max_length=512)
    aliases = serializers.ListField(required=True, child=serializers.CharField(required=False, max_length=512))
    affiliations = serializers.ListField(required=True, child=serializers.CharField(required=False, max_length=512))
    paper_count = serializers.IntegerField(required=True)
    citation_count = serializers.IntegerField(required=True)
    h_index = serializers.IntegerField(required=True)


class AuthorsDocumentsQuerySerializer(serializers.Serializer):
    page_size = serializers.IntegerField(default=10)
    page_num = serializers.IntegerField(default=1)
    limit = serializers.IntegerField(default=1000)
    begin_date = serializers.DateField(required=False, default=None)
    end_date = serializers.DateField(required=False, default=None)
    order_by = serializers.ChoiceField(
        required=False, choices=SearchQuerySerializer.OrderBy.choices, default=SearchQuerySerializer.OrderBy.RELEVANCY)
    sources = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=1024), default=None)
    authors = serializers.ListSerializer(
        required=False, child=serializers.CharField(required=False, max_length=512), default=None)


class DocumentApaListSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        return obj.get_csl_formate('apa')
        # source = obj.journal if obj.journal else obj.conference if obj.conference else obj.venue
        # return Document.get_doc_apa(obj.authors, obj.year, obj.title, source)

    class Meta:
        model = Document
        fields = ['id', 'collection_id', 'doc_id', 'doc_apa', 'title']


class DocumentApcReadListSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        return obj.get_csl_formate('apa')
        # source = obj.journal if obj.journal else obj.conference if obj.conference else obj.venue
        # return Document.get_doc_apa(obj.authors, obj.year, obj.title, source)

    class Meta:
        model = Document
        fields = ['id', 'collection_id', 'doc_id', 'doc_id', 'doc_apa', 'title', 'full_text_accessible', 'object_path',
                  'ref_collection_id', 'ref_doc_id']


class CollectionDocumentListCollectionSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        return obj.get_csl_formate('apa')
        # source = obj.journal if obj.journal else obj.conference if obj.conference else obj.venue
        # return Document.get_doc_apa(obj.authors, obj.year, obj.title, source)

    @staticmethod
    def get_type(obj: Document):
        if obj.collection_type == Document.TypeChoices.PUBLIC:
            return obj.collection_id
        else:
            return obj.collection_type

    class Meta:
        model = Document
        fields = ['id', 'collection_id', 'doc_id', 'doc_apa', 'title', 'type']


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


class DocumentUploadResultSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentLibrary
        fields = ['id', 'object_path', 'task_id', 'task_status']


class DocumentRagCreateSerializer(BaseModelSerializer):
    id = serializers.CharField(read_only=True)
    user_id = serializers.CharField(required=False, allow_null=False)
    doc_id = serializers.IntegerField(required=True, allow_null=True)
    collection_type = serializers.ChoiceField(required=True, choices=Document.TypeChoices)
    collection_id = serializers.CharField(required=True, allow_null=False)
    title = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    abstract = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    authors = serializers.ListField(required=True, child=serializers.CharField(allow_blank=True), allow_null=True)
    author_names_ids = serializers.ListField(
        required=True, child=serializers.JSONField(allow_null=True), allow_null=True)
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
        fields = ['id', 'doc_id', 'user_id', 'collection_type', 'collection_id', 'title', 'abstract',
                  'authors', 'author_names_ids', 'doi',
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

    @staticmethod
    def get_document_library_status(user_id, document_id):
        document_library = DocumentLibrary.objects.filter(
            user_id=user_id, document_id=document_id, del_flag=False).first()
        status = None
        if document_library:
            status = (
                'completed' if document_library.task_status == DocumentLibrary.TaskStatusChoices.COMPLETED
                else 'in_progress' if document_library.task_status in [
                    DocumentLibrary.TaskStatusChoices.PENDING,
                    DocumentLibrary.TaskStatusChoices.QUEUEING,
                    DocumentLibrary.TaskStatusChoices.IN_PROGRESS
                ] else 'failed'
            )
        return status

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
    keyword = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)


class DocumentLibraryPersonalSerializer(serializers.Serializer):
    id = serializers.CharField(
        required=True, allow_null=True,
        help_text='The id of the personal document library',
    )
    filename = serializers.CharField(
        required=True,
        help_text='The filename of document uploaded by person',
    )
    document_title = serializers.CharField(
        required=True, allow_blank=True,
        help_text='The title of the personal document library related paper',
    )
    document_id = serializers.CharField(
        required=True, allow_null=True,
        help_text='The id of the personal document library related paper',
    )
    record_time = serializers.DateTimeField(
        required=True, format="%Y-%m-%d %H:%M:%S", allow_null=True,
        help_text='The time when the personal document library was added',
    )
    pages = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text='The number of pages of the personal document library related paper',
    )
    type = serializers.CharField(
        required=False, default=Collection.TypeChoices.PERSONAL,
        help_text='The type of the personal document library [`personal`, `public`] '
                  'personal if add to personal library manual, public if the paper is arxiv',
    )
    reference_type = serializers.CharField(
        required=False, allow_null=True, default=None,
        help_text='The type of the personal document library reference in '
                  '[`public`, `reference`, `reference&full_text_accessible`]',
    )
    status = serializers.CharField(
        required=False, default=None,
        help_text='The status of the personal document library in [`error`, `completed`, `in_progress`]',
    )


class DocumentLibrarySubscribeSerializer(DocumentLibraryPersonalSerializer):
    bot_id = serializers.CharField(required=True)


class DocLibUpdateNameQuerySerializer(serializers.Serializer):
    filename = serializers.CharField(required=True, allow_null=False, allow_blank=False, trim_whitespace=False)


class DocLibAddQuerySerializer(serializers.Serializer):
    class AddTypeChoices(models.TextChoices):
        COLLECTION_ARXIV = 'collection_arxiv'
        COLLECTION_S2 = 'collection_s2'
        COLLECTION_SUBSCRIBE_FULL_TEXT = 'collection_subscribe_full_text'
        COLLECTION_DOCUMENT_LIBRARY = 'collection_document_library'
        COLLECTION_ALL = 'collection_all'
        DOCUMENT_SEARCH = 'document_search'
        AUTHOR_SEARCH = 'author_search'

    document_ids = serializers.ListField(
        required=False, child=serializers.CharField(allow_null=False, allow_blank=False), default=None)
    collection_id = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    bot_id = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    add_type = serializers.ChoiceField(required=False, choices=AddTypeChoices, default=None)
    search_content = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    author_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    keyword = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    search_limit = serializers.IntegerField(required=False, default=100)
    search_info = SearchDocuments4AddQuerySerializer(required=False, default=None)

    def validate(self, attrs):
        if (
            not attrs.get('add_type') and not attrs.get('document_ids')
            and not attrs.get('collection_id') and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('document_ids or collection_id or bot_id is required')

        if attrs.get('collection_id') and attrs.get('bot_id'):
            raise serializers.ValidationError('collection_id and bot_id cannot be set at the same time')

        if (
            attrs.get('add_type') and not attrs.get('collection_id') and not attrs.get('bot_id')
            and not attrs.get('search_content') and not attrs.get('author_id')
        ):
            raise serializers.ValidationError('collection_id or bot_id or search_content is required')

        if (
            attrs.get('add_type') == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_SUBSCRIBE_FULL_TEXT
            and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('bot_id is required')

        if attrs.get('search_content'):
            if not attrs.get('search_info'):
                attrs['search_info'] = {}
            attrs['search_info']['content'] = attrs['search_content']
            attrs['search_info']['limit'] = attrs.get('limit', 100)

        if attrs.get('author_id'):
            if not attrs.get('search_info'):
                attrs['search_info'] = {}
            attrs['search_info']['author_id'] = attrs['author_id']
            attrs['search_info']['limit'] = attrs.get('limit', 1000)

        return super().validate(attrs)


class DocLibDeleteQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(
        required=False, allow_null=True, child=serializers.CharField(allow_null=False, allow_blank=False))
    # is_all = serializers.BooleanField(required=False, default=False)
    list_type = serializers.ChoiceField(
        required=False, choices=DocumentLibraryListQuerySerializer.ListTypeChoices, default=None)

    def validate(self, attrs):
        if attrs.get('ids'):
            attrs['ids'] = [i for i in attrs['ids'] if i]
        if not attrs.get('ids') and not attrs.get('list_type'):
            raise serializers.ValidationError('ids or list_type is required')
        return attrs


class DocLibCheckQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(
        required=False, allow_null=True, child=serializers.CharField(allow_null=True, allow_blank=False))
    is_all = serializers.BooleanField(required=False, default=False)
    list_type = serializers.ChoiceField(
        required=False, choices=['all', 'in_progress', 'completed', 'failed'], default='all')
    keyword = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

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
