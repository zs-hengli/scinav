import logging

from celery import shared_task
from django.db.models import Q

from bot.rag_service import Document as RagDocument
from document.base_service import document_update_from_rag_ret, reference_doc_to_document, update_document_lib
from document.models import DocumentLibrary, Document

logger = logging.getLogger('celery')


@shared_task(bind=True)
def async_document_library_task(self, task_id=None):
    # no task_id
    logger.info(f'xxxxx async_document_library_task, {self}, {task_id}')
    query_filter = Q(task_id__isnull=True) | Q(task_id='')
    if instances := DocumentLibrary.objects.filter(query_filter).all():
        for i in instances:
            if not i.filename:
                rag_ret = RagDocument.ingest_public_paper(i.user_id, i.document.collection_id, i.document.doc_id)
            else:
                rag_ret = RagDocument.ingest_personal_paper(i.user_id, i.object_path)
            i.task_id = rag_ret['task_id']
            i.task_status = (
                rag_ret['task_status']
                if rag_ret['task_status'] != DocumentLibrary.TaskStatusChoices.COMPLETED
                else DocumentLibrary.TaskStatusChoices.IN_PROGRESS
            )
            if i.task_status == DocumentLibrary.TaskStatusChoices.ERROR:
                i.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_code']}
            i.save()
    # in progress
    if instances := DocumentLibrary.objects.filter(task_status__in=[
        DocumentLibrary.TaskStatusChoices.IN_PROGRESS, DocumentLibrary.TaskStatusChoices.QUEUEING
    ]).all():
        for i in instances:
            try:
                rag_ret = RagDocument.get_ingest_task(i.task_id)
            except Exception as e:
                logger.error(f'async_document_library_task {i.task_id}, {e}')
                i.task_status = DocumentLibrary.TaskStatusChoices.ERROR
                i.error = {'error_code': '500', 'error_message': str(e)}
                i.save()
                continue
            task_status = rag_ret['task_status']
            logger.info(f'async_document_library_task {i.task_id}, {task_status}')
            if task_status in [
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                DocumentLibrary.TaskStatusChoices.QUEUEING,
            ]:
                if i.task_status == task_status:
                    continue
                else:
                    i.task_status = task_status
            elif task_status == DocumentLibrary.TaskStatusChoices.ERROR:
                if i.document_id:
                    Document.objects.filter(pk=i.document_id).update(state='error')
                i.task_status = task_status
                i.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_message']}
                if i.user_id == '0000' and i.document_id:
                    document = Document.objects.filter(pk=i.document_id).first()
                    if document:
                        document.full_text_accessible = None
                        document.save()
                        Document.objects.filter(
                            ref_doc_id=document.doc_id, ref_collection_id=document.collection_id
                        ).update(full_text_accessible=None)
            else:  # COMPLETED
                i.task_status = task_status
                rag_ret['paper']['status'] = 'completed'
                try:
                    document = document_update_from_rag_ret(rag_ret['paper'])
                    i.document = document
                    if i.user_id == '0000':
                        Document.objects.filter(
                            ref_doc_id=document.doc_id, ref_collection_id=document.collection_id
                        ).update(full_text_accessible=rag_ret['paper']['full_text_accessible'])
                    if ref_document := reference_doc_to_document(document):
                        update_document_lib('0000', [ref_document.id])
                except Exception as e:
                    logger.error(f'async_document_library_task {i.task_id}, {e}')
            i.save()
    return True


@shared_task(bind=True)
def async_update_document(self, document_ids, rag_data):
    documents = Document.objects.filter(pk__in=document_ids).all()
    fileds = [
        'doc_id', 'collection_type', 'collection_id', 'title', 'abstract', 'authors', 'doi', 'categories',
        'year', 'pub_date', 'pub_type', 'venue', 'journal', 'conference', 'keywords', 'full_text_accessible',
        'pages', 'citation_count', 'reference_count', 'object_path', 'source_url', 'checksum',
        'ref_collection_id', 'ref_doc_id',
    ]
    logger.info(f'async_update_document, begin rag_data len: {len(rag_data)}')
    for i, d in enumerate(documents):
        get_rag_data = {
            'collection_type': d.collection_type,
            'collection_id': d.collection_id,
            'doc_id': d.doc_id,
        }
        try:
            data = RagDocument.get(get_rag_data)
        except Exception as e:
            logger.error(f'async_update_document, {d.doc_id}_{d.collection_id}_{d.collection_type}, {e}')
            continue
        for f in fileds:
            setattr(documents[i], f, data[f])
    Document.objects.bulk_update(documents, fileds)
    logger.info(f'async_update_document end, documents len: {len(documents)}')
    return True