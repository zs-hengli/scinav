import datetime
import logging

from celery import shared_task
from django.db.models import Q

from bot.base_service import recreate_bot, bot_detail, bot_documents
from bot.models import BotCollection, Bot
from bot.rag_service import Document as RagDocument
from chat.models import Conversation
from collection.base_service import update_conversation_by_collection
from collection.models import Collection
from collection.serializers import bot_subscribe_personal_document_num
from document.base_service import document_update_from_rag_ret, reference_doc_to_document, \
    reference_doc_to_document_library, search_result_delete_cache
from document.models import DocumentLibrary, Document
from user.models import UserOperationLog

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
        DocumentLibrary.TaskStatusChoices.IN_PROGRESS, DocumentLibrary.TaskStatusChoices.QUEUEING,
        DocumentLibrary.TaskStatusChoices.TO_BE_CANCELLED
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
                DocumentLibrary.TaskStatusChoices.TO_BE_CANCELLED
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
            else:  # COMPLETED CANCELLED
                i.task_status = task_status
                if rag_ret.get('paper'):
                    rag_ret['paper']['status'] = task_status
                try:
                    document = document_update_from_rag_ret(rag_ret['paper']) if rag_ret['paper'] else None
                    i.document = document
                    reference_doc_to_document(document)
                except Exception as e:
                    logger.error(f'async_document_library_task {i.task_id}, {e}')
            i.save()
            if i.task_status == DocumentLibrary.TaskStatusChoices.COMPLETED and i.task_type == 'personal':
                search_result_delete_cache(i.user_id)
    return True


@shared_task(bind=True)
def async_schedule_publish_bot_task(self, task_id=None):
    logger.info(f'xxxxx async_schedule_publish_bot_task, {self}, {task_id}')
    bots = Bot.objects.filter(type=Bot.TypeChoices.IN_PROGRESS).all()
    for bot in bots:
        personal_documents, ref_documents = bot_subscribe_personal_document_num(
            bot.user_id, bot_collections=None, bot=bot)
        ref_result_count = DocumentLibrary.objects.filter(
            user_id='0000', document_id__in=ref_documents,
            task_status__in=[DocumentLibrary.TaskStatusChoices.ERROR, DocumentLibrary.TaskStatusChoices.COMPLETED],
        ).count()
        if ref_result_count == len(ref_documents):
            bot.type = Bot.TypeChoices.PUBLIC
            bot.pub_date = datetime.datetime.now()
            bot.save()
        logger.info(f"async_schedule_publish_bot_task, {bot.id}, bot.type: {bot.type}")
    return True


@shared_task(bind=True)
def async_update_document(self, document_ids):
    documents = Document.objects.filter(pk__in=document_ids).all()
    fileds = [
        'title', 'abstract', 'authors', 'doi', 'categories',
        'year', 'pub_date', 'pub_type', 'venue', 'journal', 'conference', 'keywords',  # 'full_text_accessible',
        'pages', 'citation_count', 'reference_count', 'object_path', 'source_url', 'checksum',
        'ref_collection_id', 'ref_doc_id',
    ]
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
            if data[f] or isinstance(data[f], bool):
                setattr(documents[i], f, data[f])
    Document.objects.bulk_update(documents, fileds)
    logger.info(f'async_update_document end, documents len: {len(documents)}')
    return True


@shared_task(bind=True)
def async_ref_document_to_document_library(self, document_ids):
    """
    下载个人上传的关联文献
    """
    documents = Document.objects.filter(pk__in=document_ids, ref_doc_id__gt=0).all()
    ref_docs = [{'id': None, 'collection_id': d.ref_collection_id, 'doc_id': d.ref_doc_id} for d in documents]
    ref_documents = Document.raw_by_docs(ref_docs) if ref_docs else []
    for d in ref_documents:
        reference_doc_to_document_library(d)
    logger.info(f'ref_document_to_document_library end, ref_documents len: {len(ref_documents)}')
    return True


@shared_task(bind=True)
def async_update_conversation_by_collection(self, collection_id):
    """
    收藏夹有调整 更新相关问答 和专题
    """
    collection_query = BotCollection.objects.filter(collection_id=collection_id)
    collection = Collection.objects.filter(pk=collection_id).first()
    if collection:
        bots = Bot.objects.filter(
            id__in=collection_query.values_list('bot_id', flat=True),
            del_flag=False
        ).all()
        for bot in bots:
            bot_collections = BotCollection.objects.filter(
                bot_id=bot.id, del_flag=False).values_list('collection_id', flat=True).all()
            collections = Collection.objects.filter(id__in=bot_collections, del_flag=False).all()
            old_agent_id = bot.agent_id
            recreate_bot(bot, collections)
            bot.save()
            Conversation.objects.filter(agent_id=old_agent_id).update(agent_id=bot.agent_id)

        conversations = Conversation.objects.filter(collections__contains=collection_id, del_flag=False).all()
        for conv in conversations:
            update_conversation_by_collection(collection.user_id, conv, conv.collections)
    return True


@shared_task(bind=True)
def async_add_user_operation_log(
    self, user_id, operation_type, operation_content=None, obj_id1=None, obj_id2=None, obj_id3=None, source=None
):
    """
    添加用户操作日志
    """
    result = None
    if operation_type == UserOperationLog.OperationType.BOT_DETAIL:
        # 保存 bot detail 到 result
        result = _bot_detail_to_log(user_id, obj_id1)
    operation_log = UserOperationLog.objects.create(
        user_id=user_id,
        operation_type=operation_type,
        operation_content=operation_content,
        result=result,
        obj_id1=obj_id1,
        obj_id2=obj_id2,
        obj_id3=obj_id3,
        source=source,
    )
    logger.info(f'async_add_user_operation_log, {operation_log.id}')
    return True


def _bot_detail_to_log(user_id, bot_id):
    bot = Bot.objects.filter(pk=bot_id).first()
    detail = bot_detail(user_id, bot)
    documents = bot_documents(user_id, bot, 'all', 2000, 1)
    return {
        'bot_detail': detail,
        'documents': documents,
    }