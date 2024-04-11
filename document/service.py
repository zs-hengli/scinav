import copy
import json
import logging

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.db.models import query as models_query
from django.utils.translation import gettext_lazy as _

from bot.models import BotSubscribe, Bot, BotCollection
from bot.rag_service import Document as RagDocument
from bot.rag_service import Document as Rag_Document
from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash
from core.utils.exceptions import ValidationError
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagGetSerializer, DocumentRagUpdateSerializer, \
    DocumentLibrarySubscribeSerializer, DocumentLibraryPersonalSerializer

logger = logging.getLogger(__name__)


def gen_s3_presigned_post(bucket: str, path: str) -> dict:
    """
    1. 前端请求上传地址 返回 url 和 filed
    2. 端根据url和filed 加上文件 发起post 请求S3文件上传服务，
    > 单次只能单个文件上传，多个需要多次请求改接口依次上传
    > post 请求的curl示例如下
    curl --location 'http://172.23.15.206:9001/sci-nav-dev' \
    --form 'key="doc/001.jpg"' \
    --form 'x-amz-algorithm="AWS4-HMAC-SHA256"' \
    --form 'x-amz-credential="HmwhMO1B9dmzww9tiucC/20240307/us-east-1/s3/aws4_request"' \
    --form 'x-amz-date="20240307T054623Z"' \
    --form 'policy="eyJleHBpcmF0aW9uIjogIjIwMjQtMDMtMDdUMDY6NDY6MjNaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAic2NpLW5hdi1kZXYifSwgeyJrZXkiOiAiZG9jLzAwMS5qcGcifSwgeyJ4LWFtei1hbGdvcml0aG0iOiAiQVdTNC1ITUFDLVNIQTI1NiJ9LCB7IngtYW16LWNyZWRlbnRpYWwiOiAiSG13aE1PMUI5ZG16d3c5dGl1Y0MvMjAyNDAzMDcvdXMtZWFzdC0xL3MzL2F3czRfcmVxdWVzdCJ9LCB7IngtYW16LWRhdGUiOiAiMjAyNDAzMDdUMDU0NjIzWiJ9XX0="' \
    --form 'x-amz-signature="fd5db4ee420b8a31f8470569861f18d894e63c28a639d8b36e245fc302b7f987"' \
    --form 'file=@"pic/2022-06-10_09.52.44.png"'
    :return: example
        {
            "url": "https://s3-upload.bucket-name",
            "fields": {
                "key": "doc/001.jpg",
                "x-amz-algorithm": "AWS4-HMAC-SHA256",
                "x-amz-credential": "HmwhMO1B9dmzww9tiucC/20240307/us-east-1/s3/aws4_request",
                "x-amz-date": "20240307T054623Z",
                "policy": "eyJleHBpcmF0aW9uIjogIjIwMjQtMDMtMDdUMDY6NDY6MjNaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiA...",
                "x-amz-signature": "fd5db4ee420b8a31f8470569861f18d894e63c28a639d8b36e245fc302b7f987"
            }
        }
    """
    endpoint_url = settings.S3_ENDPOINT if settings.S3_ENDPOINT.startswith('http') else f"http://{settings.S3_ENDPOINT}"
    s3r = boto3.resource(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        # region_name=S3_REGION,
        config=Config(signature_version='s3v4'),
    )
    if not s3r.Bucket(bucket).creation_date:
        s3r.create_bucket(Bucket=bucket)
    dict_ = s3r.meta.client.generate_presigned_post(
        Bucket=bucket,
        Key=path,
        ExpiresIn=3600
    )
    return {'url': dict_['url'], 'fields': dict_['fields']}


def presigned_url(user_id, filename):
    return Rag_Document.presigned_url(user_id, settings.OSS_PUBLIC_KEY, filename)


def search(user_id, content, page_size=10, page_num=1, topn=100):
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    if cache_data := search_result_from_cache(content, page_size, page_num):
        return cache_data

    rag_ret = Rag_Document.search(user_id, content, limit=topn)
    ret_data = []
    for doc in rag_ret:
        data = {
            'doc_id': doc['doc_id'],
            'collection_type': doc['collection_type'],
            'collection_id': doc['collection_id'],
            'title': doc['title'],
            'abstract': doc['abstract'],
            'authors': doc['authors'],
            'doi': doc['doi'],
            'categories': doc['categories'],
            'year': doc['year'],
            'pub_date': doc['pub_date'],
            'pub_type': doc['pub_type'],
            'venue': doc['venue'],
            'journal': doc['journal'],
            'conference': doc['conference'],
            'keywords': doc['keywords'],
            'full_text_accessible': doc['full_text_accessible'],
            'citation_count': doc['citation_count'],
            'reference_count': doc['reference_count'],
            'citations': doc['citations'],
            'object_path': doc['object_path'],
            'source_url': doc['source_url'],
            'checksum': doc['checksum'],
            'ref_collection_id': doc['ref_collection_id'],  # todo 分享只返回公共文章列表，如果是个人取ref_doc_id
            'ref_doc_id': doc['ref_doc_id'],
            'state': Document.StateChoices.COMPLETE if doc['collection_id'] == 'arxiv' else Document.StateChoices.UNDONE
        }
        create_data = copy.deepcopy(data)
        del_empty_fields = ['object_path', 'source_url', 'checksum', 'full_text_accessible']
        for df in del_empty_fields:
            if not data[df]: del create_data[df]
        models_query.MAX_GET_RESULTS = 1
        doc, _ = Document.objects.update_or_create(
            defaults=create_data,
            create_defaults=data,
            doc_id=data['doc_id'], collection_id=data['collection_id'], collection_type=data['collection_type'])
        logger.debug(f'update_ret: {doc}')
        if not Collection.objects.filter(id=doc.collection_id).exists():
            collection_title = doc.collection_id
        else:
            collection_title = doc.collection.title
        ret_data.append({
            'id': str(doc.id),
            'title': doc.title,
            'abstract': doc.abstract,
            'authors': doc.authors,
            'pub_date': doc.pub_date,
            'citation_count': doc.citation_count,
            'reference_count': doc.reference_count,
            'collection_id': str(doc.collection_id),
            'collection_title': collection_title,
            'source': doc.journal if doc.journal else doc.conference if doc.conference else ''
        })
    search_result_save_cache(content, ret_data)
    total = len(ret_data)
    return {
        'list': ret_data[start_num:(page_size * page_num)] if total > start_num else [],
        'total': total,
    }


def search_result_from_cache(content, page_size=10, page_num=1):
    doc_search_redis_key_prefix = 'doc:search'
    content_hash = str_hash(content)
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


def search_result_save_cache(content, data, search_result_expires=86400 * 7):
    doc_search_redis_key_prefix = 'doc:search'
    content_hash = str_hash(content)
    redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
    res = cache.set(redis_key, json.dumps(data), search_result_expires)
    return res


def get_url_by_object_path(object_path):
    return f'{settings.OBJECT_PATH_URL_HOST}/{object_path}'


def get_document_library_list(user_id, page_size=10, page_num=1):
    # {'filename': '', 'document_title': '', 'status': '-', 'record_time': '-'}
    start_num = page_size * (page_num - 1)
    list_data = []
    public_total, subscribe_total, sub_add_list, my_total = 0, 0, [], 0
    # public
    arxiv_coll = Collection.objects.filter(id='arxiv', del_flag=False).first()
    if arxiv_coll:
        public_total = 1
        if start_num == 0:
            list_data.append({
                'id': None,
                'filename': f"{_('公共库')}: {arxiv_coll.title}",
                'document_title': '-',
                'status': '-',
                'record_time': '-',
                'type': 'public',
            })

    # subscribe
    sub_serial = DocumentLibrarySubscribeSerializer(data=_bot_subscribe_document_library_list(user_id), many=True)
    sub_serial.is_valid()
    subscribe_total = len(sub_serial.data)
    sub_add_list = list(sub_serial.data)[start_num:start_num + page_size - public_total]
    list_data += sub_add_list

    # personal
    query_set = DocumentLibrary.objects.filter(user_id=user_id, del_flag=False).order_by('-updated_at')
    my_total = query_set.count()
    if len(list_data) < page_size:
        my_start_num = 0 if list_data else max(start_num - public_total - subscribe_total, 0)
        my_end_num = my_start_num + page_size - len(list_data)
        query_set = query_set[my_start_num:my_end_num]
        my_list_data = []
        for doc_lib in query_set:
            filename = doc_lib.filename if doc_lib.filename else '-'
            my_list_data.append({
                'id': str(doc_lib.id),
                'filename': doc_lib.filename if doc_lib.filename else '-',
                'document_title': doc_lib.document.title if doc_lib.document else filename,
                'status': doc_lib.task_status,
                'record_time': doc_lib.created_at,
                'type': 'personal',
            })
        my_seral = DocumentLibraryPersonalSerializer(data=my_list_data, many=True)
        if not my_seral.is_valid():
            raise ValidationError(my_seral.errors)
        list_data += list(my_seral.data)
    return {
        'list': list_data,
        'total': my_total + subscribe_total + public_total,
    }


def _bot_subscribe_document_library_list(user_id):
    bot_sub = BotSubscribe.objects.filter(bot__user_id=user_id, del_flag=False).all()
    bots = Bot.objects.filter(id__in=[bc.bot_id for bc in bot_sub])
    list_data = []
    for bot in bots:
        list_data.append({
            'id': None,
            'filename': f"{_('专题名称')}: {bot.title}",
            'document_title': '-',
            'status': '-',
            'record_time': bot.created_at,
            'type': 'subscribe',
            'bot_id': bot.id,
        })
    return list_data


def document_update_from_rag(validated_data):
    doc_info = RagDocument.get(validated_data)
    document = _document_update_from_rag_ret(doc_info)
    data = DocumentRagUpdateSerializer(document).data
    return data


def _document_update_from_rag_ret(rag_ret):
    serial = DocumentRagGetSerializer(data=rag_ret)
    if not serial.is_valid():
        raise Exception(serial.errors)
    document, _ = Document.objects.update_or_create(
        serial.validated_data,
        doc_id=serial.validated_data['doc_id'],
        collection_type=serial.validated_data['collection_type'],
        collection_id=serial.validated_data['collection_id']
    )
    return document


def documents_update_from_rag(begin_id, end_id):
    documents = Document.objects.filter(doc_id__gte=begin_id, doc_id__lte=end_id).values_list(
        'doc_id', 'collection_id', 'collection_type', named=True).all()
    for d in documents:
        data = {
            'collection_id': d.collection_id,
            'collection_type': d.collection_type,
            'doc_id': d.doc_id,
        }
        document_update_from_rag(data)
        logger.info(f"success update doc_Id: {d.doc_id}")
    return True


def import_documents_from_json():
    with open('doc/linfeng_zhang.json') as f:
        info = json.load(f)
    topic_name = info['topic_name']
    collection_type = info['collection_type']
    collection_id = info['collection_id']
    doc_ids = info['doc_ids']
    num = len(doc_ids)
    count = 0
    c_doc_objs = []
    need_reload = False
    for doc_id in doc_ids:
        if need_reload:
            data = import_one_document(collection_id, collection_type, doc_id)
        else:
            document = Document.objects.filter(
                doc_id=doc_id, collection_id=collection_id, collection_type=collection_type).first()
            if not document:
                raise Exception(f'not found doc_id: {doc_id}')
            data = DocumentRagUpdateSerializer(document).data
        count += 1
        # ewn_collection_id = '7ce9f633-696e-4dd7-84cb-4b58416a0de5'
        zlf_collection_id = '253f05a7-c1e1-4f08-84d7-9c926f9e19ee'

        c_doc_objs.append(CollectionDocument(
            collection_id=zlf_collection_id,
            document_id=data['id'],
            full_text_accessible=True,
        ))
        logger.debug(f"ddddddddd total: {num}, count: {count}, doc_id: {doc_id}")

    CollectionDocument.objects.bulk_create(c_doc_objs)
    return {
        'total': num,
        'id_list': doc_ids
    }


def import_one_document(collection_id, collection_type, doc_id):
    data = {
        'collection_id': collection_id,
        'collection_type': collection_type,
        'doc_id': doc_id,
    }
    data = document_update_from_rag(data)
    logger.info(f"success update doc_id: {doc_id}")
    return data


def document_personal_upload(validated_data):
    vd = validated_data
    files = vd.get('files')
    for file in files:
        doc_lib_data = {
            'user_id': vd['user_id'],
            'filename': file['filename'],
            'object_path': file['object_path'],
        }
        # todo for test
        # logger.debug(f'dddddddd doc_lib_data: {doc_lib_data}')
        # continue
        instance, _ = DocumentLibrary.objects.update_or_create(
            doc_lib_data, user_id=vd['user_id'], filename=file['filename'], object_path=file['object_path'])
        if not instance.task_id:
            rag_ret = RagDocument.ingest_personal_paper(vd['user_id'], file['object_path'])
            instance.task_id = rag_ret['task_id']
            instance.task_status = (
                rag_ret['task_status']
                if rag_ret['task_status'] != DocumentLibrary.TaskStatusChoices.COMPLETED
                else DocumentLibrary.TaskStatusChoices.IN_PROGRESS
            )
            if instance.task_status == DocumentLibrary.TaskStatusChoices.ERROR:
                instance.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_message'], }
            instance.save()
    return vd


def document_library_add(user_id, document_ids, collection_id, bot_id):
    # get document_ids
    collection_ids = []
    if bot_id:
        if Bot.objects.filter(id=bot_id, user_id=user_id, del_flag=False).exists():
            bot_coll = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).values('collection_id').all()
            collection_ids = [c['collection_id'] for c in bot_coll]
    if collection_id:
        collection_ids.append(collection_id)
    collections = Collection.objects.filter(
        id__in=collection_ids, del_flag=False, type=Collection.TypeChoices.PERSONAL).values('id').all()
    collection_ids = [c['id'] for c in collections]
    coll_document = CollectionDocument.objects.filter(
        collection__id__in=collection_ids, del_flag=False).values('document_id').all()
    if not document_ids:
        document_ids = []
    document_ids += [c['document_id'] for c in coll_document]
    update_document_lib(user_id, document_ids)
    return True


def update_document_lib(user_id, document_ids):
    for doc_id in document_ids:
        data = {
            'user_id': user_id,
            'document_id': doc_id,
        }
        DocumentLibrary.objects.update_or_create(data, user_id=user_id, document_id=doc_id)
    return True


def async_document_library_task():
    # no task_id
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
    if instances := DocumentLibrary.objects.filter(task_status=DocumentLibrary.TaskStatusChoices.IN_PROGRESS).all():
        for i in instances:
            rag_ret = RagDocument.get_ingest_task(i.task_id)
            task_status = rag_ret['task_status']
            logger.info(f'async_document_library_task {i.task_id}, {task_status}')
            if task_status == DocumentLibrary.TaskStatusChoices.IN_PROGRESS:
                continue
            elif task_status == DocumentLibrary.TaskStatusChoices.ERROR:
                i.task_status = task_status
                i.error = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_code']}
            else:  # COMPLETED
                i.task_status = task_status
                document = _document_update_from_rag_ret(rag_ret['paper'])
                i.document = document
            i.save()
    return True
