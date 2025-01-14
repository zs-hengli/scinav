import logging
from operator import itemgetter

from bot.rag_service import Conversations as RagConversations
from chat.models import Conversation
from chat.serializers import chat_paper_ids
from collection.models import Collection, CollectionDocument
from core.utils.common import cmp_ignore_order
from document.base_service import search_result_from_cache
from document.models import Document


logger = logging.getLogger(__name__)


def update_conversation_by_collection(user_id, conversation, collection_ids, model=None):
    # update conversation
    document_ids, paper_ids, papers_info, is_updated = [], [], [], False
    if model:
        conversation.model = model
    update_data = {
        'conversation_id': conversation.id,
        'agent_id': conversation.agent_id,
        'llm_name': conversation.model,
        # 'paper_ids': paper_ids,
        # 'public_collection_ids': public_collection_ids,
    }
    all_collections = list(
        set(conversation.collections if conversation.collections else [])
        | set(conversation.public_collection_ids if conversation.public_collection_ids else []))
    if collection_ids:
        collections = Collection.objects.filter(id__in=collection_ids, del_flag=False).all()
        public_collection_ids = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
        personal_collection_ids = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]

        collection_docs = CollectionDocument.objects.filter(
            collection_id__in=personal_collection_ids, del_flag=False).all()
        document_ids += [doc.document_id for doc in collection_docs]
        document_ids = list(set(document_ids))
        if document_ids:
            documents = Document.objects.filter(id__in=document_ids).values(
                'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
                'ref_collection_id', 'ref_doc_id', 'object_path',
            ).all()
            papers_info = chat_paper_ids(
                user_id, documents, collection_ids=personal_collection_ids, bot_id=conversation.bot_id
            )
        for p in papers_info:
            paper_ids.append({
                'collection_id': p['collection_id'],
                'collection_type': p['collection_type'],
                'doc_id': p['doc_id'],
                'full_text_accessible': p['full_text_accessible'],
            })

        if (
            not cmp_ignore_order(conversation.paper_ids, papers_info, sort_fun=itemgetter('collection_id', 'doc_id'))
            or conversation.public_collection_ids != public_collection_ids
            or conversation.collections != personal_collection_ids
        ):
            update_data['paper_ids'] = paper_ids
            update_data['public_collection_ids'] = public_collection_ids
            conversation.paper_ids = papers_info
            conversation.public_collection_ids = public_collection_ids
            conversation.collections = personal_collection_ids
            if collection_ids and not conversation.bot_id:
                conversation.type = (
                    Conversation.TypeChoices.COLLECTION_COV
                    if len(collection_ids) == 1 else Conversation.TypeChoices.COLLECTIONS_COV
                )
            conversation.save()
            if not update_data['agent_id'].startswith('default-scinav'):
                RagConversations.update(**update_data)
                is_updated = True

    elif collection_ids is not None and collection_ids != all_collections:
        paper_ids = []
        update_data['paper_ids'] = paper_ids
        update_data['public_collection_ids'] = []
        conversation.paper_ids = paper_ids
        conversation.public_collection_ids = []
        conversation.collections = []
        conversation.type = None
        conversation.save()
        RagConversations.update(**update_data)
        is_updated = True

    if model and not is_updated:
        RagConversations.update(**update_data)
    return conversation


def generate_collection_title(content=None, document_titles=None):
    if content:
        search_result = search_result_from_cache(content, 200, 1)
        titles = [
            sr['title'] for sr in search_result['list']
        ] if search_result and search_result.get('list') else [content]
    else:
        titles = document_titles
    title = RagConversations.generate_favorite_title(titles)
    return title[:255]