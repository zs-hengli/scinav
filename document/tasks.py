import logging

from celery import shared_task
from django.db.models import Q

from bot.rag_service import Document as RagDocument
from document.base_service import document_update_from_rag_ret, reference_doc_to_document
from document.models import DocumentLibrary

logger = logging.getLogger('celery')


@shared_task(bind=True)
def async_document_library_task(self, task_id=None):
    # no task_id
    logger.info(f'xxxxx async_document_library_task, {self}, {task_id}')
    query_filter = Q(task_id__isnull=True) | Q(task_id='')
    if instances := DocumentLibrary.objects.filter(query_filter).all():
        for i in instances:
            if not i.object_path:
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
                rag_ret['paper']['status'] = 'completed'
                document_update_from_rag_ret(rag_ret['paper'])
                i.task_status = task_status
                i.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_message']}
            else:  # COMPLETED
                i.task_status = task_status
                rag_ret['paper']['status'] = 'completed'
                document = document_update_from_rag_ret(rag_ret['paper'])
                reference_doc_to_document(document)
                i.document = document
            i.save()
    return True