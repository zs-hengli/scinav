import logging

from rest_framework import serializers

from collection.models import Collection

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class CollectionCreateSerializer(BaseModelSerializer):
    name = serializers.CharField(required=True, source='title')
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)

    def create(self, validated_data):
        validated_data['title'] = validated_data['title'][:255]
        return Collection.objects.create(**validated_data)

    class Meta:
        model = Collection
        fields = '__all__'


class CollectionUpdateSerializer(BaseModelSerializer):
    name = serializers.CharField(required=True, source='title')

    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title[:255])
        instance.save()
        return instance

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
