import logging

from collection.models import Collection, CollectionDocument
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagCreateSerializer
from bot.rag_service import Document as RagDocument

logger = logging.getLogger(__name__)


def update_document_lib(user_id, document_ids):
    for doc_id in document_ids:
        data = {
            'user_id': user_id,
            'document_id': doc_id,
            'del_flag': False,
            'task_status': DocumentLibrary.TaskStatusChoices.PENDING,
            'task_id': None,
            'error': None,
        }
        DocumentLibrary.objects.update_or_create(data, user_id=user_id, document_id=doc_id)
    return True


def document_update_from_rag_ret(rag_ret):
    serial = DocumentRagCreateSerializer(data=rag_ret)
    if not serial.is_valid():
        raise Exception(serial.errors)
    vd = serial.validated_data
    document, _ = Document.objects.update_or_create(
        vd,
        doc_id=vd['doc_id'],
        collection_type=vd['collection_type'],
        collection_id=vd['collection_id']
    )
    return document


def reference_doc_to_document(document: Document):
    """
    需注意个人上传文件情况，关联&全文获取标签的文献，自动帮助订阅者下载公共库该文献全文，仅关联标签或无标签个人上传文献，则订阅者无法获取该文献
    """
    if document.full_text_accessible and document.ref_doc_id and document.ref_collection_id:
        coll = Collection.objects.filter(pk=document.ref_collection_id).first()
        if not coll:
            logger.error(f'reference_to_document_library failed, ref_collection_id: {document.ref_collection_id} not exist')
            return False
        rag_ret = RagDocument.get({
            'doc_id': document.ref_doc_id,
            'collection_id': document.ref_collection_id,
            'collection_type': coll.type,
        })
        document_update_from_rag_ret(rag_ret)
        return True
    else:
        return False