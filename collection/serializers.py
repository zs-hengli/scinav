import json
import logging

from django.db.models import F
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from bot.models import BotCollection, Bot
from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash
from document.models import Document, DocumentLibrary
from django.core.cache import cache

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
    author_id = serializers.IntegerField(required=False)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)
    document_titles = serializers.ListField(required=False, child=serializers.CharField(max_length=255))
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if (
            not attrs.get('title') and not attrs.get('document_ids')
            and not attrs.get('search_content') and not attrs.get('author_id')
        ):
            raise serializers.ValidationError(_('Please provide a name or document_ids or search_content'))
        if attrs.get('is_all') and not attrs.get('search_content') and not attrs.get('author_id'):
            raise serializers.ValidationError(_('Please provide a search_content or author_id'))
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]

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


class CollectionListQuerySerializer(serializers.Serializer):
    keyword = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    list_type = serializers.CharField(required=True)
    page_size = serializers.IntegerField(required=False, default=10)
    page_num = serializers.IntegerField(required=False, default=1)

    def validate(self, attrs):
        if attrs.get('list_type'):
            attrs['list_type'] = attrs['list_type'].split(',')
            all_types = ['my', 'public', 'subscribe']
            if set(attrs['list_type']) - set(all_types):
                raise serializers.ValidationError(_('list_type must be my, public, subscribe'))
        return attrs


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
    list_type = serializers.ChoiceField(
        required=False, choices=['s2', 'arxiv', 'document_library', 'all'], default=None)
    search_content = serializers.CharField(required=False, allow_null=True, default=None)
    author_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if not attrs.get('document_ids') and not attrs.get('is_all') and not attrs.get('list_type'):
            raise serializers.ValidationError(f"document_ids and list_type {_('cannot be empty at the same time')}")
        if (attrs.get('is_all') or attrs.get('list_type')
        ) and attrs.get('action') == 'add' and not attrs.get('search_content') and not attrs.get('author_id'):
            raise serializers.ValidationError("search_content or author_id required")
        return attrs

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
    keyword = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
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


class CollectionDocumentSelectedQuerySerializer(serializers.Serializer):
    collection_ids = serializers.ListField(
        required=False, child=serializers.CharField(max_length=36, min_length=1))
    bot_id = serializers.CharField(required=False, max_length=36)
    document_ids = serializers.ListField(
        required=False, child=serializers.CharField(max_length=36, min_length=1)
    )
    list_type = serializers.ChoiceField(
        required=True, choices=['all', 'arxiv', 's2', 'subscribe_full_text', 'document_library']
    )

    def validate(self, attrs):
        if not attrs.get('collection_ids') and not attrs.get('bot_id'):
            raise serializers.ValidationError(f"collection_id and bot_id {_('cannot be empty at the same time')}")
        if attrs.get('collection_ids'):
            if not Collection.objects.filter(id__in=attrs['collection_ids'], del_flag=False).exists():
                raise serializers.ValidationError(f"collection_id {_('does not exist')}")
        if attrs.get('bot_id'):
            if not Bot.objects.filter(id=attrs['bot_id'], del_flag=False).exists():
                raise serializers.ValidationError(f"bot_id {_('does not exist')}")
            filter_query = (
                Q(bot_id=attrs['bot_id'], del_flag=False)
                & ~Q(collection_id__in=['s2', 'arxiv'])
            )
            attrs['collection_ids'] = list(BotCollection.objects.filter(
                filter_query).values_list('collection_id', flat=True).all())
        return attrs


class CollectionDocumentListSerializer(serializers.Serializer):
    @staticmethod
    def get_collection_documents(user_id, collection_ids, list_type, bot=None):
        p_documents, ref_documents = [], []
        if bot and user_id != bot.user_id:
            p_documents, ref_documents = bot_subscribe_personal_document_num(bot.user_id, bot=bot)
        elif collection_ids:
            p_documents = collection_sub_personal_documents(user_id, collection_ids)
            if p_documents:
                ref_documents = get_ref_document_ids(p_documents)
        doc_lib_document_ids, sub_bot_document_ids = None, None
        if list_type in ['all', 'all_documents']:
            filter_query = Q(collection_id__in=collection_ids, del_flag=False)
            # 非本人专题，过滤个人没有关联文献的文件
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
            sub_bot_document_ids = []
            if bot and bot.type == Bot.TypeChoices.PUBLIC:
                sub_bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(
                    bot.user_id, is_self=False
                )
            document_ids = list(set(document_ids) | set(sub_bot_document_ids))
            if bot and user_id != bot.user_id and p_documents:
                document_ids = list(set(document_ids) | set(p_documents))
            filter_query = ~Q(document_id__in=document_ids) \
                           & Q(collection_id__in=collection_ids, del_flag=False, document__collection_id='arxiv')
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 's2':
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            sub_bot_document_ids = []
            if bot and bot.type == Bot.TypeChoices.PUBLIC:
                sub_bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(
                    bot.user_id, is_self=False
                )
            document_ids = list(set(document_ids) | set(sub_bot_document_ids))
            if bot and user_id != bot.user_id and p_documents:
                document_ids = list(set(document_ids) | set(p_documents))
            filter_query = ~Q(document_id__in=document_ids) \
                           & Q(collection_id__in=collection_ids, del_flag=False, document__collection_id='s2')
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 'subscribe_full_text':
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            if bot.user_id == user_id or (bot.user_id != user_id and bot and bot.type == Bot.TypeChoices.PERSONAL):
                bot_document_ids = document_ids
            else:
                bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(bot.user_id, is_self=False)
                if p_documents:
                    bot_document_ids = list(set(bot_document_ids) - set(p_documents))
            filter_query = (
                (~Q(document_id__in=document_ids) & Q(document_id__in=bot_document_ids))
                & Q(collection_id__in=collection_ids, del_flag=False)
            )
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        elif list_type == 'personal&subscribe_full_text':
            doc_lib_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            if not bot or bot.user_id == user_id or (
                bot.user_id != user_id and bot and bot.type == Bot.TypeChoices.PERSONAL):
                sub_bot_document_ids = doc_lib_document_ids
            else:
                sub_bot_document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(bot.user_id, False)
                if p_documents:
                    sub_bot_document_ids = list(set(sub_bot_document_ids) - set(p_documents))
            all_document_ids = doc_lib_document_ids + sub_bot_document_ids
            filter_query = Q(document_id__in=all_document_ids, del_flag=False)
            if collection_ids:
                filter_query &= Q(collection_id__in=collection_ids)
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()

        else:  # document_library personal
            # todo 订阅个人文件库处理
            document_ids = CollectionDocumentListSerializer._my_doc_lib_document_ids(user_id)
            filter_query = Q(document_id__in=document_ids, collection_id__in=collection_ids, del_flag=False)
            if p_documents:
                filter_query &= ~Q(document_id__in=p_documents)
            # if bot and bot.type == Bot.TypeChoices.PERSONAL:
            #     filter_query &= Q(document_id__in=p_documents)
            query_set = CollectionDocument.objects.filter(
                filter_query).values('document_id').order_by('document_id').distinct()
        return query_set, doc_lib_document_ids, sub_bot_document_ids, ref_documents

    @staticmethod
    def _my_doc_lib_document_ids(user_id, is_self=True):
        """
        个人文件库  本人：排队中 入库中 入库完成
            非本人： 入库完成
        """
        if not is_self:
            doc_libs = DocumentLibrary.objects.filter(
                user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
            ).values('document_id').all()
        else:
            doc_libs = DocumentLibrary.objects.filter(user_id=user_id, del_flag=False, task_status__in=[
                DocumentLibrary.TaskStatusChoices.COMPLETED,
                DocumentLibrary.TaskStatusChoices.PENDING,
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                DocumentLibrary.TaskStatusChoices.QUEUEING,
            ]).values('document_id').all()
        return [d['document_id'] for d in doc_libs if d['document_id']]


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

    # def validate(self, attrs):
    #     if not attrs.get('bot_id') and not attrs.get('ids'):
    #         raise serializers.ValidationError(_('bot_id or ids must be set'))
    #     return attrs


def bot_subscribe_personal_document_num(bot_user_id, bot_collections=None, bot=None):
    """
    订阅专题 个人文献id列表 个人上传文献关联的公共文献列表
    :return (个人文献id列表, 个人上传文献关联的公共文献列表)
    """
    bot_id = None
    if bot: bot_id = bot.id
    if bot_id:
        bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
    collection_ids = [bc.collection_id for bc in bot_collections]
    coll_documents = CollectionDocument.objects.filter(
        collection_id__in=collection_ids, del_flag=False).values('document_id').all()

    personal_doc_libs = DocumentLibrary.objects.filter(
        user_id=bot_user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED,
        filename__isnull=False, document__id__in=[d['document_id'] for d in coll_documents]
    ).values('document_id').distinct('document_id')

    # 个人上传文献关联的公共文献列表
    ref_document_ids = []
    personal_documents = Document.objects.filter(
        id__in=[pd['document_id'] for pd in personal_doc_libs]
    ).values('id', 'ref_collection_id', 'ref_doc_id').all()

    ref_docs = [{'id': None, 'collection_id': d['ref_collection_id'], 'doc_id': d['ref_doc_id']}
                for d in personal_documents if d['ref_doc_id'] and d['ref_collection_id']]
    if ref_docs:
        ref_documents = Document.raw_by_docs(ref_docs, fileds='id')
        ref_document_ids = [d.id for d in ref_documents]
    # 个人文献列表
    document_set = (
        set([cd['document_id'] for cd in coll_documents])
        & set([pd['document_id'] for pd in personal_doc_libs])
    )
    return list(document_set), ref_document_ids


def collection_sub_personal_documents(user_id, collection_ids) -> list:
    """
    非本人收藏夹列表中包括的个人文献id列表
    :param user_id:
    :param collection_ids:
    :return:
    """
    collection_ids = '\'' + '\', \''.join(collection_ids) + '\''
    sql = ("select d.id from collection_document cd "
           "left join document d on d.id = cd.document_id "
           "left join collection c on cd.collection_id=c.id "
           f"where cd.collection_id in ({collection_ids}) and cd.del_flag=false "
           f"and c.user_id != '{user_id}' and c.del_flag=false "
           f"and d.collection_type='personal'")
    result = Document.raw_sql(sql)
    document_ids = [d.id for d in result]
    return document_ids


def get_ref_document_ids(document_ids) -> list:
    document_ids = '\'' + '\', \''.join(document_ids) + '\''
    sql = ("select d.id from document d "
           "left join document dr on d.ref_collection_id=dr.collection_id and d.ref_doc_id=dr.doc_id "
           f"where d.id in ({document_ids})")
    result = Document.raw_sql(sql)
    ref_document_ids = [d.id for d in result]
    return ref_document_ids
