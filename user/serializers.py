from rest_framework import serializers

from user.models import MyUser


class UserSyncQuerySerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    registerSource = serializers.ListSerializer(required=True, child=serializers.CharField())
    photo = serializers.CharField(required=False, max_length=4096)


class UserSyncRespSerializer(serializers.ModelSerializer):

    class Meta:
        model = MyUser
        fields = ['id', 'nickname', 'email', 'phone', 'is_superuser', 'date_joined']
