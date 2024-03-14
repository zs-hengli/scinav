import json
import logging

from django.utils.translation import gettext_lazy as _
from django.core.cache import cache

from rest_framework import serializers

from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class CollectionCreateSerializer(BaseModelSerializer):
    name = serializers.CharField(required=True, source='title')
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)

    def validate(self, attrs):
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]
        return attrs

    class Meta:
        model = Collection
        fields = '__all__'


class CollectionUpdateSerializer(BaseModelSerializer):
    name = serializers.CharField(required=True, source='title')

    def validate(self, attrs):
        if attrs.get('title') and len(attrs['title']) > 255:
            attrs['title'] = attrs['title'][:255]
        return attrs

    class Meta:
        model = Collection
        fields = ['id', 'name', 'updated_at']


class CollectionDetailSerializer(BaseModelSerializer):
    name = serializers.CharField(source='title')

    class Meta:
        model = Collection
        fields = ['id', 'name', 'updated_at', 'total_public', 'total_personal']


class CollectionListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='title')

    class Meta:
        model = Collection
        fields = ['id', 'name', 'updated_at']


class CollectionDocUpdateSerializer(serializers.Serializer):
    collection_id = serializers.CharField(required=True, max_length=36, min_length=36)
    document_ids = serializers.ListField(
        required=False, child=serializers.CharField(required=True, max_length=36, min_length=36)
    )
    is_all = serializers.BooleanField(required=False, default=False)
    search_content = serializers.CharField(required=False, default=None)

    def validate(self, attrs):
        if not attrs.get('document_ids') and not attrs.get('is_all'):
            raise serializers.ValidationError(f"document_ids and is_all {_('cannot be empty at the same time')}")
        if attrs.get('is_all') and not attrs.get('search_content'):
            raise serializers.ValidationError(f"search_content required")
        return attrs

    def create(self, validated_data):
        instances = []
        if not validated_data.get('document_ids') and validated_data.get('is_all'):
            doc_search_redis_key_prefix = 'doc:search'
            content_hash = str_hash(validated_data['search_content'])
            redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
            search_cache = cache.get(redis_key)
            if search_cache:
                all_cache = json.loads(search_cache)
                doc_ids = [c['id'] for c in all_cache]
                validated_data['document_ids'] = doc_ids
        for d_id in validated_data.get('document_ids', []):
            cd_data = {
                'collection_id': validated_data['collection_id'],
                'document_id': d_id,
            }
            collection_document, created = (CollectionDocument.objects.update_or_create(
                cd_data, collection_id=cd_data['collection_id'], document_id=cd_data['document_id']))
            instances.append({
                'collection_document': collection_document,
                'created': created,
            })
        return instances
