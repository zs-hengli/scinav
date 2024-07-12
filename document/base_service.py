import copy
import datetime
import json
import logging

from django.db.models import Q
from django.core.cache import cache

from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagCreateSerializer
from bot.rag_service import Document as RagDocument
from django_redis import get_redis_connection

from vip.serializers import LimitCheckSerializer

logger = logging.getLogger(__name__)


def update_document_lib(user_id, document_ids, keyword=None):
    filter_query = Q(id__in=document_ids, del_flag=False, collection_type=Document.TypeChoices.PUBLIC)
    if keyword:
        filter_query &= Q(title__contains=keyword)
    document_ids = Document.objects.filter(filter_query).values_list('id', flat=True)
    limit_info = LimitCheckSerializer.embedding_limit(user_id)
    document_count = document_ids.count()
    if user_id != '0000':
        if limit_info['daily'] and limit_info['daily'] <= limit_info['used_day'] + document_count:
            return 130006, 'exceed day limit', {
                'used': limit_info['used_day'], 'limit': limit_info['daily'], 'need': document_count
            }
        elif limit_info['monthly'] and limit_info['monthly'] <= limit_info['used_month'] + document_count:
            return 130007, 'exceed month limit', {
                'used': limit_info['used_month'], 'limit': limit_info['monthly'], 'need': document_count
            }

    document_libraries = []
    for doc_id in document_ids.all():
        if old_document_library := DocumentLibrary.objects.filter(
            user_id=user_id, document_id=doc_id, del_flag=False, task_status__in=[
                DocumentLibrary.TaskStatusChoices.COMPLETED, DocumentLibrary.TaskStatusChoices.ERROR
            ]
        ).first():
            document_libraries.append(old_document_library)
            continue
        data = {
            'user_id': user_id,
            'document_id': doc_id,
            'del_flag': False,
            'task_status': DocumentLibrary.TaskStatusChoices.PENDING,
            'task_type': Document.TypeChoices.PUBLIC,
            'task_id': None,
            'error': None,
        }
        update_defaults = copy.deepcopy(data)
        update_defaults['created_at'] = datetime.datetime.now()
        document_library, _ = DocumentLibrary.objects.update_or_create(
            defaults=update_defaults, create_defaults=data, user_id=user_id, document_id=doc_id)
        document_libraries.append(document_library)
    return 0, 'success', document_libraries


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


def search_result_delete_cache(user_id):
    doc_search_redis_key_prefix = f'scinav:paper:search:{user_id}'
    keys = cache.keys(f"{doc_search_redis_key_prefix}:*")
    if keys:
        return cache.delete_many(keys)
    return True


def search_result_from_cache(user_id, content, page_size=10, page_num=1, search_type='paper', limit=100):
    if search_type == 'paper':
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}:{limit}'
    else:
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}'
    content_hash = str_hash(f'{content}')
    redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
    search_cache = cache.get(redis_key)

    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    if search_cache:
        logger.info(f'search resp from cache: {redis_key}')
        all_cache = json.loads(search_cache)
        total = len(all_cache)
        return {
            'list': json.loads(search_cache)[start_num:(page_size * page_num)] if total > start_num else [],
            'total': total
        }


def search_result_cache_data(user_id, content, search_type='paper', limit=100):
    if search_type == 'paper':
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}:{limit}'
    else:
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}'
    content_hash = str_hash(f'{content}')
    redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
    search_cache = cache.get(redis_key)

    if search_cache:
        logger.info(f'search resp from cache: {redis_key}')
        all_cache = json.loads(search_cache)
        return all_cache
    return None
