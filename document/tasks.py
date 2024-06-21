import datetime
import logging
from time import sleep

from celery import shared_task
from django.db.models import Q

from bot.base_service import recreate_bot, bot_detail, bot_documents
from bot.models import BotCollection, Bot
from bot.rag_service import Document as RagDocument
from chat.models import Conversation, Question, ConversationShare
from chat.serializers import QuestionListSerializer
from collection.base_service import update_conversation_by_collection
from collection.models import Collection
from collection.serializers import bot_subscribe_personal_document_num
from document.base_service import document_update_from_rag_ret, reference_doc_to_document, \
    reference_doc_to_document_library, search_result_delete_cache
from document.models import DocumentLibrary, Document
from openapi.base_service import update_openapi_log_upload_status
from openapi.models import OpenapiLog
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
            update_document_library_task(i)
    return True


def update_document_library_task(doc_lib: DocumentLibrary):
    try:
        rag_ret = RagDocument.get_ingest_task(doc_lib.task_id)
    except Exception as e:
        logger.error(f'async_document_library_task get_ingest_task error {doc_lib.task_id}, {e}')
        return False, False
    task_id = doc_lib.task_id
    task_status = rag_ret['task_status']
    logger.info(f'async_document_library_task {task_id}, {task_status}')

    if task_status == DocumentLibrary.TaskStatusChoices.ERROR:
        if doc_lib.document_id:
            Document.objects.filter(pk=doc_lib.document_id).update(state='error')
        doc_lib.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_message']}
        update_openapi_log_upload_status(task_id, OpenapiLog.Status.FAILED)
    elif task_status == DocumentLibrary.TaskStatusChoices.CANCELLED:
        update_openapi_log_upload_status(task_id, OpenapiLog.Status.FAILED)
    elif task_status == DocumentLibrary.TaskStatusChoices.COMPLETED:
        if rag_ret.get('paper'):
            rag_ret['paper']['state'] = task_status
        update_openapi_log_upload_status(task_id, OpenapiLog.Status.SUCCESS)
        try:
            document = document_update_from_rag_ret(rag_ret['paper']) if rag_ret['paper'] else None
            doc_lib.document = document
            reference_doc_to_document(document)
        except Exception as e:
            logger.error(f'async_document_library_task {task_status} {doc_lib.task_id}, {e}')
    else:  # QUEUEING IN_PROGRESS TO_BE_CANCELLED
        if doc_lib.task_status == task_status:
            return doc_lib, rag_ret
    doc_lib.task_status = task_status
    doc_lib.save()
    if doc_lib.task_status == DocumentLibrary.TaskStatusChoices.COMPLETED and doc_lib.task_type == 'personal':
        search_result_delete_cache(doc_lib.user_id)
    return doc_lib, rag_ret


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


@shared_task(bind=True)
def async_update_conversation_share_content(self, conversation_share_id, conversation_id, selected_questions):
    logger.info(
        f'async_update_conversation_share_content, {conversation_share_id}, {conversation_id},{selected_questions}')
    conversation_share = ConversationShare.objects.filter(pk=conversation_share_id).first()
    if not conversation_share:
        logger.warning(
            f'async_update_conversation_share_content, not find conversation_share by id: {conversation_share_id}'
        )
        return False
    selected_questions_dict = {q['id']:q for q in selected_questions}
    filter_query = Q(conversation_id=conversation_id, del_flag=False)
    # filter_query &= ~Q(id__in=selected_question_ids)
    query_set = Question.objects.filter(filter_query).all()
    question_data = QuestionListSerializer(query_set, many=True).data
    new_question_data = []
    for index, q in enumerate(question_data):
        if q['id'] in selected_questions_dict:
            sq = selected_questions_dict[q['id']]
            if (
                not sq['has_answer'] and sq['has_answer'] is not None
                and not sq['has_question'] and sq['has_question'] is not None
            ):
                continue
            if not sq['has_answer'] and sq['has_answer'] is not None:
                q['answer'] = None
                q['references'] = None
            if not sq['has_question'] and sq['has_question'] is not None:
                q['content'] = None
            new_question_data.append(q)
        else:
            new_question_data.append(q)
    conversation_share.content = {
        'questions': new_question_data,
    }
    conversation_share.num = len(new_question_data)
    conversation_share.save()
    logger.info(f'async_update_conversation_share_content success ({len(selected_questions)}), {conversation_share_id}')
    return True


@shared_task(bind=True)
def async_complete_abstract(self, user_id, document_ids):
    documents = Document.objects.filter(pk__in=document_ids).all()
    for d in documents:
        ret, times = None, 0
        while not ret and times < 3:
            try:
                ret = RagDocument.complete_abstract(user_id, d.collection_id, d.doc_id)
            except Exception as e:
                logger.error(f'async_complete_abstract error: {e}')
                sleep(5)
    return True

