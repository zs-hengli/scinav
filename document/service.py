import copy
import uuid
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
from collection.serializers import CollectionDocumentListSerializer
from core.utils.common import str_hash
from core.utils.exceptions import ValidationError
from document.base_service import document_update_from_rag_ret, update_document_lib
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagUpdateSerializer, \
    DocumentLibrarySubscribeSerializer, DocumentLibraryPersonalSerializer, DocLibAddQuerySerializer, \
    DocumentLibraryListQuerySerializer, DocumentDetailSerializer, DocumentRagGetSerializer
from document.tasks import async_document_library_task

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
    return Rag_Document.presigned_url(user_id, settings.OSS_PUBLIC_KEY, 'put_object', filename=filename)


def get_url_by_object_path(user_id, object_path):
    if object_path:
        rag_ret = Rag_Document.presigned_url(user_id, settings.OSS_PUBLIC_KEY, 'get_object', object_path=object_path)
        return rag_ret['presigned_url'] if rag_ret and rag_ret.get('presigned_url') else None
    return None


def search(user_id, content, page_size=10, page_num=1, topn=100):
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    if cache_data := search_result_from_cache(content, page_size, page_num):
        return cache_data

    rag_ret = Rag_Document.search(user_id, content, limit=topn)
    ret_data = []
    rag_collections = list(set([r['collection_id'] for r in rag_ret]))
    rag_data_dict = {f"{r['doc_id']}_{r['collection_id']}_{r['collection_type']}": r for r in rag_ret}
    create_data = []
    update_data = []
    collections = Collection.objects.filter(id__in=rag_collections).values('id', 'title').all()
    collections_dict = {c['id']: c for c in collections}
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
            'pages': doc['pages'],
            'citation_count': doc['citation_count'],
            'reference_count': doc['reference_count'],
            # 'citations': doc['citations'],
            'object_path': doc['object_path'],
            'source_url': doc['source_url'],
            'checksum': doc['checksum'],
            'ref_collection_id': doc['ref_collection_id'],  # todo 分享只返回公共文章列表，如果是个人取ref_doc_id
            'ref_doc_id': doc['ref_doc_id'],
            'state': (Document.StateChoices.COMPLETED
                      if doc['collection_id'] == 'arxiv' else Document.StateChoices.UNDONE)
        }
        # doc = Document.objects.filter(
        #     doc_id=data['doc_id'], collection_id=data['collection_id'], collection_type=data['collection_type']
        # ).first()
        # if doc:
        #     data['id'] = str(doc.id)
        #     update_data.append(doc)
        # else:
        #     data['id'] = str(uuid.uuid4())
        #     create_data.append(data)

        create_data = copy.deepcopy(data)
        models_query.MAX_GET_RESULTS = 1
        doc, _ = Document.objects.update_or_create(
            defaults=create_data,
            doc_id=data['doc_id'], collection_id=data['collection_id'], collection_type=data['collection_type'])
        logger.debug(f'update_ret: {doc}')
        data['id'] = str(doc.id)

        if collections_dict.get(data['collection_id']):
            collection_title = collections_dict[data['collection_id']]['title']
        else:
            collection_title = '个人库'
        type_pub = Collection.TypeChoices.PUBLIC
        collection_tag = data['collection_id'] if data['collection_type'] == type_pub else data['collection_type']
        ret_data.append({
            'id': data['id'],
            'title': data['title'],
            'abstract': data['abstract'],
            'authors': data['authors'],
            'pub_date': data['pub_date'],
            'citation_count': data['citation_count'],
            'reference_count': data['reference_count'],
            'collection_id': str(data['collection_id']),
            'type': collection_tag,
            'collection_title': collection_title,
            'source': data['journal'] if data['journal'] else data['conference'] if data['conference'] else '',
            'reference_formats': get_reference_formats(DocumentRagGetSerializer(data).data),
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


def get_document_library_list(user_id, list_type, page_size=10, page_num=1):
    # {'filename': '', 'document_title': '', 'status': '-', 'record_time': '-'}
    start_num = page_size * (page_num - 1)
    list_data = []
    public_total, subscribe_total, sub_add_list, my_total = 0, 0, [], 0
    if list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.ALL:
        # public
        public_colles = Collection.objects.filter(id__in=['arxiv'], del_flag=False).all()
        if public_colles:
            public_total = len(public_colles)
            if start_num == 0:
                for public_colle in public_colles:
                    list_data.append({
                        'id': None,
                        'collection_id': public_colle.id,
                        'filename': f"{_('公共库')}: {public_colle.title}",
                        'document_title': None,
                        'document_id': None,
                        'pages': None,
                        'status': '-',
                        'record_time': None,
                        'type': 'public',
                    })

        # subscribe
        # sub_serial = DocumentLibrarySubscribeSerializer(data=_bot_subscribe_document_library_list(user_id), many=True)
        # sub_serial.is_valid()
        # subscribe_total = len(sub_serial.data)
        # sub_add_list = list(sub_serial.data)[start_num:start_num + page_size - public_total]
        # if sub_add_list:
        #     sub_add_list = sorted(sub_add_list, key=lambda x: x['record_time'], reverse=True)
        # list_data += sub_add_list

    # personal
    if list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.ALL:
        query_set = DocumentLibrary.objects.filter(user_id=user_id, del_flag=False).order_by('-updated_at')
    elif list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.IN_PROGRESS:
        query_set = DocumentLibrary.objects.filter(
            user_id=user_id, del_flag=False,
            task_status__in=[DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                             DocumentLibrary.TaskStatusChoices.PENDING,
                             DocumentLibrary.TaskStatusChoices.QUEUEING,
                             ]
        ).order_by('-updated_at')
    elif list_type in [
        DocumentLibraryListQuerySerializer.ListTypeChoices.ERROR,
        DocumentLibraryListQuerySerializer.ListTypeChoices.FAILED
    ]:
        query_set = DocumentLibrary.objects.filter(
            user_id=user_id, del_flag=False,
            task_status=DocumentLibrary.TaskStatusChoices.ERROR
        ).order_by('-updated_at')
    else:
        query_set = DocumentLibrary.objects.filter(
            user_id=user_id, del_flag=False,
            task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
        ).order_by('-updated_at')
    my_total = query_set.count()
    if len(list_data) < page_size:
        my_start_num = 0 if list_data else max(start_num - public_total - subscribe_total, 0)
        my_end_num = my_start_num + page_size - len(list_data)
        query_set = query_set[my_start_num:my_end_num]
        my_list_data = []
        for doc_lib in query_set:
            document_title = doc_lib.document.title if doc_lib.document else '-'
            filename = doc_lib.filename if doc_lib.filename else document_title
            ref_type, document = None, None
            if doc_lib.document_id:
                document = doc_lib.document
                if document.ref_doc_id:
                    ref_type = 'reference'
                    ref_document = Document.objects.filter(
                        doc_id=document.ref_doc_id, collection_id=document.ref_collection_id,
                        object_path__isnull=False, del_flag=False
                    ).first()
                    if ref_document:
                        ref_type = 'reference&full_text_accessible'
            stat_comp = DocumentLibrary.TaskStatusChoices.COMPLETED
            stat_queue = DocumentLibrary.TaskStatusChoices.QUEUEING
            stat_in = DocumentLibrary.TaskStatusChoices.IN_PROGRESS
            stat_pend = DocumentLibrary.TaskStatusChoices.PENDING
            my_list_data.append({
                'id': str(doc_lib.id),
                'filename': filename,
                'document_title': document_title,
                'document_id': str(doc_lib.document_id) if doc_lib.document_id else None,
                'pages': None if not document or doc_lib.task_status != stat_comp else document.pages,
                'status': doc_lib.task_status if doc_lib.task_status not in [stat_queue, stat_pend] else stat_in,
                'reference_type': ref_type,
                'record_time': doc_lib.created_at if doc_lib.task_status == stat_comp else None,
                'type': 'personal',
            })
        my_seral = DocumentLibraryPersonalSerializer(data=my_list_data, many=True)
        if not my_seral.is_valid():
            raise ValidationError(my_seral.errors)
        list_data += list(my_seral.data)
    return {
        'list': list_data,
        'total': my_total + subscribe_total + public_total,
        'show_total': my_total + public_total,
    }


def _bot_subscribe_document_library_list(user_id):
    bot_sub = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bots = Bot.objects.filter(id__in=[bc.bot_id for bc in bot_sub], del_flag=False).all()
    list_data = []
    for bot in bots:
        list_data.append({
            'id': None,
            'filename': f"{_('专题名称')}: {bot.title}",
            'document_title': None,
            'document_id': None,
            'pages': None,
            'status': '-',
            'record_time': bot.created_at,
            'type': 'subscribe',
            'bot_id': bot.id,
        })
    return list_data


def document_update_from_rag(validated_data):
    doc_info = RagDocument.get(validated_data)

    document = document_update_from_rag_ret(doc_info)
    data = DocumentRagUpdateSerializer(document).data
    return data


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


def import_papers_to_collection(collection_papers):
    info = collection_papers
    personal_collection_id = info['personal_collection_id']
    collection_type = info['collection_type']
    collection_id = info['collection_id']
    doc_ids = info['doc_ids']
    num = len(doc_ids)
    count = 0
    c_doc_objs = []
    add_num = 0
    skip_ids = []
    for doc_id in doc_ids:
        try:
            data = import_one_document(collection_id, collection_type, doc_id)
        except Exception as e:
            logger.error(f"import_papers_to_collection error: {doc_id}, {e}")
            skip_ids.append(doc_id)
            continue
        count += 1
        c_doc_objs.append(CollectionDocument(
            collection_id=personal_collection_id,
            document_id=data['id'],
            full_text_accessible=True,
            del_flag=False,
        ))
        coll_doc = {
            'collection_id': personal_collection_id,
            'document_id': data['id'],
            'full_text_accessible': True,
            'del_flag': False,
        }
        collection, created = CollectionDocument.objects.update_or_create(
            coll_doc, collection_id=personal_collection_id, document_id=data['id'])
        if created:
            add_num += 1
    if add_num:
        collection = Collection.objects.filter(id=personal_collection_id).first()
        collection.total_personal += add_num
        collection.save()
    return {
        'total': num,
        'add_num': add_num,
        'skip_ids': skip_ids,
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


def update_exist_documents():
    page_size = 200
    page_num = 1
    documents = Document.objects.filter(del_flag=False).values(
        'collection_type', 'doc_id', 'collection_id').order_by(
        'updated_at')[page_size*(page_num-1):page_size*page_num]
    while documents:
        logger.debug(f'ddddddddd page_size: {page_size}, page_num: {page_num}')
        for d in documents:
            data = {
                'collection_id': d['collection_id'],
                'collection_type': d['collection_type'],
                'doc_id': d['doc_id'],
            }
            document_update_from_rag(data)
            logger.debug(f"ddddddddd success update doc_id: {d['doc_id']}")
        page_num += 1
        documents = Document.objects.filter(del_flag=False).values(
            'collection_type', 'doc_id', 'collection_id').order_by(
            'updated_at')[page_size*(page_num-1):page_size*page_num]


def document_personal_upload(validated_data):
    vd = validated_data
    files = vd.get('files')
    for file in files:
        doc_lib_data = {
            'user_id': vd['user_id'],
            'filename': file['filename'],
            'object_path': file['object_path'],
            'del_flag': False,
            'task_status': DocumentLibrary.TaskStatusChoices.PENDING,
            'task_id': None,
            'error': None,
        }
        filename_count = DocumentLibrary.objects.filter(
            filename__startswith=file['filename'], user_id=vd['user_id'], del_flag=False).count()
        if filename_count:
            doc_lib_data['filename'] = f"{file['filename']}({filename_count})"
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


def document_library_add(user_id, document_ids, collection_id, bot_id, add_type, search_content):
    """
    添加个人库：
     1. 搜索结果添加
     2. 收藏夹添加  all arxiv 全量库 个人库
     3. 文献列表添加
    """
    is_all = True
    all_document_ids = []
    if add_type == DocLibAddQuerySerializer.AddTypeChoices.DOCUMENT_SEARCH:
        search_result = search_result_from_cache(search_content, 200, 1)
        if search_result:
            all_document_ids = [d['id'] for d in search_result['list']]
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_ARXIV:
        coll_documents, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, [collection_id], 'arxiv')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_S2:
        coll_documents, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, [collection_id], 's2')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_SUBSCRIBE_FULL_TEXT:
        bot = Bot.objects.filter(id=bot_id).first()
        coll_documents, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, [collection_id], 'subscribe_full_text', bot)
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_DOCUMENT_LIBRARY:
        collection_ids = [collection_id]
        if bot_id:
            collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).values('collection_id').all()
            collection_ids += [c['collection_id'] for c in collections]
        coll_documents, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'document_library')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_ALL:
        coll_documents, d1, d2, d3 = CollectionDocumentListSerializer.get_collection_documents(
            user_id, [collection_id], 'all')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    else:
        # get document_ids
        is_all = False
        collection_ids = [collection_id] if collection_id else []
        if bot_id and not document_ids:
            if Bot.objects.filter(id=bot_id, user_id=user_id, del_flag=False).exists():
                bot_coll = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).values('collection_id').all()
                collection_ids += [c['collection_id'] for c in bot_coll]
        all_document_ids = []
        if collection_ids and not document_ids:
            collections = Collection.objects.filter(
                id__in=collection_ids, del_flag=False, type=Collection.TypeChoices.PERSONAL).values('id').all()
            collection_ids = [c['id'] for c in collections]
            coll_document = CollectionDocument.objects.filter(
                collection__id__in=collection_ids, del_flag=False).values('document_id').all()
            all_document_ids = [d['document_id'] for d in coll_document]
    if not document_ids:
        document_ids = all_document_ids
    else:
        document_ids = list(set(all_document_ids) - set(document_ids)) \
            if is_all else list(set(document_ids + all_document_ids))
    update_document_lib(user_id, document_ids)
    async_document_library_task.apply_async()
    return True


def doc_lib_batch_operation_check(user_id, validated_data):
    ids = validated_data.get('ids')
    list_type = validated_data.get('list_type')
    is_all = validated_data.get('is_all')
    if is_all:
        if list_type == 'all':
            filter_query = Q(user_id=user_id, del_flag=False)
        elif list_type == 'in_progress':
            filter_query = Q(user_id=user_id, del_flag=False, task_status__in=[
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                DocumentLibrary.TaskStatusChoices.PENDING,
            ])
        else:
            filter_query = Q(user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED)
        if ids:
            filter_query &= ~Q(id__in=ids,)
        doc_libs = DocumentLibrary.objects.filter(filter_query)
    else:
        doc_libs = DocumentLibrary.objects.filter(user_id=user_id, del_flag=False, id__in=ids)
    cannot_status = [
        DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
        DocumentLibrary.TaskStatusChoices.ERROR,
        DocumentLibrary.TaskStatusChoices.PENDING,
    ]
    cannot_filter_query = Q(task_status__in=cannot_status) | Q(document_id__isnull=True)
    if doc_libs.filter(cannot_filter_query).exists():
        return 130003, '您选择的文件当前尚未收录完成，无法执行该操作，请您耐心等待或修改选择对象。'
    document_ids = [doclib.document_id for doclib in doc_libs.all() if doclib.document_id]
    return 0, document_ids


def document_library_delete(user_id, ids, list_type):
    if list_type:
        if list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.ALL:
            filter_query = Q(user_id=user_id, del_flag=False)
        elif list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.IN_PROGRESS:
            filter_query = Q(user_id=user_id, del_flag=False, task_status__in=[
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                DocumentLibrary.TaskStatusChoices.QUEUEING,
                DocumentLibrary.TaskStatusChoices.PENDING,
            ])
        elif list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.COMPLETED:
            filter_query = Q(user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED)
        else:
            filter_query = Q(user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.ERROR)
        if ids:
            filter_query &= ~Q(id__in=ids)
    else:
        filter_query = Q(user_id=user_id, del_flag=False, id__in=ids)
    doc_libs = DocumentLibrary.objects.filter(filter_query)
    effected_num = doc_libs.update(del_flag=True)
    return effected_num


def get_reference_formats(document):
    """
        APA 格式 （参考 https://wordvice.cn/citation-guide/apa）
        MLA 格式 （参考 https://wordvice.cn/citation-guide/mla）
            作者. "来源标题." 出版物名称, 其他贡献者, 版本, 编号, 出版社, 出版日期, 地点.
        GB/T 7714 （文案有 GB/T 修改为 GB/T 7714）格式 （参考 GB/T 7714-2015 国标要求）
            作者. 会议文集名：会议文集其他信息[C]. 出版地：出版者，出版年. 获取和访问路径.
        BibTeX（中间无空格）

    """
    authors = ','.join(document['authors'])
    title = document['title']
    year = document['year']
    source = document['journal'] if document['journal'] else document['conference'] \
        if document['conference'] else document['venue']
    pages = document['pages'] if document['pages'] else ''
    venue = document['venue'] if document['venue'] else ''
    pub_type = (
        document['pub_type']
        if document['pub_type'] else 'conference'
        if document['conference'] else 'journal'
        if document['journal'] else ''
    )
    pub_data = document['pub_date'] if document['pub_date'] else ''
    # apa
    apa = f'{authors};{title}.{source} {year}'  # noqa
    mla = f'{authors}. "{title}." {venue}, {pub_data}.'
    pub_type_tag = '[C]' if pub_type == 'conference' else '[J]' if pub_type == 'journal' else ''
    gbt = f'{authors}. {title}: {venue}{pub_type_tag}, {year}.'
    # bibtex
    # conference
    # @conference{RN04,
    #   author    = "Holleis, Paul and Wagner, Matthias and Koolwaaij, Johan",
    #   title     = "Studying mobile context-aware social services in the wild",
    #   booktitle = "Proc. of the 6th Nordic Conf. on Human-Computer Interaction",
    #   series    = "NordiCHI",
    #   year      = 2010,
    #   pages     = "207--216",
    #   publisher = "ACM",
    #   address   = "New York, NY"
    # }
    bibtex = ''
    info = {
        'authors': authors,
        'title': title,
        'venue': venue,
        'year': year,
        'pages': f'number={pages}' if pages else '',
    }
    if pub_type == 'conference':
        template = '''@conference{{RN04,
    author={authors},
    title={title},
    booktitle={venue},
    year={year}
}}'''
        bibtex = template.format(**info)
    # journal
    # @article{RN01,
    #   author   = "P. J. Cohen",
    #   title    = "The independence of the continuum hypothesis",
    #   journal  = "Proceedings of the National Academy of Sciences",
    #   year     = 1963,
    #   volume   = "50",
    #   number   = "6",
    #   pages    = "1143--1148",
    # }
    else:  # pub_type == 'journal':
        template = '''@article{{RN01,
    author={authors},
    title={title},
    journal={venue},
    year={year},
    {pages}
}}'''
        bibtex = template.format(**info)

    return {
        'GB/T': gbt,
        'MLA': mla,
        'APA': apa,
        'BibTex': bibtex,
    }

