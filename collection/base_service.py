from chat.serializers import chat_paper_ids
from collection.models import Collection, CollectionDocument
from document.models import Document
from bot.rag_service import Conversations as RagConversation


def update_conversation_by_collection(user_id, conversation, collection_ids):
    # update conversation
    document_ids, paper_ids = [], []
    collections = Collection.objects.filter(id__in=collection_ids).all()
    public_collection_ids = [c.id for c in collections if c.type == Collection.TypeChoices.PUBLIC]
    personal_collection_ids = [c.id for c in collections if c.type == Collection.TypeChoices.PERSONAL]

    collection_docs = CollectionDocument.objects.filter(
        collection_id__in=personal_collection_ids, del_flag=False).all()
    document_ids += [doc.document_id for doc in collection_docs]
    document_ids = list(set(document_ids))
    papers_info = []
    if document_ids:
        documents = Document.objects.filter(id__in=document_ids).values(
            'id', 'user_id', 'title', 'collection_type', 'collection_id', 'doc_id', 'full_text_accessible',
            'ref_collection_id', 'ref_doc_id', 'object_path',
        ).all()
        papers_info = chat_paper_ids(user_id, documents, collection_ids=personal_collection_ids)
    for p in papers_info:
        paper_ids.append({
            'collection_id': p['collection_id'],
            'collection_type': p['collection_type'],
            'doc_id': p['doc_id'],
        })
    RagConversation.update(
        conversation.id,
        agent_id=conversation.agent_id,
        paper_ids=paper_ids,
        public_collection_ids=public_collection_ids
    )
    conversation.paper_ids = papers_info
    conversation.collections = collection_ids
    conversation.bot_id = None
    return conversation