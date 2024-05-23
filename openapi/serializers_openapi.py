import logging

from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from bot.models import Bot
from bot.serializers import BotListAllSerializer
from document.serializers import DocumentLibraryPersonalSerializer

logger = logging.getLogger(__name__)


class BaseResponseSerializer(serializers.Serializer):
    code = serializers.IntegerField(help_text='Response code. 0 if successful, non-zero if not.')
    msg = serializers.CharField(help_text='Response message. empty if successful, error message if not.')


class SearchDocumentResultSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=36, help_text='Paper id.')
    title = serializers.CharField(max_length=512, help_text='Paper title.')
    abstract = serializers.CharField(max_length=1024, help_text='Summary of the paper\'s content.')
    authors = serializers.ListField(
        required=False, child=serializers.CharField(max_length=128), help_text='List of paper authors.')
    pub_date = serializers.DateField(help_text='Publication date, formatted as `YYYY-MM-DD`.')
    citation_count = serializers.IntegerField(required=False, help_text='Number of citation', allow_null=True)
    reference_count = serializers.IntegerField(required=False, help_text='Number of references', allow_null=True)
    doc_id = serializers.IntegerField(help_text='Globally unique document identifier.')
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


class SearchResponseDataSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text='Total number of search results.')
    list = SearchDocumentResultSerializer(many=True, help_text='List of search results.')


class SearchResponseSerializer(BaseResponseSerializer):
    data = SearchResponseDataSerializer(help_text='Response data.', required=False)


class ChatResultSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=36, help_text='Paper id.')
    title = serializers.CharField(max_length=512, help_text='Paper title.')
    abstract = serializers.CharField(max_length=1024, help_text='Summary of the paper\'s content.')
    authors = serializers.ListField(
        required=False, child=serializers.CharField(max_length=128), help_text='List of paper authors.')
    pub_date = serializers.DateField(help_text='Publication date, formatted as `YYYY-MM-DD`.')
    citation_count = serializers.IntegerField(required=False, help_text='Number of citation', allow_null=True)
    reference_count = serializers.IntegerField(required=False, help_text='Number of references', allow_null=True)
    doc_id = serializers.IntegerField(help_text='Globally unique document identifier.')
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
        required=False, help_text='The ID of the conversation question when event is conversation.'
    )
    metadata = serializers.JSONField(
        required=False, allow_null=True,
        help_text='Contains metadata for this event, including details like the session_id '
                  'and the executing user\'s user_id.'
    )


class UploadFileResponseSerializer(BaseResponseSerializer):
    data = serializers.JSONField(help_text='The data of the response.', default={})


# TopicPlaza/MyTopic
class TopicPlazaRequestSerializer(serializers.Serializer):
    page_size = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=10,
        help_text='number of records per page'
    )
    page_num = serializers.IntegerField(
        min_value=1, required=False, default=1,
        help_text='page number begin with 1'
    )


class TopicPlazaListDetailSerializer(serializers.Serializer):
    id = serializers.CharField(help_text='The id of the topic.')
    author = serializers.CharField(help_text='The author of the topic.')
    title = serializers.CharField(help_text='The title of the topic.')
    description = serializers.CharField(help_text='The description of the topic.')
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    subscribed = serializers.BooleanField(help_text='Whether the user is subscribed to the topic.')


class TopicPlazaDataSerializer(serializers.Serializer):
    list = TopicPlazaListDetailSerializer(many=True)
    total = serializers.IntegerField()


class TopicPlazaResponseSerializer(BaseResponseSerializer):
    data = TopicPlazaDataSerializer(help_text='The data of the response.')


# PersonalLibrary
class PersonalLibraryRequestSerializer(serializers.Serializer):
    class ListTypeChoices(models.TextChoices):
        ALL = 'all', _('all personal document libraries')
        IN_PROGRESS = 'in_progress', _('paper is parsing')
        COMPLETED = 'completed', _('paper parse completed')
        FAILED = 'failed', _('paper parse failed')
    page_size = serializers.IntegerField(
        min_value=1, max_value=2000, required=False, default=10,
        help_text='number of records per page'
    )
    page_num = serializers.IntegerField(
        min_value=1, required=False, default=1,
        help_text='page number begin with 1'
    )
    list_type = serializers.ChoiceField(
        required=False, choices=ListTypeChoices, default=ListTypeChoices.ALL,
        help_text='The type of the list.'
    )


class PersonalLibraryDataSerializer(serializers.Serializer):
    list = DocumentLibraryPersonalSerializer(many=True)
    total = serializers.IntegerField()


class PersonalLibraryResponseSerializer(BaseResponseSerializer):
    data = PersonalLibraryDataSerializer(help_text='The data of the response.')

