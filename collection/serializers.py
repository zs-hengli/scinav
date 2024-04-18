import json
import logging

from django.core.cache import cache
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from rest_framework import serializers

from bot.models import BotCollection
from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash
from document.models import Document, DocumentLibrary

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class CollectionCreateByDocsSerializer(serializers.Serializer):
    doc_ids = serializers.ListField(required=True, child=serializers.CharField(min_length=32, max_length=36))
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)
    doc_titles = serializers.ListField(required=False, child=serializers.CharField(max_length=255))

    def validate(self, attrs):
        titles = Document.objects.filter(id__in=attrs['doc_ids']).values_list("title", flat=True).all()
        attrs['title'] = list(titles)
        return attrs


class CollectionCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False, source='title')
    document_ids = serializers.ListField(required=False, child=serializers.CharField(min_length=32, max_length=36))
    search_content = serializers.CharField(required=False)
    user_id = serializers.CharField(required=True, max_length=36)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)
    document_titles = serializers.ListField(required=False, child=serializers.CharField(max_length=255))
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('title') and not attrs.get('document_ids') and not attrs.get('search_content'):
            raise serializers.ValidationError(_('Please provide a name or document_ids or search_content'))
        if attrs.get('is_all') and not attrs.get('search_content'):
            raise serializers.ValidationError(_('Please provide a search_content'))
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]
        elif attrs.get('document_ids'):
            titles = Document.objects.filter(id__in=attrs['document_ids']).values_list("title", flat=True).all()
            attrs['document_titles'] = list(titles)

        return attrs

    class Meta:
        model = Collection
        fields = '__all__'


class CollectionCreateByDocLibSerializer(BaseModelSerializer):
    name = serializers.CharField(required=False, source='title')
    document_ids = serializers.ListField(required=False, child=serializers.CharField(min_length=32, max_length=36))
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('title') and not attrs.get('document_ids') and not attrs.get('search_content'):
            raise serializers.ValidationError(_('Please provide a name or document_ids or search_content'))
        if attrs.get('is_all') and not attrs.get('search_content'):
            raise serializers.ValidationError(_('Please provide a search_content'))
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]
        elif attrs.get('document_ids'):
            titles = Document.objects.filter(id__in=attrs['document_ids']).values_list("title", flat=True).all()
            attrs['document_titles'] = list(titles)

        return attrs

    class Meta:
        model = Collection
        fields = '__all__'


class CollectionUpdateSerializer(BaseModelSerializer):
    id = serializers.CharField(required=False)
    name = serializers.CharField(required=True, source='title')

    def validate(self, attrs):
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]
        return attrs

    class Meta:
        model = Collection
        fields = ['id', 'name', 'updated_at']


class CollectionPublicSerializer(serializers.ModelSerializer):
    id = serializers.CharField(required=True)
    title = serializers.CharField(required=True)
    user_id = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    type = serializers.CharField(required=True)
    total_public = serializers.IntegerField(required=True)
    updated_at = serializers.DateTimeField(required=True, format="%Y-%m-%dT%H:%M:%S")
    del_flag = serializers.BooleanField(required=True)

    def to_internal_value(self, data):
        ModelClass = self.Meta.model
        date_field = ModelClass._meta.get_field('updated_at')
        date_field.auto_now = False
        date_field.editable = True
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title)
        instance.updated_at = validated_data.get('updated_at', instance.updated_at)
        instance.del_flag = validated_data.get('del_flag', instance.del_flag)
        instance.total_public = validated_data.get('total_public', instance.total_public)
        instance.save()

    class Meta:
        model = Collection
        fields = ['id', 'title', 'user_id', 'type', 'total_public', 'updated_at', 'del_flag']


class CollectionDetailSerializer(BaseModelSerializer):
    name = serializers.CharField(source='title')
    total = serializers.SerializerMethodField()

    @staticmethod
    def get_total(obj):
        return obj.total_public + obj.total_personal

    class Meta:
        model = Collection
        fields = ['id', 'name', 'updated_at', 'total']


class CollectionSubscribeSerializer(serializers.Serializer):
    id = serializers.CharField(required=True, allow_null=True)
    bot_id = serializers.CharField(required=True)
    name = serializers.CharField(required=True)
    updated_at = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S")
    total = serializers.IntegerField(required=True)
    type = serializers.CharField(required=False, default=Collection.TypeChoices.PUBLIC)

    class Meta:
        fields = ['id', 'bot_id', 'name', 'total', 'updated_at', 'type']


class CollectionRagPublicListSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    name = serializers.CharField(required=True)
    updated_at = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S")
    total = serializers.IntegerField(required=True)
    type = serializers.CharField(required=False, default=Collection.TypeChoices.PUBLIC)

    class Meta:
        fields = ['id', 'name', 'total', 'updated_at', 'type']


class CollectionListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='title')
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    total = serializers.SerializerMethodField()

    @staticmethod
    def get_total(obj):
        return obj.total_public + obj.total_personal

    class Meta:
        model = Collection
        fields = ['id', 'name', 'total', 'updated_at', 'type']


class CollectionDeleteQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    ids = serializers.ListField(
        required=False, child=serializers.CharField(required=True, max_length=36, min_length=1)
    )
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs.get('ids'):
            attrs['ids'] = [cid for cid in attrs['ids'] if cid]
        if not attrs.get('ids') and not attrs.get('is_all'):
            raise serializers.ValidationError(f"ids and is_all {_('cannot be empty at the same time')}")
        return attrs


class CollectionDocUpdateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    collection_id = serializers.CharField(required=True, max_length=36, min_length=36)
    document_ids = serializers.ListField(
        required=False, child=serializers.CharField(required=True, max_length=36, min_length=36)
    )
    is_all = serializers.BooleanField(required=False, default=False)
    action = serializers.ChoiceField(required=False, choices=['add', 'delete'], default='add')
    search_content = serializers.CharField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if not attrs.get('document_ids') and not attrs.get('is_all'):
            raise serializers.ValidationError(f"document_ids and is_all {_('cannot be empty at the same time')}")
        if attrs.get('is_all') and attrs.get('action') == 'add' and not attrs.get('search_content'):
            raise serializers.ValidationError("search_content required")
        return attrs

    def create(self, validated_data):
        vd = validated_data
        instances = []
        if vd.get('is_all'):
            doc_search_redis_key_prefix = 'doc:search'
            content_hash = str_hash(vd['search_content'])
            redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
            search_cache = cache.get(redis_key)
            if search_cache:
                all_cache = json.loads(search_cache)
                doc_ids = [c['id'] for c in all_cache]
                if vd.get('document_ids'):
                    vd['document_ids'] = list(set(doc_ids) - set(vd['document_ids']))
                else:
                    vd['document_ids'] = doc_ids
        created_num, updated_num = 0, 0
        updated_num = CollectionDocument.objects.filter(
            collection_id=vd['collection_id'], document_id__in=vd['document_ids'], del_flag=True).update(del_flag=False)
        d_lib = DocumentLibrary.objects.filter(
            user_id=vd['user_id'], del_flag=False, document_id__in=vd['document_ids']
        ).values_list('document_id', flat=True)
        for d_id in validated_data.get('document_ids', []):
            cd_data = {
                'collection_id': validated_data['collection_id'],
                'document_id': d_id,
                'full_text_accessible': d_id in d_lib,  # todo v1.0 默认都有全文 v2.0需要考虑策略
            }
            collection_document, created = (CollectionDocument.objects.update_or_create(
                cd_data, collection_id=cd_data['collection_id'], document_id=cd_data['document_id']))
            instances.append({
                'collection_document': collection_document,
                'created': created,
            })
            if created:
                created_num += 1
        if created_num + updated_num:
            Collection.objects.filter(id=validated_data['collection_id']).update(
                total_personal=F('total_personal') + created_num + updated_num)
        return instances

    @staticmethod
    def delete_document(validated_data):
        vd = validated_data
        if vd.get('is_all'):
            total = len(vd.get('document_ids', []))
            if vd.get('document_id'):
                filter_query = (
                    Q(collection_id=vd['collection_id'], del_flag=False)
                    & ~Q(document_id__in=vd['document_ids'])
                )
                CollectionDocument.objects.filter(filter_query).update(del_flag=True)
            else:
                CollectionDocument.objects.filter(
                    collection_id=vd['collection_id'], del_flag=False
                ).update(del_flag=True)

            Collection.objects.filter(id=vd['collection_id']).update(total_personal=total, total_public=0)
        else:
            effect_num = CollectionDocument.objects.filter(
                collection_id=vd['collection_id'], document_id__in=vd['document_ids'], del_flag=False
            ).update(del_flag=True)
            Collection.objects.filter(id=vd['collection_id']).update(total_personal=F('total_personal') - effect_num)
        return validated_data

    @staticmethod
    def _update_bot_collections_doc_num(collection_id, num, action='update'):
        # todo update
        bot_collections = BotCollection.objects.filter(collection_id=collection_id, del_flag=False)
        bot_ids = [bc.bot_id for bc in bot_collections]
        if action == 'update':
            Collection.objects.filter(bot_id__in=bot_ids).update(total_public=F('total_public') + num)
        elif action == 'set':
            Collection.objects.filter(bot_id__in=bot_ids).update(total_public=num)
        return num


class CollectionDocumentListQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    collection_ids = serializers.ListField(
        required=False, child=serializers.CharField(max_length=36, min_length=1)
    )
    list_type = serializers.ChoiceField(
        required=False,
        choices=[
            'all', 'all_documents', 'public', 'arxiv', 's2', 'personal', 'document_library'
        ],
        default='all'
    )
    bot_id = serializers.CharField(required=False, max_length=36)
    page_size = serializers.IntegerField(required=False, default=10)
    page_num = serializers.IntegerField(required=False, default=1)


class CollectionDocumentListSerializer(serializers.Serializer):
    @staticmethod
    def get_collection_documents(user_id, collection_ids, list_type, bot=None):
        p_documents, p_document_num = [], 0
        if bot and user_id != bot.user_id:
            p_document_num, p_documents = bot_subscribe_personal_document_num(bot.user_id, bot_ids=[bot.id])
        doc_lib_document_ids, sub_bot_document_ids = None, None
        if list_type in ['all', 'all_documents']:
            filter_query = Q(collection_id__in=collection_ids, del_flag=False)
            if p_documents:
                filter_query &= ~Q(document_id__in=p_documents)
            query_set = CollectionDocument.objects.filter(filter_query).values('document_id') \
                .order_by('document_id').distinct()
        elif list_type == 'publish':
            query_set = CollectionDocument.objects.filter(
                collection_id__in=collection_ids, del_flag=False, document__collection_type=Document.TypeChoices.PUBLIC
            ).values('document_id').order_by('document_id').distinct()
        elif list_type == 'arxiv':
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            filter_query = \
                ~Q(document_id__in=document_ids) \
                & Q(collection_id__in=collection_ids, del_flag=False, document__collection_id='arxiv')
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 's2':
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            filter_query = ~Q(document_id__in=document_ids) \
                           & Q(collection_id__in=collection_ids, del_flag=False, document__collection_id='s2')
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 'subscribe_full_text':
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            bot_user = bot.user_id
            if bot_user == user_id:
                bot_document_ids = document_ids
            else:
                bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(bot_user)
            filter_query = (
                ~Q(document_id__in=document_ids)
                & Q(document_id__in=bot_document_ids)
                & Q(collection_id__in=collection_ids, del_flag=False)
            )
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 'personal&subscribe_full_text':
            doc_lib_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            bot_user = bot.user_id
            if bot_user == user_id:
                sub_bot_document_ids = doc_lib_document_ids
            else:
                sub_bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(bot_user)
            all_document_ids = doc_lib_document_ids + sub_bot_document_ids
            filter_query = (
                Q(document_id__in=all_document_ids)
                & Q(collection_id__in=collection_ids, del_flag=False)
            )
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()

        else:  # document_library personal
            # todo 订阅个人文件库处理
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            filter_query = Q(document_id__in=document_ids, collection_id__in=collection_ids, del_flag=False)
            if p_documents:
                filter_query &= ~Q(document_id__in=p_documents)
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        return query_set, doc_lib_document_ids, sub_bot_document_ids

    @staticmethod
    def _my_doc_lib_document_ids(user_id):
        """
        个人文件库 排队中 入库中 入库完成
        """
        doc_libs = DocumentLibrary.objects.filter(user_id=user_id, del_flag=False, task_status__in=[
            DocumentLibrary.TaskStatusChoices.COMPLETED,
            DocumentLibrary.TaskStatusChoices.PENDING,
            DocumentLibrary.TaskStatusChoices.QUEUEING,
        ]).values('document_id').all()
        my_documents = Document.objects.filter(collection_id=user_id).values('id').all()
        return [d['document_id'] for d in doc_libs] + [d['id'] for d in my_documents]


class CollectionCheckQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(required=False, child=serializers.CharField(), default=None)
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('is_all') and not attrs.get('ids'):
            raise serializers.ValidationError(_('ids or is_all must be set'))
        return attrs


class CollectionCreateBotCheckQuerySerializer(serializers.Serializer):
    ids = serializers.ListField(required=False, child=serializers.CharField(max_length=36, min_length=1), default=[])
    bot_id = serializers.CharField(required=False, max_length=36, min_length=1, default=None)

    def validate(self, attrs):
        if not attrs.get('bot_id') and not attrs.get('ids'):
            raise serializers.ValidationError(_('bot_id or ids must be set'))
        return attrs


def bot_subscribe_personal_document_num(bot_user_id, bot_collections=None, bot_ids=None):
    """
    订阅专题 包括的文献列表 个人上传文献没有关联id的记录个数
    """
    if bot_ids:
        bot_collections = BotCollection.objects.filter(
            bot_id__in=bot_ids, del_flag=False).order_by('bot_id', '-updated_at').all()
    collection_ids = [bc.collection_id for bc in bot_collections]
    coll_documents = CollectionDocument.objects.filter(
        collection_id__in=collection_ids, del_flag=False).values('document_id').all()
    personal_not_ref_doc_lib = DocumentLibrary.objects.filter(
        user_id=bot_user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED,
        document__ref_doc_id__isnull=True, filename__isnull=False
    ).values('document_id').distinct('document_id')
    personal_documents = Document.objects.filter(
        collection_id=bot_user_id, collection_type=Document.TypeChoices.PERSONAL,
        full_text_accessible__in=[False, None]).values('id').all()
    document_set = (
        set([cd['document_id'] for cd in coll_documents])
        & set([pd['document_id'] for pd in personal_not_ref_doc_lib] + [pd['id'] for pd in personal_documents])
    )
    return len(document_set), list(document_set)