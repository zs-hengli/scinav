import logging

from rest_framework import serializers
from django.db import models
from django.utils.translation import gettext_lazy as _

from bot.models import Bot, BotCollection, HotBot, BotTools

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class BotCreateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    author = serializers.CharField(required=True)
    title = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(allow_null=True, allow_blank=True)
    prompt_spec = serializers.CharField(allow_null=True, allow_blank=True)
    questions = serializers.ListField(child=serializers.CharField(min_length=1), allow_empty=True)
    collections = serializers.ListField(child=serializers.CharField(max_length=36, min_length=1), allow_empty=True)
    type = serializers.CharField(default=Bot.TypeChoices.PERSONAL)
    llm = serializers.JSONField(default=None, allow_null=True)
    tools = serializers.JSONField(default=None, allow_null=True)
    cover_url = serializers.CharField(default=None, allow_null=True)

    def validate(self, attrs):
        if attrs.get('author') and len(attrs['author']) > 128:
            attrs['author'] = attrs['author'][:128]
        if attrs.get('title') and len(attrs['title']) > 128:
            attrs['title'] = attrs['title'][:128]
        if attrs.get('description') and len(attrs['description']) > 255:
            attrs['description'] = attrs['description'][:255]
        if attrs.get('prompt_spec') and len(attrs['prompt_spec']) > 8000:
            attrs['prompt_spec'] = attrs['prompt_spec'][:8000]
        if attrs.get('questions'):
            for index, question in enumerate(attrs['questions']):
                if len(question) > 255:
                    attrs['questions'][index] = question[:255]
        return attrs

    @staticmethod
    def updated_attrs(instance: Bot, validated_data):
        attrs = []
        bot_collections = BotCollection.objects.filter(bot=instance, del_flag=False).all()
        for k, v in validated_data.items():
            if k == 'prompt_spec':
                if v != instance.prompt['spec']['system_prompt']:
                    instance.prompt['spec']['system_prompt'] = v
                    attrs.append(k)
            elif k == 'collections':
                collection_ids = [bc.collection_id for bc in bot_collections]
                if set(v) != set(collection_ids):
                    attrs.append(k)
            # elif k == 'tools':
            #     attrs.append(k)
            elif getattr(instance, k) != v:
                setattr(instance, k, v)
                attrs.append(k)
        return instance, bot_collections, attrs


class BotDetailSerializer(BaseModelSerializer):
    prompt_spec = serializers.SerializerMethodField()
    collections = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()

    @staticmethod
    def get_prompt_spec(obj: Bot):
        return obj.prompt.get('spec', {}).get('system_prompt', '')

    @staticmethod
    def get_collections(obj: Bot):
        bot_c = BotCollection.objects.filter(bot_id=obj.id, del_flag=False).all()
        return [bc.collection_id for bc in bot_c]

    @staticmethod
    def get_tools(obj: Bot):
        if not obj.tools or not isinstance(obj.tools, list):
            return None
        tool_ids = [t['id'] for t in obj.tools if t.get('id')]
        all_tools = BotTools.objects.filter(
            bot_id__in=tool_ids, del_flag=False, checked=True, user_id=obj.user_id).all()
        tools = []
        tools_dict = {t.id: t for t in all_tools}
        for t in obj.tools:
            if t['id'] in tools_dict:
                tools.append(tools_dict[t.id])
        return BotToolsDetailSerializer(obj.tools, many=True).data

    class Meta:
        model = Bot
        fields = [
            'id', 'user_id', 'author', 'title', 'description', 'prompt_spec', 'questions', 'collections',
            'tools', 'updated_at'
        ]


class HotBotListSerializer(BaseModelSerializer):
    title = serializers.SerializerMethodField()

    @staticmethod
    def get_title(obj: HotBot):
        return obj.bot.title

    class Meta:
        model = HotBot
        fields = ['bot_id', 'order_num', 'title', 'updated_at']


class BotListQuerySerializer(serializers.Serializer):
    class ListTypeChoices(models.TextChoices):
        ALL = 'all', _('all'),
        MY = 'my', _('my'),
        SUBSCRIBE = 'subscribe', _('subscribe'),
        CHAT_MENU = 'chat_menu', _('chat_menu')

    user_id = serializers.CharField(required=True, max_length=36)
    list_type = serializers.ChoiceField(required=False, choices=ListTypeChoices, default=ListTypeChoices.ALL)
    page_num = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=10)


class MyBotListAllSerializer(BaseModelSerializer):

    class Meta:
        model = Bot
        fields = ['id', 'author', 'title', 'description', 'updated_at', 'user_id']


class BotListAllSerializer(BaseModelSerializer):
    doc_total = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_total(obj):
        bot_collections = BotCollection.objects.filter(bot_id=obj.id, del_flag=False).all()
        return sum([bc.collection.total_public + bc.collection.total_personal for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'author', 'title', 'description', 'doc_total', 'updated_at', 'user_id']


class BotListMySerializer(BaseModelSerializer):
    doc_total = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_total(obj):
        bot_collections = BotCollection.objects.filter(bot_id=obj.id).all()
        return sum([bc.collection.total_public + bc.collection.total_personal for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'title', 'description', 'doc_total', 'updated_at']


class BotListChatMenuSerializer(BaseModelSerializer):

    class Meta:
        model = Bot
        fields = ['id', 'title', 'description', 'updated_at']


class BotDocumentsQuerySerializer(serializers.Serializer):
    list_type = serializers.ChoiceField(
        required=False,
        choices=[
            'all', 'all_documents', 'subscribe_full_text', 'arxiv', 's2', 'personal', 'document_library', 'public'
        ],
        default='all'
    )
    bot_id = serializers.CharField(required=False, max_length=36)
    page_num = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=10)

    def validate(self, attrs):
        if attrs.get('list_type') in ['subscribe_full_text', 'all_documents'] and not attrs.get('bot_id'):
            raise serializers.ValidationError(_('bot_id required'))
        return attrs


class BotToolsCreateQuerySerializer(serializers.Serializer):
    auth_type = serializers.ChoiceField(allow_null=True, choices=BotTools.AuthType, default=None)
    name = serializers.CharField(max_length=128, trim_whitespace=False, allow_blank=True)
    url = serializers.URLField(max_length=2048)
    openapi_json_path = serializers.CharField(required=False, max_length=1024, default=None)
    username_password_base64 = serializers.CharField(required=False, allow_null=True, default=None)
    token = serializers.CharField(required=False, allow_null=True, default=None)
    api_key = serializers.CharField(required=False, default=None)
    custom_header = serializers.CharField(required=False, allow_null=True, max_length=128, default=None)
    endpoints = serializers.JSONField(required=False, default=None)

    def validate(self, attrs):
        if attrs.get('name'):
            attrs['name'] = attrs['name'][:128]
        if attrs.get('openapi_json_path'):
            attrs['openapi_json_path'] = attrs['openapi_json_path'][:1024]
        attrs['endpoints'] = None
        if attrs.get('auth_type'):
            if attrs['auth_type'] == 'basic':
                if not attrs.get('username_password_base64'):
                    raise serializers.ValidationError(_('username_password_base64 required'))
                attrs['endpoints'] = {
                    'type': attrs['auth_type'],
                    'username_and_passwd_b64': attrs['username_password_base64']
                }
            elif attrs['auth_type'] == 'bearer':
                if not attrs.get('token'):
                    raise serializers.ValidationError(_('token required'))
                attrs['endpoints'] = {
                    'type': attrs['auth_type'],
                    'token': attrs['token']
                }
            else:
                if not attrs.get('api_key'):
                    raise serializers.ValidationError(_('api_key required'))
                if not attrs.get('custom_header'):
                    attrs['custom_header'] = 'X-API-KEY'
                attrs['endpoints'] = {
                    'type': attrs['auth_type'],
                    'api_key': attrs['api_key'],
                    'custom_header': attrs['custom_header']
                }
        return attrs


class BotToolsUpdateQuerySerializer(BotToolsCreateQuerySerializer):
    id = serializers.CharField(required=True, max_length=36)


class BotToolsDetailSerializer(BaseModelSerializer):

    class Meta:
        model = BotTools
        fields = [
            'id', 'bot_id', 'name', 'url', 'openapi_json_path', 'auth_type',
            'username_password_base64', 'token', 'api_key', 'custom_header',
        ]


class BotToolsDeleteQuerySerializer(serializers.Serializer):
    id = serializers.CharField(required=True, max_length=36)