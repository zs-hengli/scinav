from rest_framework import serializers

from customadmin.models import GlobalConfig


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class ConfigValueMemberLimitCheckSerializer(serializers.Serializer):
    limit_chat_daily = serializers.IntegerField(required=True)
    limit_chat_monthly = serializers.IntegerField(required=True)
    limit_embedding_daily = serializers.IntegerField(required=True)
    limit_embedding_monthly = serializers.IntegerField(required=True)
    limit_advanced_share = serializers.IntegerField(required=False, default=0)  # 高级分享个数配置


class ConfigValueMemberExchangeCheckSerializer(serializers.Serializer):
    days_30 = serializers.IntegerField(required=True)
    days_90 = serializers.IntegerField(required=True)
    days_360 = serializers.IntegerField(required=True)


class ConfigValueAwardCheckSerializer(serializers.Serializer):
    per = serializers.IntegerField(required=True)
    limit = serializers.IntegerField(required=True, allow_null=True)
    period_of_validity = serializers.IntegerField(required=False, default=0, allow_null=True)  # 有效期


class ConfigValueDurationAwardCheckSerializer(serializers.Serializer):
    duration = serializers.IntegerField(required=True, allow_null=True)
    per = serializers.IntegerField(required=True, allow_null=True)
    period_of_validity = serializers.IntegerField(required=False, default=0, allow_null=True)  # 有效期


class GlobalConfigPostQuerySerializer(serializers.Serializer):
    id = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    config_type = serializers.ChoiceField(required=False, choices=GlobalConfig.ConfigType)
    sub_type = serializers.ChoiceField(required=False, choices=GlobalConfig.SubType)
    value = serializers.JSONField(required=False)
    order = serializers.IntegerField(required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('config_type') and attrs.get('config_type') in [
            GlobalConfig.ConfigType.MEMBER_FREE, GlobalConfig.ConfigType.MEMBER_STANDARD,
            GlobalConfig.ConfigType.MEMBER_PREMIUM
        ]:
            if not attrs.get('sub_type') or attrs.get('sub_type') not in [
                GlobalConfig.SubType.LIMIT, GlobalConfig.SubType.EXCHANGE
            ]:
                raise serializers.ValidationError('sub_type is invalid must in [limit, exchange]')
            if attrs['sub_type'] == GlobalConfig.SubType.LIMIT:
                value_serial = ConfigValueMemberLimitCheckSerializer(data=attrs.get('value'))
            else:
                value_serial = ConfigValueMemberExchangeCheckSerializer(data=attrs.get('value'))
            if not value_serial.is_valid():
                raise serializers.ValidationError(value_serial.errors)

        # award
        if attrs.get('config_type') and attrs.get('config_type') == GlobalConfig.ConfigType.AWARD:
            if not attrs.get('sub_type') or attrs.get('sub_type') not in [
                GlobalConfig.SubType.SUBSCRIBED_BOT, GlobalConfig.SubType.INVITE_REGISTER,
                GlobalConfig.SubType.NEW_USER_AWARD, GlobalConfig.SubType.DURATION
            ]:
                raise serializers.ValidationError({
                    'sub_type': 'award config sub_type is invalid must in [subscribed_bot, invite_register, '
                                'new_user_award, duration_award]'
                })
            if attrs.get('sub_type') == GlobalConfig.SubType.DURATION:
                award_serial = ConfigValueDurationAwardCheckSerializer(data=attrs.get('value'))
                if not award_serial.is_valid():
                    errors = award_serial.errors
                    errors[f'{GlobalConfig.SubType.DURATION}.value'] = \
                        f'check error'
                    raise serializers.ValidationError(errors)
            else:
                award_serial = ConfigValueAwardCheckSerializer(data=attrs.get('value'))
                if not award_serial.is_valid():
                    raise serializers.ValidationError(award_serial.errors)
        return attrs


class GlobalConfigDetailSerializer(BaseModelSerializer):

    class Meta:
        model = GlobalConfig
        fields = ['id', 'name', 'config_type', 'sub_type', 'value', 'order', 'updated_at', 'created_at']
