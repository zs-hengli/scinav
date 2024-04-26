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
            'task_type': Document.TypeChoices.PUBLIC,
            'task_id': None,
            'error': None,
        }
        DocumentLibrary.objects.update_or_create(data, user_id=user_id, document_id=doc_id)
    return True


def document_update_from_rag_ret(rag_ret):
    serial = DocumentRagCreateSerializer(data=rag_ret)
    if not serial.is_valid():
        logger.error(f'document_update_from_rag_ret failed, serial.errors: {serial.errors}')
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
    if document.ref_doc_id and document.ref_collection_id:
        coll = Collection.objects.filter(pk=document.ref_collection_id).first()
        if not coll:
            logger.error(f'reference_to_document_library failed, ref_collection_id: {document.ref_collection_id} not exist')
            return False
        rag_ret = RagDocument.get({
            'doc_id': document.ref_doc_id,
            'collection_id': document.ref_collection_id,
            'collection_type': coll.type,
        })
        if not rag_ret.get('full_text_accessible'):
            rag_ret['full_text_accessible'] = document.full_text_accessible
        ref_document = document_update_from_rag_ret(rag_ret)
        return ref_document
    else:
        return False


def reference_doc_to_document_library(document):
    if document.ref_doc_id and document.ref_collection_id:
        ref_document: Document = Document.objects.filter(
            doc_id=document.ref_doc_id, collection_id=document.ref_collection_id).first()
        if not ref_document:
            ref_document = reference_doc_to_document(document)
        if ref_document:
            update_document_lib('0000', [ref_document.id])
