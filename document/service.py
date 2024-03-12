import json
import logging

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.db.models import query as models_query

from bot.rag_service import Document as Rag_Document
from core.utils.common import str_hash
from document.models import Document, DocumentLibrary

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


def search(user_id, content, page_size=10, page_num=1, topn=1000):
    doc_search_redis_key_prefix = 'doc:search'
    search_result_expires = 86400 * 7  # 缓存过期时间 7天
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
            'journal': doc['journal'],
            'conference': doc['conference'],
            'keywords': doc['keywords'],
            'is_open_access': doc['is_open_access'],
            'citation_count': doc['citation_count'],
            'reference_count': doc['reference_count'],
            'citations': doc['citations'],
            'object_path': doc['object_path'],
            'source_url': doc['source_url'],
            'checksum': doc['checksum'],
            'state': Document.StateChoices.COMPLETE,
        }
        models_query.MAX_GET_RESULTS = 1
        doc, _ = Document.objects.update_or_create(
            data, doc_id=data['doc_id'], collection_id=data['collection_id'], collection_type=data['collection_type'])
        logger.debug(f'update_ret: {doc}')
        ret_data.append({
            'id': str(doc.id),
            'title': doc.title,
            'abstract': doc.abstract,
            'authors': doc.authors,
            'pub_date': doc.pub_date,
            'citation_count': doc.citation_count,
            'reference_count': doc.reference_count,
            'collection_id': str(doc.collection_id),
            'collection_title': doc.collection.title,
        })
    cache.set(redis_key, json.dumps(ret_data), search_result_expires)
    total = len(ret_data)
    return {
        'list': ret_data[start_num:(page_size * page_num)] if total > start_num else [],
        'total': total,
    }


def update_document_lib(user_id, document_ids):
    for doc_id in document_ids:
        data = {
            'user_id': user_id,
            'document_id': doc_id,
        }
        DocumentLibrary.objects.update_or_create(data, user_id=user_id, document_id=doc_id)
    return True
