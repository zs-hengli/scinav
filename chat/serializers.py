import logging

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from bot.models import BotCollection, Bot, BotSubscribe
from chat.models import Conversation, Question, ConversationShare
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer
from document.models import Document

logger = logging.getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")


class ConversationCreateBaseSerializer(serializers.Serializer):
    documents = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    collections = serializers.ListField(required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    bot_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, min_length=32, max_length=36)
    model = serializers.ChoiceField(choices=Conversation.LLMModel, required=False, default=Conversation.LLMModel.BASIC)

    def validate(self, attrs):
        attrs['has_conversation'] = False
        if attrs.get('conversation_id'):
            attrs['has_conversation'] = True
            return attrs
        document_ids = []
        if attrs.get('documents'):
            document_ids = attrs['documents']
        is_bot = False
        if attrs.get('bot_id'):
            is_bot = True
            collections = BotCollection.objects.filter(bot_id=attrs['bot_id'], del_flag=False).values('collection_id').all()
            attrs['collections'] = [c['collection_id'] for c in collections]
        if attrs.get('collections'):
            collections = Collection.objects.filter(id__in=attrs['collections']).all()
            public_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
            personal_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]
            attrs['public_collection_ids'] = public_colls
            if not is_bot:
                collection_docs = CollectionDocument.objects.filter(
                    collection_id__in=personal_colls, del_flag=False).all()
                document_ids += [doc.document_id for doc in collection_docs]
                document_ids = list(set(document_ids))
        attrs['all_document_ids'] = document_ids
        return attrs

    @staticmethod
    def get_papers_info(user_id, bot_id, collection_ids, document_ids):
        documents = Document.objects.filter(id__in=document_ids).values(
            'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
            'ref_collection_id', 'ref_doc_id', 'object_path',
        ).all()
        return chat_paper_ids(
            user_id, documents,
            collection_ids=collection_ids,
            bot_id=bot_id,
        )

    @staticmethod
    def get_chat_type(validated_data):
        vd = validated_data
        bot = vd.get('bot_id')
        doc_ids = vd.get('doc_ids')
        collections = vd.get('collections')
        if bot:
            return Conversation.TypeChoices.BOT_COV
        elif doc_ids and not bot and not collections:
            if len(doc_ids) == 1:
                return Conversation.TypeChoices.DOC_COV
            else:
                return Conversation.TypeChoices.DOCS_COV
        elif collections and not bot and not doc_ids:
            if len(collections) == 1:
                return Conversation.TypeChoices.COLLECTION_COV
            else:
                return Conversation.TypeChoices.COLLECTIONS_COV
        elif doc_ids and collections:
            return Conversation.TypeChoices.MIX_COV
        else:
            return Conversation.TypeChoices.SIMPLE_COV


class ConversationCreateSerializer(ConversationCreateBaseSerializer):
    public_collection_ids = serializers.ListField(
        required=False, child=serializers.CharField(min_length=1), allow_empty=True)
    paper_ids = serializers.ListField(
        required=False, child=serializers.JSONField(), allow_empty=True, allow_null=True, default=list())
    question = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    share_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, min_length=32, max_length=36)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if (
            not attrs.get('documents')
            and not attrs.get('collections')
            and not attrs.get('bot_id')
            and not attrs.get('share_id')
        ):
            raise serializers.ValidationError('documents, collections, bot_id, share_id are all empty')
        if attrs.get('question'):
            attrs['content'] = attrs['question']
        return attrs


class ConversationUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, min_length=1, max_length=128, allow_blank=True, trim_whitespace=False)
    collections = serializers.ListField(
        required=False, child=serializers.CharField(min_length=1), allow_null=True)
    model = serializers.ChoiceField(choices=Conversation.LLMModel, required=False, default=None)

    def validate(self, attrs):
        if attrs.get('collections') is None and not attrs.get('title') and not attrs.get('model'):
            raise serializers.ValidationError('collections, title, model are all empty')
        if attrs.get('title') and len(attrs['title']) > 128:
            attrs['title'] = attrs['title'][:128]
        return attrs


class ConversationDetailSerializer(BaseModelSerializer):
    questions = serializers.SerializerMethodField()
    stop_chat_type = serializers.SerializerMethodField(default=None)
    sharer = serializers.SerializerMethodField()

    @staticmethod
    def get_questions(obj: Conversation):
        return None
        # filter_query = Q(del_flag=False) & (Q(source='share') | (~Q(answer='') & Q(answer__isnull=False)))
        # query_set = obj.question.filter(filter_query).order_by('-updated_at')
        # return QuestionListSerializer(query_set[0:10], many=True).data[::-1]

    @staticmethod
    def get_stop_chat_type(obj: Conversation):
        if obj.type == Conversation.TypeChoices.BOT_COV and obj.bot_id:
            bot = Bot.objects.filter(id=obj.bot_id).first()
            if bot and bot.del_flag:
                return 'bot_deleted'
        return None

    @staticmethod
    def get_sharer(obj: Conversation):
        if obj.share_id:
            conv_share = ConversationShare.objects.filter(id=obj.share_id).first()
            sharer_user = conv_share.user
            if conv_share:
                return {
                    'id': sharer_user.id,
                    # 'avatar': sharer_user.avatar,
                    'nickname': sharer_user.nickname,
                    'email': sharer_user.email,
                    'phone': sharer_user.phone,
                    'register_source': sharer_user.register_source,
                }
        return None

    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'user_id', 'bot_id', 'model', 'documents', 'collections', 'type', 'questions',
            'stop_chat_type', 'sharer'
        ]


class ConversationListSerializer(BaseModelSerializer):
    last_used_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'last_used_at', 'bot_id', 'model']


class ChatQuerySerializer(ConversationCreateBaseSerializer):
    conversation_id = serializers.CharField(required=False, min_length=32, max_length=36)
    question_id = serializers.CharField(required=False, min_length=32, max_length=36)
    content = serializers.CharField(required=True, min_length=1, max_length=4096)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if (
            not attrs.get('conversation_id')
            and not attrs.get('documents')
            and not attrs.get('collections')
            and not attrs.get('bot_id')
        ):
            raise serializers.ValidationError('conversation_id, documents, collections, bot_id are all empty')
        if attrs.get('conversation_id'):
            if not Conversation.objects.filter(id=attrs['conversation_id']).exists():
                raise serializers.ValidationError(f"conversation_id: {attrs['conversation_id']} is not exists")
        return attrs


class QuestionListQuerySerializer(serializers.Serializer):
    page_num = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=10)


class QuestionReferenceSerializer(serializers.Serializer):
    bbox = serializers.JSONField(required=True, allow_null=True)
    doc_id = serializers.CharField(required=True, min_length=1, max_length=36)
    citation_id = serializers.CharField(required=True, min_length=1, max_length=36)
    content_type = serializers.CharField(required=False, min_length=1, max_length=64)
    collection_id = serializers.CharField(required=True, min_length=1, max_length=36)
    collection_type = serializers.CharField(required=False, min_length=1, max_length=36)
    title = serializers.CharField(required=False, min_length=1, max_length=1024)
    authors = serializers.JSONField(required=False)


class QuestionListSerializer(serializers.ModelSerializer):
    references = serializers.SerializerMethodField()

    @staticmethod
    def get_references(obj: Question):
        data = []
        if obj.stream and obj.stream.get('output'):
            data = [QuestionReferenceSerializer(o).data for o in obj.stream['output'] if 'bbox' in o]
            # for i, d in enumerate(data):
            #     data[i]['doc_apa'] = d.get('title', '')
            # papers = {}
            # data = update_chat_references(data)
        return data

    class Meta:
        model = Question
        fields = [
            'id', 'content', 'answer', 'model', 'input_tokens', 'output_tokens', 'is_like', 'references', 'source']


class QuestionAnswerSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    question_id = serializers.CharField(required=True, min_length=32, max_length=36)
    is_like = serializers.BooleanField(required=True)

    def validate(self, attrs):
        question = Question.objects.filter(id=attrs['question_id']).exists()
        if not question:
            raise serializers.ValidationError(f"question not found, question_id: {attrs['question_id']}")
        attrs['question'] = question
        return attrs

    def save(self, validated_data):
        effect_count = Question.objects.filter(id=validated_data['question_id']).update(
            is_like=validated_data['is_like'])
        return effect_count


class QuestionUpdateAnswerQuerySerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True, max_length=36)
    question_id = serializers.CharField(required=False, max_length=36)
    conversation_id = serializers.CharField(required=False, max_length=36)
    answer = serializers.CharField(required=True, trim_whitespace=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('conversation_id') and not attrs.get('question_id'):
            raise serializers.ValidationError('conversation_id and question_id are all empty')
        if attrs.get('question_id') and not Question.objects.filter(
            id=attrs['question_id'], conversation__user_id=attrs['user_id']
        ).exists():
            raise serializers.ValidationError(f"question not found, question_id: {attrs['question_id']}")
        if attrs.get('conversation_id') and not Conversation.objects.filter(
            id=attrs['conversation_id'], user_id=attrs['user_id']
        ).exists():
            raise serializers.ValidationError(f"conversation not found, conversation_id: {attrs['conversation_id']}")
        return attrs

    @staticmethod
    def update_answer(validated_data):
        vd = validated_data
        answer = vd['answer']
        question_id = vd.get('question_id')
        conversation_id = vd.get('conversation_id')
        if not question_id:
            if question := Question.objects.filter(conversation_id=conversation_id).order_by('-updated_at').first():
                question.answer = answer
                question.is_stop = True
                question.save()
        else:
            Question.objects.filter(id=question_id).update(answer=answer, is_stop=True)
        return True


class ConversationsMenuQuerySerializer(serializers.Serializer):
    class ListTypeChoices(models.TextChoices):
        ALL = 'all', _('all')
        NO_BOT = 'no_bot', _('not include bot conversation')

    list_type = serializers.ChoiceField(required=False, choices=ListTypeChoices, default=ListTypeChoices.ALL)


def chat_paper_ids(user_id, documents, collection_ids=None, bot_id=None):
    ret_data, org_documents, ref_text_accessible_ds, is_sub = [], documents, [], False
    bot = None
    if bot_id:
        bot = Bot.objects.filter(id=bot_id).first()
        if not bot: return []
        if bot.user_id == user_id or BotSubscribe.objects.filter(user_id=user_id, bot_id=bot_id).exists():
            is_sub = True
        if not documents:
            document_ids = CollectionDocument.objects.filter(
                collection_id__in=collection_ids, del_flag=False).values_list('document_id', flat=True)
            if bot.user_id != user_id:
                filter_query = Q(id__in=document_ids.all(), collection_type=Document.TypeChoices.PUBLIC)
            else:
                filter_query = Q(id__in=document_ids.all())
            documents = Document.objects.filter(filter_query).values(
                'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
                'ref_collection_id', 'ref_doc_id', 'object_path',
            ).all()

    query_set, doc_lib_document_ids, sub_bot_document_ids, ref_ds = \
        CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'personal&subscribe_full_text', bot)
    full_text_documents = doc_lib_document_ids

    # 订阅专题会话 获取 full_text_documents
    if bot and is_sub and user_id != bot.user_id:
        full_text_documents += sub_bot_document_ids
        documents = [d for d in documents if d['collection_type'] == 'public']
        if ref_ds and is_sub:
            ref_documents = Document.objects.filter(id__in=ref_ds).values(
                'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
                'ref_collection_id', 'ref_doc_id', 'object_path',
            ).all()
            documents += list(ref_documents)
            # 订阅了专题广场里面的非本人专题
            if bot.type == Bot.TypeChoices.PUBLIC or bot.advance_share:
                ref_text_accessible_ds = [
                    rd['id'] for rd in ref_documents for d in org_documents
                    if rd['doc_id'] == d['ref_doc_id'] and d['full_text_accessible']
                ]
            # 订阅了非专题广场里面的非本人专题
            else:
                ref_text_accessible_ds = [
                    rd['id'] for rd in ref_documents if rd['id'] in doc_lib_document_ids
                ]
            full_text_documents += ref_text_accessible_ds
    elif not bot and collection_ids:
        is_self_coll = Collection.objects.filter(id=collection_ids[0], user_id=user_id).exists()
        document_ids = CollectionDocument.objects.filter(
            collection_id__in=collection_ids, del_flag=False).values_list('document_id', flat=True)
        if not is_self_coll:
            filter_query = Q(id__in=document_ids.all(), collection_type=Document.TypeChoices.PUBLIC)
            if ref_ds:
                filter_query |= Q(id__in=ref_ds, collection_type=Document.TypeChoices.PUBLIC)
        else:
            filter_query = Q(id__in=document_ids.all())
        documents = Document.objects.filter(filter_query,).values(
            'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
            'ref_collection_id', 'ref_doc_id', 'object_path',
        ).all()
    # 非本人个人文献 转为关联公共文献
    other_personal_documents = [
        d for d in documents if d['collection_type'] == 'personal' and d['collection_id'] != user_id
    ]
    ref_docs = [{'id': None, 'collection_id': d['ref_collection_id'], 'doc_id': d['ref_doc_id']}
                for d in other_personal_documents if d['ref_doc_id'] and d['ref_collection_id']]
    if ref_docs:
        ref_documents_raw = Document.raw_by_docs(ref_docs, fileds='id')
        ref_document_ids = [d.id for d in ref_documents_raw]
        if ref_document_ids:
            ref_documents = Document.objects.filter(id__in=ref_document_ids).values(
                'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
                'ref_collection_id', 'ref_doc_id', 'object_path',
            ).all()
            documents = list(documents) + list(ref_documents)

    for d in documents:
        if d['collection_type'] == 'personal' and d['collection_id'] != user_id:
            continue
        ret_data.append({
            'collection_type': d['collection_type'],
            'collection_id': d['collection_id'],
            'doc_id': d['doc_id'],
            'document_id': d['id'],
            'full_text_accessible': d['id'] in full_text_documents or d['collection_id'] == 'arxiv'
        })
    return ret_data


class ConversationShareQuestionSelectSerializer(serializers.Serializer):
    id = serializers.CharField(required=True, max_length=36)
    has_answer = serializers.BooleanField(required=False, default=True)
    has_question = serializers.BooleanField(required=False, default=True)


class ConversationShareCreateQuerySerializer(serializers.Serializer):
    conversation_id = serializers.CharField(required=True, max_length=36)
    selected_questions = ConversationShareQuestionSelectSerializer(required=False, many=True)
    is_all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('selected_questions') and not attrs.get('is_all'):
            raise serializers.ValidationError('selected_questions or is_all is required')
        return attrs


class ConversationShareListQuerySerializer(serializers.Serializer):
    page_num = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=10)


class ShareQuestionListSerializer(serializers.Serializer):
    id = serializers.CharField(required=True, max_length=36)
    content = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    answer = serializers.CharField(required=True, allow_null=True, allow_blank=True)
    model = serializers.CharField(required=True)
    references = serializers.JSONField(required=False, allow_null=True)


class ConversationShareDetailSerializer(BaseModelSerializer):
    # todo answers, questions
    questions = serializers.SerializerMethodField()
    sharer = serializers.SerializerMethodField()

    @staticmethod
    def get_questions(obj: ConversationShare):
        questions = obj.content['questions']
        # for question in questions:
        #     if question.get('references'):
        #         for i,ref in enumerate(question['references']):
        #             question['references'][i]['doc_apa'] = ref.get('title', '')
        # #         question['references'] = update_chat_references(question['references'])
        return questions

    @staticmethod
    def get_sharer(obj: ConversationShare):
        sharer_user = obj.user
        return {
            'id': sharer_user.id,
            'avatar': sharer_user.avatar,
            'nickname': sharer_user.nickname,
            'email': sharer_user.email,
            'phone': sharer_user.phone,
            'register_source': sharer_user.register_source,
        }

    class Meta:
        model = ConversationShare
        fields = [
            'id', 'user_id', 'bot_id', 'model', 'documents', 'collections', 'questions', 'sharer'
        ]


class ChatDocumentsTotalQuerySerializer(serializers.Serializer):
    bot_id = serializers.CharField(required=False, max_length=36)
    collections = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    collection_ids = serializers.ListField(required=False, child=serializers.CharField(max_length=36))

    def validate(self, attrs):
        if not attrs.get('bot_id') and not attrs.get('collections'):
            raise serializers.ValidationError('bot_id or collections is required')
        if attrs.get('collections'):
            attrs['collection_ids'] = attrs['collections'].split(',')
        return super().validate(attrs)
