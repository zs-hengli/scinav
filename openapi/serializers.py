import logging

from rest_framework import serializers

from openapi.models import OpenapiKey

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(required=False, format="%Y-%m-%d %H:%M:%S")


class OpenapiKeyCreateQuerySerializer(serializers.Serializer):
    title = serializers.CharField(
        required=True, allow_null=False, allow_blank=True, help_text='Title of the openapi key.')

    def validate(self, attrs):
        if attrs.get('title'):
            attrs['title'] = attrs['title'][:128]
        return attrs


class OpenapiKeyUpdateQuerySerializer(OpenapiKeyCreateQuerySerializer):
    id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return attrs


class OpenapiKeyDetailSerializer(BaseModelSerializer):

    class Meta:
        model = OpenapiKey
        fields = ['id', 'title', 'api_key_show', 'updated_at', 'created_at']


class OpenapiKeyCreateDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    title = serializers.CharField(required=True)
    api_key = serializers.CharField(required=True)
    api_key_show = serializers.CharField(required=True)
    updated_at = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S")
    created_at = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S")


class OpenapiListQuerySerializer(serializers.Serializer):
    page_size = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=10,
        help_text='number of records per page'
    )
    page_num = serializers.IntegerField(
        min_value=1, required=False, default=1,
        help_text='page number begin with 1'
    )
