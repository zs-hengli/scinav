import logging

from rest_framework import serializers

from chat.models import Conversation, Question
from collection.models import Collection, CollectionDocument
from document.models import Document

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    

class ConversationCreateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    documents = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    collections = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    bot_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, min_length=32, max_length=36)

    def validate(self, attrs):
        if (
            not attrs.get('documents')
            and not attrs.get('collections')
            and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('documents, collections, bot_id are all empty')
        document_ids = []
        if attrs.get('documents'):
            document_ids = attrs['documents']
        if attrs.get('collections'):
            collections = Collection.objects.filter(id__in=attrs['collections']).all()
            public_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
            personal_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]
            attrs['public_collection_ids'] = public_colls
            collection_docs = CollectionDocument.objects.filter(collection_id__in=personal_colls, del_flag=False).all()
            document_ids += [doc.document_id for doc in collection_docs]
            document_ids = list(set(document_ids))
        if document_ids:
            documents = Document.objects.filter(id__in=document_ids)\
                .values_list('id', 'collection_type', 'collection_id', 'doc_id', named=True).all()
            attrs['paper_ids'] = []
            for d in documents:
                attrs['paper_ids'].append({
                    'collection_type': d.collection_type,
                    'collection_id': d.collection_id,
                    'doc_id': d.doc_id,
                })
        return attrs

    @staticmethod
    def get_chat_type(validated_data):
        vd = validated_data
        bot = vd.get('bot_id')
        doc_ids = vd.get('doc_ids')
        collections = vd.get('collections')
        if bot and not doc_ids and not collections:
            return Conversation.TypeChoices.BOT_COV
        elif doc_ids and not bot and not collections:
            if len(doc_ids) == 1: return Conversation.TypeChoices.DOC_COV
            else: return Conversation.TypeChoices.DOCS_COV
        elif collections and not bot and not doc_ids:
            if len(collections) == 1: return Conversation.TypeChoices.COLLECTION_COV
            else: return Conversation.TypeChoices.COLLECTIONS_COV
        elif bot or doc_ids or collections:
            return Conversation.TypeChoices.MIX_COV
        else:
            return Conversation.TypeChoices.SIMPLE_COV


class ConversationUpdateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    title = serializers.CharField(required=True, min_length=1, max_length=128)

    def validate(self, attrs):
        if attrs.get('title') and len(attrs['title']) > 128:
            attrs['title'] = attrs['title'][:128]
        return attrs


class ConversationDetailSerializer(BaseModelSerializer):
    # todo answers, questions
    questions = serializers.SerializerMethodField()

    @staticmethod
    def get_questions(obj: Conversation):
        questions = obj.question.filter(del_flag=False).all()
        return QuestionConvDetailSerializer(questions, many=True).data

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'user_id', 'bot_id', 'documents', 'collections', 'type', 'questions']


class ConversationListSerializer(BaseModelSerializer):
    last_used_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'last_used_at']


class ChatQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    conversation_id = serializers.CharField(required=False, min_length=32, max_length=36)
    content = serializers.CharField(required=True, min_length=1, max_length=1024)

    documents = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    collections = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    bot_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, min_length=32, max_length=36)

    def validate(self, attrs):
        if (
            not attrs.get('conversation_id')
            and not attrs.get('documents')
            and not attrs.get('collections')
            and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('conversation_id, documents, collections, bot_id are all empty')
        document_ids = []
        if attrs.get('documents'):
            document_ids = attrs['documents']
        if attrs.get('collections'):
            collections = Collection.objects.filter(id__in=attrs['collections']).all()
            public_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
            personal_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]
            attrs['collections'] = public_colls
            collection_docs = CollectionDocument.objects.filter(collection_id__in=personal_colls, del_flag=False).all()
            document_ids += [doc.document_id for doc in collection_docs]
            document_ids = list(set(document_ids))
        if document_ids:
            documents = Document.objects.filter(id__in=document_ids)\
                .values_list('id', 'collection_type', 'collection_id', 'doc_id', named=True).all()
            attrs['documents'] = []
            for d in documents:
                attrs['documents'].append({
                    'collection_type': d.collection_type,
                    'collection_id': d.collection_id,
                    'doc_id': d.doc_id,
                })
        return attrs


class QuestionConvDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'content', 'answer', 'input_tokens', 'output_tokens', 'is_like']


class QuestionAnswerSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, min_length=32, max_length=36)
    question_id = serializers.CharField(required=True, min_length=32, max_length=36)
    is_like = serializers.BooleanField(required=True)

    def validate(self, attrs):
        question = Question.objects.filter(id=attrs['question_id']).exists()
        if not question:
            raise serializers.ValidationError(f"question not found, question_id: {attrs['question_id']}")
        attrs['question'] = question
        return attrs

    def save(self, validated_data):
        effect_count = Question.objects.filter(id=validated_data['question_id']).update(is_like=validated_data['is_like'])
        return effect_count
