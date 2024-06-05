import logging
from typing import Optional, List

from django.db import models
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers

from bot.models import BotCollection
from chat.models import Conversation
from collection.models import Collection, CollectionDocument

logger = logging.getLogger(__name__)


class ExceptionResponseSerializer(serializers.Serializer):
    error_code = serializers.IntegerField(help_text='Error code. 0 if successful, non-zero if not.')
    error_msg = serializers.CharField(help_text='Error message. empty if successful, error message if not.')
    request_id = serializers.CharField(help_text='Request id.')
    details = serializers.JSONField(required=False, help_text='Error details.')


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'content': 'Google Distributed System Architecture',
            'limit': 100,
        })
    ]
)
class SearchQuerySerializer(serializers.Serializer):
    content = serializers.CharField(
        required=True, max_length=1024,
        help_text='The query content based on which the search is performed. <br>'
                  'This could be `text`, `keywords`, or any other form of searchable content.')
    limit = serializers.IntegerField(
        min_value=1, max_value=1000, required=False, default=100,
        help_text='max records to return the search results'
    )


class PaperIdSerializer(serializers.Serializer):
    collection_type = serializers.CharField(max_length=36, help_text='Collection type.')
    collection_title = serializers.CharField(max_length=255, help_text='Title of the collection type.')
    collection_id = serializers.CharField(
        max_length=36, help_text='Identifier of the paper\'s source, like `arxiv` for public access '
                                 'or a `user_id` for personal collections.')
    doc_id = serializers.IntegerField(help_text='Globally unique paper identifier.')


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            "id": "97f9507e-7e00-4766-ad25-2ef089b0e362",
            "title": "Perceptual Assimilation and L2 Learning: Evidence from the Perception of Southern British "
                     "English Vowels by Native Speakers of Greek and Japanese",
            "abstract": "Abstract This study examined the extent to which previous experience with duration in first ",

            "authors": [
                "A. Lengeris"
            ],
            "pub_date": "2009-09-01",
            "citation_count": 49,
            "source": {
                'collection_type': 'public',
                'collection_title': 'Public Library',
                'collection_id': 's2',
                'doc_id': 94,
            },
            "venue": "Phonetica: International Journal of Phonetic Science",
            "doi": "10.1159/000235659",
            "categories": [
                "Linguistics",
                "Computer Science",
                "Medicine",
                "Psychology"
            ],
            "reference_formats": {
                "GB/T": "A. Lengeris. Perceptual Assimilation and L2 Learning: Evidence from the Perception of "
                        "Southern British English Vowels by Native Speakers of Greek and Japanese: Phonetica: "
                        "International Journal of Phonetic Science, 2009.",
                "MLA": "A. Lengeris. \"Perceptual Assimilation and L2 Learning: Evidence from the Perception of "
                       "Southern British English Vowels by Native Speakers of Greek and Japanese.\" Phonetica: "
                       "International Journal of Phonetic Science, 2009-09-01.",
                "APA": "A. Lengeris;Perceptual Assimilation and L2 Learning: Evidence from the Perception of Southern "
                       "British English Vowels by Native Speakers of Greek and Japanese.Phonetica: International "
                       "Journal of Phonetic Science 2009",
                "BibTex": "@article{RN01,\n    author=A. Generis,\n    title=Perceptual Assimilation and L2 Learning: "
                          "Evidence from the Perception of Southern British English Vowels by Native Speakers of "
                          "Greek and Japanese,\n    journal=Phonetica: International Journal of Phonetic Science,"
                          "\n    year=2009,\n    number=20\n}"
            },
        })
    ]
)
class SearchDocumentResultSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=36, help_text='Paper id.')
    title = serializers.CharField(required=False, max_length=512, help_text='Paper title.')
    abstract = serializers.CharField(required=False, help_text='Summary of the paper\'s content.')
    authors = serializers.ListField(
        required=False, child=serializers.CharField(max_length=128), help_text='List of paper authors.')
    pub_date = serializers.DateField(required=False, help_text='Publication date, formatted as `YYYY-MM-DD`.')
    citation_count = serializers.IntegerField(required=False, help_text='Number of citation', allow_null=True)
    source = PaperIdSerializer(required=False, help_text='Paper source identifier.')
    # collection_title = serializers.CharField(required=False, max_length=255, help_text='Title of the paper\'s source.')
    venue = serializers.CharField(
        required=False, max_length=32, help_text='the paper published at.(a journal or conference)', allow_null=True)
    doi = serializers.CharField(required=False, max_length=256, help_text='the paper doi', allow_null=True)
    categories = serializers.ListField(
        required=False, child=serializers.CharField(max_length=128), help_text='List of the paper relevant subject.'
    )
    reference_formats = serializers.JSONField(
        required=False, help_text='a Dictionary of formate references for the paper. key enum:[GB/T,MLA,APA,BibTex]')


class ChatResultSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=36, help_text='Paper id.')
    title = serializers.CharField(max_length=512, help_text='Paper title.')
    abstract = serializers.CharField(max_length=1024, help_text='Summary of the paper\'s content.')
    authors = serializers.ListField(
        required=False, child=serializers.CharField(max_length=128), help_text='List of paper authors.')
    pub_date = serializers.DateField(help_text='Publication date, formatted as `YYYY-MM-DD`.')
    citation_count = serializers.IntegerField(required=False, help_text='Number of citation', allow_null=True)
    reference_count = serializers.IntegerField(required=False, help_text='Number of references', allow_null=True)
    doc_id = serializers.IntegerField(help_text='Globally unique paper identifier.')
    collection_id = serializers.CharField(
        max_length=36, help_text='Identifier of the paper\'s source, like `arxiv` for public access '
                                 'or a `user_id` for personal collections.')
    type = serializers.CharField(
        max_length=32,
        help_text='Enum: [public, personal] Defines the paper\'s accessibility as either `public` or `personal`.'
    )
    collection_title = serializers.CharField(max_length=255, help_text='Title of the paper\'s source.')
    source = serializers.CharField(required=False, max_length=32, help_text='Source of the paper.', allow_null=True)
    reference_formats = serializers.JSONField(
        help_text='a Dictionary of formate references for the paper. key enum:[GB/T,MLA,APA,BibTex]')


class ChatResponseDataSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text='Total number of search results.')
    list = ChatResultSerializer(many=True, help_text='List of search results.')


class ChatStatisticsSerializer(serializers.Serializer):
    model_name = serializers.CharField(
        required=True,
        help_text='The model name, examples include gpt-3.5.turbo, gpt-4, and text-embedding-3-small.'
    )
    input_tokens = serializers.IntegerField(
        required=True, help_text='The total number of input tokens in a call')
    output_tokens = serializers.IntegerField(
        required=True, help_text='The total number of output tokens in a call')


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'object_path': 'scinav-personal-upload/6618f9172e18b95b4e73b496/i-dLEQ-104291857.pdf',
            'task_id': 'd5d24036-43e7-4b32-993f-e588ef5fb6d5',
        })
    ]
)
class UploadFileResponseSerializer(serializers.Serializer):
    object_path = serializers.CharField(help_text='The object path of the uploaded file.')
    task_id = serializers.CharField(help_text='The task id of the uploaded file.')


# TopicPlaza/MyTopic
@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'limit': 100,
        })
    ]
)
class TopicListRequestSerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=100,
        help_text='max records to return'
    )

@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'id': 'd5d24036-43e7-4b32-993f-e588ef5fb6d5',
            'author': 'E Weinan',
            'title': 'E Weinan\'s works',
            'description': 'E Weinan\'s Compilation of Papers',
            'updated_at': '2024-06-03 15:58:26',
            'created_at': '2024-04-09 09:30:28',
            'subscribed': True,
        })
    ]
)
class TopicListSerializer(serializers.Serializer):
    id = serializers.CharField(help_text='The id of the topic.')
    title = serializers.CharField(help_text='The title of the topic.')
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    author = serializers.CharField(required=False, help_text='The author of the topic.')
    description = serializers.CharField(required=False, help_text='The description of the topic.')
    subscribed = serializers.BooleanField(required=False, help_text='Whether the user is subscribed to the topic.')


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'status': 'all',
            'limit': 100,
        })
    ]
)
class PersonalLibraryRequestSerializer(serializers.Serializer):
    class ListTypeChoices(models.TextChoices):
        ALL = 'all', _('all personal paper libraries')
        IN_PROGRESS = 'in_progress', _('paper is parsing')
        COMPLETED = 'completed', _('paper parse completed')
        FAILED = 'failed', _('paper parse failed')
    limit = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=100,
        help_text='max records to return'
    )
    status = serializers.ChoiceField(
        required=False, choices=ListTypeChoices, default=ListTypeChoices.ALL,
        help_text='The status of the list.'
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'limit': 100,
        })
    ]
)
class CollectionListRequestSerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=100,
        help_text='max records to return'
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            "id": "f5d5f9ad-bdbc-4489-95fb-74867377c74e",
            "name": "collection name",
            "paper_ids": ["f59f83fd-a52e-4aa0-a8c9-0237f0de55e5", "ba8e29e9-63a1-4300-b934-ab01b32e127e"]
        })
    ]
)
class CollectionListSerializer(serializers.Serializer):
    id = serializers.CharField(help_text='The unique id of the collection.')
    name = serializers.CharField(source='title', help_text='The name of the collection.')
    paper_ids = serializers.SerializerMethodField(
        required=False, help_text='The list of paper ids in the collection.',
    )

    @staticmethod
    def get_paper_ids(obj: Collection) -> Optional[List[str]]:
        if obj.type == Collection.TypeChoices.PERSONAL:
            return list(CollectionDocument.objects.filter(
                collection_id=obj.id, del_flag=False).values_list('document_id', flat=True).all())
        else:
            return None

    class Meta:
        model = Collection
        fields = ['id', 'name', 'paper_ids']


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            "id": "f5d5f9ad-bdbc-4489-95fb-74867377c74e",
            "filename": "104291857.pdf(8)",
            "paper_title": "A Comparative Analysis Of Optimization And Generalization Properties Of Two-Layer Neural Network And Random Feature Models Under Gradient Descent Dynamics",
            "paper_id": "2917becd-a399-442a-85c2-f8429e1e9970",
            "pages": 30,
            "record_time": "2024-05-24 14:28:42",
            "type": "personal",
            "reference_type": "reference",
            "status": "completed"
        })
    ]
)
class DocumentLibraryPersonalSerializer(serializers.Serializer):
    id = serializers.CharField(
        required=True, allow_null=True,
        help_text='The id of the personal paper library',
    )
    filename = serializers.CharField(
        required=True,
        help_text='The filename of paper uploaded by person',
    )
    paper_title = serializers.CharField(
        required=True, allow_blank=True,
        help_text='The title of the personal paper library related paper',
    )
    paper_id = serializers.CharField(
        required=True, allow_null=True,
        help_text='The id of the personal paper library related paper',
    )
    record_time = serializers.DateTimeField(
        required=True, format="%Y-%m-%d %H:%M:%S", allow_null=True,
        help_text='The time when the personal paper library was added',
    )
    pages = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text='The number of pages of the personal paper library related paper',
    )
    type = serializers.CharField(
        required=False, default=Collection.TypeChoices.PERSONAL,
        help_text='The type of the personal paper library [`personal`, `public`] '
                  'personal if add to personal library manual, public if the paper is arxiv',
    )
    reference_type = serializers.CharField(
        required=False, allow_null=True, default=None,
        help_text='The type of the personal paper library reference in '
                  '[`public`, `reference`, `reference&full_text_accessible`]',
    )
    status = serializers.CharField(
        required=False, default=None,
        help_text='The status of the personal paper library in [`error`, `completed`, `in_progress`]',
    )


class PaperKnowledgeSerializer(serializers.Serializer):
    paper_ids = serializers.ListField(
        required=False, child=serializers.CharField(min_length=1), allow_empty=True,
        help_text='The list of paper ids to be processed by large language model.'
    )
    collection_ids = serializers.ListField(
        required=False, child=serializers.CharField(min_length=1), allow_empty=True,
        help_text='The list of collection ids to be processed by large language model.'
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample('Example', value={
            'content': 'public',
            'topic_id': ['d5d24036-43e7-4b32-993f-e588ef5fb6d5'],
            'paper_knowledge': {
                'paper_ids': ['d5d24036-43e7-4b32-993f-e588ef5fb6d5'],
                'collection_ids': ['s2', 'cb30a72f-7e41-43b6-8f63-4977779c1b59'],
            },
            'conversation_id': 'a7d51983-1828-4ccf-9808-d0a2aeb3e18c',
            'question_id': 'b0b8987b-a981-49e9-947b-f28476286c05',
            'model': 'gpt-4o',
        })
    ]
)
class ChatQuerySerializer(serializers.Serializer):
    content = serializers.CharField(
        required=True, min_length=1, max_length=4096,
        help_text='The `content` of the question to be processed by large language model.'
    )
    conversation_id = serializers.CharField(
        required=True, min_length=32, max_length=36,
        help_text='Unique identifier of the conversation. You can pass in a non-existent `conversation_id` to create a '
                  'conversation')
    topic_id = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, min_length=32, max_length=36,
        help_text='The id of the topic. If the `topic_id` is passed in, the `paper_knowledge` will be ignored.'
    )
    paper_knowledge = PaperKnowledgeSerializer(
        required=False, help_text='The paper knowledge of the conversation to be processed by large language model.')
    question_id = serializers.CharField(
        required=False, min_length=32, max_length=36,
        help_text='Unique identifier of one round of dialogue with the `conversation_id`. '
                  'If the `question_id` is passed in, the `paper_knowledge` and `topic_id` will be ignored.'
    )
    model = serializers.ChoiceField(
        choices=Conversation.LLMModel, required=False, default=Conversation.LLMModel.GPT_4O,
        help_text='Specify large language `model` name. Currently, only `gpt-4o` is available'
        # gpt-4o is currently open for access, but in the future, it will be restricted to advanced users only.
    )

    def validate(self, attrs):
        attrs['has_conversation'] = False
        if attrs.get('conversation_id'):
            if Conversation.objects.filter(id=attrs['conversation_id']).exists():
                attrs['has_conversation'] = True
                return attrs
        paper_ids = []
        if attrs.get('paper_knowledge') and attrs['paper_knowledge'].get('paper_ids'):
            paper_ids = attrs['paper_knowledge']['paper_ids']
        is_bot = False
        if attrs.get('topic_id'):
            is_bot = True
            collections = BotCollection.objects.filter(bot_id=attrs['topic_id'], del_flag=False).values(
                'collection_id').all()
            attrs['collection_ids'] = [c['collection_id'] for c in collections]
        if attrs.get('paper_knowledge') and attrs['paper_knowledge'].get('collection_ids'):
            collections = Collection.objects.filter(id__in=attrs['paper_knowledge']['collection_ids']).all()
            public_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
            personal_colls = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]
            attrs['public_collection_ids'] = public_colls
            if not is_bot:
                collection_docs = CollectionDocument.objects.filter(
                    collection_id__in=personal_colls, del_flag=False).all()
                paper_ids += [doc.document_id for doc in collection_docs]
                paper_ids = list(set(paper_ids))
        attrs['all_document_ids'] = paper_ids

        if (
            not attrs.get('paper_knowledge', {}).get('paper_ids')
            and not attrs.get('paper_knowledge', {}).get('collection_ids')
            and not attrs.get('topic_id')
        ):
            raise serializers.ValidationError(
                'topic_id、 paper_knowledge.paper_ids and paper_knowledge.collection_ids are all empty')
        return attrs


class ChatResponseSerializer(serializers.Serializer):
    class EventType(models.TextChoices):
        TOOL_START = 'tool_start', _('when the tool starts')
        TOOL_END = 'tool_end', _('when the tool ends ')
        MODEL_STREAM = 'model_stream', _('when the model is streaming')
        MODEL_STATISTICS = 'model_statistics', _('when the model ends, it will contain statistics information')
        ON_ERROR = 'on_error', _('execution error, if it is a model error, it will contain the token statistics '
                                 'that have been generated')
        CONVERSATION = 'conversation', _('when the conversation ends, it will contain the id and question_id')

    event = serializers.ChoiceField(required=True, choices=EventType.choices,help_text='')
    name = serializers.CharField(required=True, help_text='The name of the runnable that generated the event.')
    run_id = serializers.CharField(required=True, help_text='The run ID of the runnable that generated the event.')
    input = serializers.JSONField(
        required=False, allow_null=True,
        help_text='''
The input passed to the runnable that generated the event.
- The specific field content is determined by its Runnable'
- Inputs will sometimes be available at the *START* of the Runnable, and sometimes at the *END* of the Runnable.'
'''
    )
    output = serializers.JSONField(
        required=False, allow_null=True,
        help_text='''
The output of the Runnable that generated the event.
- Outputs will only be available at the *END* of the Runnable.
- The specific field content is determined by its Runnable 
- For most Runnables, this field can be inferred from the `chunk` field,
    though there might be some exceptions for special cased Runnables (e.g., like chat models), 
    which may return more information.
'''
    )
    statistics = ChatStatisticsSerializer(
        required=False,
        help_text='Model token usage statistics, including input and output Statistics will only be available '
                  'at the model_end and on_error when model is streaming'
    )
    id = serializers.CharField(required=False, help_text='The ID of the conversation when event is conversation.')
    question_id = serializers.CharField(
        required=False,
        help_text='The ID of the conversation question when event is conversation. When multiple questions are asked '
                  'in the same conversation, generate multiple questions and answers.'
    )
    metadata = serializers.JSONField(
        required=False, allow_null=True,
        help_text='Contains metadata for this event, including details like the session_id '
                  'and the executing user\'s user_id.'
    )
