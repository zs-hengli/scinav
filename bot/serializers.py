import logging

from rest_framework import serializers

from bot.models import Bot, BotCollection, HotBot

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class BotCreateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    author = serializers.CharField(required=True)
    title = serializers.CharField(required=True)
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
        if attrs.get('description') and len(attrs['description']) > 128:
            attrs['description'] = attrs['description'][:128]
        if attrs.get('prompt_spec') and len(attrs['prompt_spec']) > 128:
            attrs['prompt_spec'] = attrs['prompt_spec'][:128]
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
            elif getattr(instance, k) != v:
                setattr(instance, k, v)
                attrs.append(k)
            # todo llm tools id updated
        return instance, bot_collections, attrs


class BotDetailSerializer(BaseModelSerializer):
    prompt_spec = serializers.SerializerMethodField()
    collections = serializers.SerializerMethodField()

    @staticmethod
    def get_prompt_spec(obj: Bot):
        return obj.extension['spec'].get('prompt', {}).get('spec', {}).get('system_prompt', '')

    @staticmethod
    def get_collections(obj: Bot):
        bot_c = BotCollection.objects.filter(bot_id=obj.id, del_flag=False).all()
        return [bc.collection_id for bc in bot_c]

    class Meta:
        model = Bot

        fields = ['id', 'author', 'title', 'description', 'prompt_spec', 'questions', 'collections', 'updated_at']


class HotBotListSerializer(BaseModelSerializer):
    title = serializers.SerializerMethodField()

    @staticmethod
    def get_title(obj: HotBot):
        return obj.bot.title

    class Meta:
        model = HotBot
        fields = ['bot_id', 'order_num', 'title', 'updated_at']


class BotListAllSerializer(BaseModelSerializer):
    doc_total = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_total(obj):
        bot_collections = BotCollection.objects.filter(bot_id=obj.id).all()
        return sum([bc.collection.total_public + bc.collection.total_personal for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'author', 'title', 'description', 'doc_total', 'updated_at']


class BotListMySerializer(BaseModelSerializer):
    doc_total = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_total(obj):
        bot_collections = BotCollection.objects.filter(bot_id=obj.id).all()
        return sum([bc.collection.total_public + bc.collection.total_personal for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'title', 'description', 'doc_total', 'updated_at']
