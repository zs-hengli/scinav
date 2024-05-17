from operator import itemgetter

from bot.rag_service import Conversations as RagConversation
from chat.models import Conversation
from chat.serializers import chat_paper_ids
from collection.models import Collection, CollectionDocument
from core.utils.common import cmp_ignore_order
from document.models import Document


def update_conversation_by_collection(user_id, conversation, collection_ids, model=None):
    # update conversation
    document_ids, paper_ids, papers_info = [], [], []
    update_data = {
        'conversation_id': conversation.id,
        'agent_id': conversation.agent_id,
        # 'paper_ids': paper_ids,
        # 'public_collection_ids': public_collection_ids,
        # 'llm_name': model,
    }
    if collection_ids:
        collections = Collection.objects.filter(id__in=collection_ids).all()
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

        if not cmp_ignore_order(conversation.paper_ids, papers_info, sort_fun=itemgetter('collection_id', 'doc_id')):
            update_data['paper_ids'] = paper_ids
            update_data['public_collection_ids'] = public_collection_ids
            conversation.paper_ids = papers_info
            conversation.public_collection_ids = public_collection_ids
            conversation.collections = collection_ids
            if collection_ids and not conversation.bot_id:
                conversation.type = (
                    Conversation.TypeChoices.COLLECTION_COV
                    if len(collection_ids) == 1 else Conversation.TypeChoices.COLLECTIONS_COV
                )
            conversation.save()
    elif collection_ids is not None and collection_ids != conversation.collections:
        paper_ids = []
        update_data['paper_ids'] = paper_ids
        update_data['public_collection_ids'] = []
        conversation.paper_ids = paper_ids
        conversation.public_collection_ids = []
        conversation.collections = []
        conversation.type = None
        conversation.save()

    if model:
        update_data['llm_name'] = model
        conversation.model = model
        conversation.save()
    RagConversation.update(**update_data)
    return conversation