import logging

from rest_framework import serializers

from bot.models import Bot, BotCollection, HotBot

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class BotDetailSerializer(serializers.ModelSerializer):
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

        fields = ['id', 'author', 'title', 'description', 'prompt_spec', 'questions', 'collections']


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
        return sum([bc.collection.total for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'author', 'title', 'description', 'doc_total', 'updated_at']


class BotListMySerializer(BaseModelSerializer):
    doc_total = serializers.SerializerMethodField()

    @staticmethod
    def get_doc_total(obj):
        bot_collections = BotCollection.objects.filter(bot_id=obj.id).all()
        return sum([bc.collection.total for bc in bot_collections])

    class Meta:
        model = Bot
        fields = ['id', 'title', 'description', 'doc_total', 'updated_at']
