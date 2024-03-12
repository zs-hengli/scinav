import logging

from rest_framework import serializers

from collection.models import Collection

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class CollectionListSerializer(serializers.ModelSerializer):

    class Meta:
        model = Collection
        # fields = ['id']
        fields = '__all__'


class CollectionDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = Collection
        # fields = ['id']
        fields = '__all__'
