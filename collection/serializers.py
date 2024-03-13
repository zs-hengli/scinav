import logging

from rest_framework import serializers

from collection.models import Collection

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class CollectionCreateSerializer(BaseModelSerializer):
    title = serializers.CharField(required=True)
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    type = serializers.ChoiceField(choices=Collection.TypeChoices.choices, default=Collection.TypeChoices.PERSONAL)

    def create(self, validated_data):
        validated_data['title'] = validated_data['title'][:255]
        return Collection.objects.create(**validated_data)

    class Meta:
        model = Collection
        fields = '__all__'


class CollectionUpdateSerializer(BaseModelSerializer):
    title = serializers.CharField(required=True)

    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title[:255])
        instance.save()
        return instance

    class Meta:
        model = Collection
        fields = ['id', 'title', 'updated_at']


class CollectionDetailSerializer(BaseModelSerializer):

    class Meta:
        model = Collection
        fields = ['id', 'title', 'updated_at', 'total_public', 'total_personal']


class CollectionListSerializer(serializers.ModelSerializer):

    class Meta:
        model = Collection
        fields = ['id', 'title', 'updated_at']
