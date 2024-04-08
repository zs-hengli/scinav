import copy
import json
import logging

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.db.models import query as models_query

from bot.rag_service import Document as Rag_Document
from collection.models import Collection, CollectionDocument
from core.utils.common import str_hash
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagGetSerializer, DocumentUpdateSerializer

from bot.rag_service import Document as RagDocument

logger = logging.getLogger(__name__)


def gen_s3_presigned_post(bucket: str, path: str) -> dict:
    """

    :param bucket:
    :param path:
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

# url, fields = generate_presigned_post('bucket', 'remote/path/of/file')


def search(user_id, content, page_size=10, page_num=1, topn=100):
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
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


def update_document_lib(user_id, document_ids):
    for doc_id in document_ids:
        data = {
            'user_id': user_id,
            'document_id': doc_id,
        }
        DocumentLibrary.objects.update_or_create(data, user_id=user_id, document_id=doc_id)
    return True


def get_url_by_object_path(object_path):
    return f'{settings.OBJECT_PATH_URL_HOST}/{object_path}'


def document_update_from_rag(validated_data):
    doc_info = RagDocument.get(validated_data)
    serial = DocumentRagGetSerializer(data=doc_info)
    if not serial.is_valid():
        raise Exception(serial.errors)
    document, _ = Document.objects.update_or_create(
        serial.validated_data,
        doc_id=serial.validated_data['doc_id'],
        collection_type=serial.validated_data['collection_type'],
        collection_id=serial.validated_data['collection_id']
    )
    data = DocumentUpdateSerializer(document).data
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
        logger.debug(f"success update doc_Id: {d.doc_id}")
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
            data = DocumentUpdateSerializer(document).data
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
    logger.debug(f"success update doc_id: {doc_id}")
    return data