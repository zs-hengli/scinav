import logging

from rest_framework import serializers

from document.models import Document

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class DocumentListSerializer(serializers.ModelSerializer):
    doc_apa = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_apa(obj: Document):
        # 作者1,作者2;标题.期刊 时间
        authors = ','.join(obj.authors)
        title = obj.title
        year = obj.year
        journal_or_conference = obj.journal if obj.journal else obj.conference if obj.conference else ''
        return f'{authors};{title}.{journal_or_conference} {year}'

    class Meta:
        model = Document
        fields = ['id', 'doc_apa']
