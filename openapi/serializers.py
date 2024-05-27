import datetime
import logging

from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from chat.models import Conversation
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
        fields = ['id', 'title', 'api_key_show', 'updated_at', 'created_at', 'del_flag', ]


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
    is_all = serializers.BooleanField(required=False, default=False)
    is_used = serializers.BooleanField(required=False, default=None)


class UsageBaseSerializer(serializers.Serializer):
    class Schedule(models.TextChoices):
        WEEK = 'week', _('week')
        MONTH = 'month', _('month')
        QUARTER = 'quarter', _('quarter')
        YEAR = 'year', _('year')

    schedule_type = serializers.ChoiceField(choices=Schedule)
    openapi_key_id = serializers.CharField(default=None)

    @staticmethod
    def get_schedule_parts_info(schedule_type):
        now = datetime.datetime.now()
        if schedule_type == UsageBaseSerializer.Schedule.WEEK:
            parts = 7
            part_list = [(now - relativedelta(days=index)).strftime('%Y/%m/%d') for index in range(parts, -1, -1)]
            min_date = (now - relativedelta(days=parts)).strftime('%Y/%m/%d')
            info = [{
                'parts_num': parts,
                'part_list': part_list,
                'part_type': 'day',
                'min_date': min_date
            }]
        elif schedule_type == UsageBaseSerializer.Schedule.MONTH:
            parts = 30
            part_list = [(now - relativedelta(days=index)).strftime('%Y/%m/%d') for index in range(parts, -1, -1)]
            min_date = (now - relativedelta(days=parts)).strftime('%Y/%m/%d')
            info = [{
                'parts_num': parts,
                'part_list': part_list,
                'part_type': 'day',
                'min_date': min_date
            }]
        elif schedule_type == UsageBaseSerializer.Schedule.QUARTER:

            parts_day, parts_month = 90, 3
            part_list_day = [
                (now - relativedelta(days=index)).strftime('%Y/%m/%d') for index in range(parts_day, -1, -1)]
            part_list_month = [
                (now - relativedelta(months=index)).strftime('%Y/%m') for index in range(parts_month, -1, -1)]
            min_date_day = (now - relativedelta(days=parts_day)).strftime('%Y/%m/%d')
            min_date_month = (now - relativedelta(months=parts_month)).strftime('%Y/%m/%d')
            info = [{
                'parts_num': parts_day,
                'part_list': part_list_day,
                'part_type': 'day',
                'min_date': min_date_day
            },{
                'parts_num': parts_month,
                'part_list': part_list_month,
                'part_type': 'month',
                'min_date': min_date_month
            }]
        else:
            parts = 12
            part_list = [(now - relativedelta(months=index)).strftime('%Y/%m') for index in range(parts, -1, -1)]
            min_date = (now - relativedelta(months=parts)).strftime('%Y/%m/%d')
            info = [{
                'parts': parts,
                'part_list': part_list,
                'part_type': 'month',
                'min_date': min_date,
            }]
        return info


class UsageChatQuerySerializer(UsageBaseSerializer):
    model = serializers.ChoiceField(choices=Conversation.LLMModel, default=None)

