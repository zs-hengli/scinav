import logging
from operator import itemgetter

from django.db.models import Q

from bot.models import Bot, BotCollection
from bot.rag_service import Conversations as RagConversation
from bot.rag_service import Document as Rag_Document
from chat.service import update_simple_conversation
from collection.base_service import update_conversation_by_collection
from collection.models import Collection
from core.utils.common import cmp_ignore_order
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagCreateSerializer
from document.service import get_documents_by_rag, get_reference_formats
from document.tasks import async_update_document
from openapi.serializers_openapi import CollectionListSerializer

logger = logging.getLogger(__name__)


def search(user_id, content, topn=100):
    rag_ret = Rag_Document.search(user_id, content, limit=topn)
    rag_ret = DocumentRagCreateSerializer(rag_ret, many=True).data
    ret_data = []
    documents_dict = get_documents_by_rag(rag_ret)
    document_ids = [d.id for d in documents_dict.values()]
    for doc in rag_ret:
        data = DocumentRagCreateSerializer(doc).data
        data['id'] = str(documents_dict[f"{doc['collection_id']}-{doc['doc_id']}"].id)
        venue = (
            data['venue'] if data['venue'] else
            data['journal'] if data['journal'] else
            data['conference'] if data['conference'] else
            ''
        )
        document = Document(**data)
        ret_data.append({
            'id': data['id'],
            'title': data['title'],
            'abstract': data['abstract'],
            'authors': data['authors'],
            'pub_date': data['pub_date'],
            'citation_count': data['citation_count'],
            'venue': venue,
            'doi': data['doi'],
            'categories': data['categories'],
            'source': {
                'collection_type': data['collection_type'],
                'collection_id': str(data['collection_id']),
                'doc_id': data['doc_id'],
            },
            'reference_formats': get_reference_formats(document),
        })
    async_update_document.apply_async(args=[document_ids, rag_ret])
    return ret_data


def collection_list_mine(user_id, page_size=10, page_num=1, keyword=None):
    filter_query = Q(user_id=user_id, del_flag=False)
    if keyword:
        filter_query &= Q(title__icontains=keyword)
    collections = Collection.objects.filter(filter_query).order_by('-updated_at')
    query_set = collections[page_size*(page_num-1):page_size*page_num]
    return CollectionListSerializer(query_set, many=True).data


def update_conversation(conversation, validated_data):
    diff_model, is_updated = None, None
    vd = validated_data
    rag_update_data = {
        'conversation_id': conversation.id,
        'agent_id': conversation.agent_id,
        'paper_ids': conversation.paper_ids,
        'public_collection_ids': conversation.public_collection_ids,
        'llm_name': conversation.model,
    }
    if vd.get('model') and conversation.model != vd['model']:
        diff_model = vd['model']
        rag_update_data['llm_name'] = vd['model']
    if vd.get('bot_id') and conversation.bot_id != vd['bot_id']:
        bot = Bot.objects.filter(id=vd['bot_id']).first()
        vd['public_collection_ids'] = bot.extension['public_collection_ids']
        if not vd['public_collection_ids']:
            vd['public_collection_ids'] = []
        bot_collections = BotCollection.objects.filter(
            bot_id=vd['bot_id'], del_flag=False).values_list('collection_id', flat=True).all()
        vd['collection_ids'] = list(bot_collections)
        conversation.bot_id = vd['bot_id']
    elif vd.get('collection_ids') and conversation.collection_ids != vd['collection_ids']:
        collections = Collection.objects.filter(id__in=vd['collection_ids']).all()
        vd['public_collection_ids'] = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
        vd['collection_ids'] = [c.id for c in collections]

    if vd.get('public_collection_ids') and conversation.public_collection_ids != vd['public_collection_ids']:
        conversation.public_collection_ids = vd['public_collection_ids']
        rag_update_data['public_collection_ids'] = vd['public_collection_ids']

    if vd.get('collection_ids') and conversation.collection_ids != vd['collection_ids']:
        conversation.save()
        conversation = update_conversation_by_collection(
            conversation.user_id, conversation, vd['collection_ids'], diff_model)
        is_updated = True
    elif vd.get('documents') and conversation.documents != vd['documents']:
        conversation.documents = vd['documents']
        conversation.save()
        doc_libs = DocumentLibrary.objects.filter(
            user_id=conversation.user_id,
            document_id__in=conversation.documents,
            del_flag=False,
            task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
        ).values_list('document_id', flat=True).all()
        documents = Document.objects.filter(id__in=conversation.documents, del_flag=False).all()
        new_paper_ids = [{
            'collection_id': d.collection_id,
            'collection_type': d.collection_type,
            'doc_id': d.doc_id,
            'full_text_accessible': d.id in doc_libs,
        } for d in documents] if documents else []
        new_papers_info = [{
            'collection_id': d.collection_id,
            'collection_type': d.collection_type,
            'doc_id': d.doc_id,
            'document_id': d.id,
            'full_text_accessible': d.id in doc_libs,
        } for d in documents] if documents else []
        rag_update_data['paper_ids'] = new_paper_ids
        if not cmp_ignore_order(conversation.paper_ids, new_papers_info,sort_fun=itemgetter('collection_id', 'doc_id')):
            RagConversation.update(**rag_update_data)
            is_updated = True
    if not is_updated and diff_model:
        conversation.model = diff_model
        conversation.save()
        RagConversation.update(**rag_update_data)
    return conversation
