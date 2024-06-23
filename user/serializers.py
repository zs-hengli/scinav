from rest_framework import serializers


class UserSyncQuerySerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    registerSource = serializers.ListSerializer(required=True, child=serializers.CharField())
