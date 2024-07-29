import datetime
import json
import logging
import uuid
from collections import Counter

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, F
from django.utils.translation import gettext_lazy as _

from bot.models import BotSubscribe, Bot, BotCollection
from bot.rag_service import Document as RagDocument
from bot.rag_service import Authors as RagAuthors
from collection.models import Collection, CollectionDocument
from collection.serializers import CollectionDocumentListSerializer
from core.utils.common import str_hash
from core.utils.date import str2date
from core.utils.exceptions import ValidationError
from document.base_service import document_update_from_rag_ret, update_document_lib, search_result_delete_cache, \
    search_result_from_cache, search_result_cache_data
from document.models import Document, DocumentLibrary, bulk_insert_ignore_duplicates
from document.serializers import DocumentLibraryPersonalSerializer, DocLibAddQuerySerializer, \
    DocumentLibraryListQuerySerializer, DocumentRagCreateSerializer, AuthorsDetailSerializer, SearchQuerySerializer
from document.tasks import async_document_library_task, async_update_document, async_update_conversation_by_collection, \
    update_document_library_task
from vip.base_service import MemberTimeClock
from vip.models import MemberUsageLog
from vip.serializers import LimitCheckSerializer

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
    return RagDocument.presigned_url(user_id, settings.OSS_PUBLIC_KEY, 'put_object', filename=filename)


def get_url_by_object_path(user_id, object_path):
    if object_path:
        rag_ret = RagDocument.presigned_url(user_id, settings.OSS_PUBLIC_KEY, 'get_object', object_path=object_path)
        return rag_ret['presigned_url'] if rag_ret and rag_ret.get('presigned_url') else None
    return None


def _rag_papers_to_documents(rag_papers):
    rag_ret = DocumentRagCreateSerializer(rag_papers, many=True).data
    documents = []
    rag_collections = list(set([r['collection_id'] for r in rag_ret]))
    collections = Collection.objects.filter(id__in=rag_collections).values('id', 'title').all()
    collections_dict = {c['id']: c for c in collections}
    documents_dict = get_documents_by_rag(rag_ret)
    document_ids = [d.id for d in documents_dict.values()]
    for doc in rag_ret:
        data = DocumentRagCreateSerializer(doc).data
        data['id'] = str(documents_dict[f"{doc['collection_id']}-{doc['doc_id']}"].id)

        if collections_dict.get(data['collection_id']):
            collection_title = collections_dict[data['collection_id']]['title']
        else:
            collection_title = '个人库'
        type_pub = Collection.TypeChoices.PUBLIC
        collection_tag = data['collection_id'] if data['collection_type'] == type_pub else data['collection_type']
        source = (
            data['venue'] if data['venue'] else
            data['journal'] if data['journal'] else
            data['conference'] if data['conference']
            else ''
        )
        pub_date = data['pub_date'] if data['pub_date'] else str(data['year']) if data['year'] else None
        # document = Document(**data)
        documents.append({
            'id': data['id'],
            'title': data['title'],
            'abstract': data['abstract'],
            'authors': data['authors'],
            'author_names_ids': data['author_names_ids'],
            'pub_date': pub_date,
            'citation_count': data['citation_count'],
            'doc_id': data['doc_id'],
            'collection_id': str(data['collection_id']),
            'type': collection_tag,
            'collection_title': collection_title,
            'venue': source,
            'source': source,
            # 'reference_formats': get_reference_formats(document),
        })
    return documents


def advance_search(documents, validated_data):
    vd = validated_data
    # static source/authors
    all_sources = [d['source'] for d in documents if d['source']]
    counter = Counter(all_sources)
    counter_sources = dict(sorted(counter.items(), key=lambda item: item[1], reverse=True))

    all_authors = [author.strip() for d in documents for author in (d['authors'] if d['authors'] else [])]
    counter = Counter(all_authors)
    counter_authors = dict(sorted(counter.items(), key=lambda item: item[1], reverse=True))

    if vd.get('sources'):
        documents = [d for d in documents if d['source'] in vd['sources']]
    if vd.get('authors'):
        documents = [
            d for d in documents
            if d['authors']
               and any(author in [t.strip() for t in d['authors']] for author in [t.strip() for t in vd['authors']])
        ]

    if vd.get('begin_date'):
        if isinstance(vd['begin_date'], str):
            vd['begin_date'] = datetime.datetime.strptime(vd['begin_date'], '%Y-%m-%d').date()
        documents = [
            d for d in documents
            if d['pub_date'] and str2date(d['pub_date']) >= vd['begin_date']
        ]
    if vd.get('end_date'):
        if isinstance(vd['end_date'], str):
            vd['end_date'] = datetime.datetime.strptime(vd['end_date'], '%Y-%m-%d').date()
        documents = [
            d for d in documents
            if d['pub_date'] and str2date(d['pub_date']) <= vd['end_date']
        ]
    if vd.get('order_by') and vd.get('order_by') != SearchQuerySerializer.OrderBy.RELEVANCY:
        if vd['order_by'] == SearchQuerySerializer.OrderBy.PUB_DATE:
            documents = sorted(
                documents, key=lambda x: x['pub_date'] if x['pub_date'] is not None else '', reverse=True)
    return documents, counter_sources, counter_authors


def search(user_id, validated_data):
    vd = validated_data
    content = vd['content']
    page_size = vd['page_size']
    page_num = vd['page_num']
    limit = vd['limit']
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    # if cache_data := search_result_from_cache(user_id, content, page_size, page_num, limit=limit):
    #     return cache_data

    if cache_data := search_result_cache_data(user_id, content, limit=limit):
        documents = cache_data
    else:
        rag_ret = RagDocument.search(user_id, content, limit=limit)
        documents = _rag_papers_to_documents(rag_ret)
        document_ids = [d['id'] for d in documents]
        async_update_document.apply_async(args=[document_ids, rag_ret])
        search_result_save_cache(user_id, content, documents, limit=limit)

    documents, sources, authors = advance_search(documents, vd)
    total = len(documents)
    return {
        'list': documents[start_num:(page_size * page_num)] if total > start_num else [],
        'sources': sources,
        'authors': authors,
        'total': total,
    }


def get_citations(obj: Document):
    if obj.collection_type == Document.TypeChoices.PERSONAL:
        if obj.ref_doc_id and obj.ref_collection_id:
            citations = RagDocument.citations('public', obj.ref_collection_id, obj.ref_doc_id)
        else:
            citations = []
    else:
        citations = RagDocument.citations(obj.collection_type, obj.collection_id, obj.doc_id)
    if citations:
        ret_data = []
        for i, c in enumerate(citations):
            # title = c['title']
            # year = c['year']
            # source = c['journal'] if c['journal'] else c['conference'] if c['conference'] else c['venue']
            # doc_apa = Document.get_doc_apa(c['authors'], year, title, source)
            document = Document(
                collection_type=c['collection_type'],
                collection_id=c['collection_id'],
                doc_id=c['doc_id'],
                title=c['title'],
                authors=c['authors'],
                year=c['year'],
                pub_date=c['pub_date'],
                pub_type=c['pub_type'],
                venue=c['venue'],
                journal=c['journal'],
                conference=c['conference'],
                pages=c['pages'],
                citation_count=c['citation_count'],
            )
            doc_apa = document.get_csl_formate('apa')
            ret_data.append({
                'doc_id': c['doc_id'],
                'collection_id': c['collection_id'],
                'collection_type': c['collection_type'],
                'title': c['title'],
                'doc_apa': doc_apa
            })
        return ret_data
    return []


def get_references(obj: Document):
    if obj.collection_type == Document.TypeChoices.PERSONAL:
        if obj.ref_doc_id and obj.ref_collection_id:
            references = RagDocument.references('public', obj.ref_collection_id, obj.ref_doc_id)
        else:
            references = []
    else:
        references = RagDocument.references(obj.collection_type, obj.collection_id, obj.doc_id)
    if references:
        ret_data = []
        for i, r in enumerate(references):
            # title = r['title']
            # year = r['year']
            # source = r['journal'] if r['journal'] else r['conference'] if r['conference'] else r['venue']
            # doc_apa = Document.get_doc_apa(r['authors'], year, title, source)

            document = Document(
                collection_type=r['collection_type'],
                collection_id=r['collection_id'],
                doc_id=r['doc_id'],
                title=r['title'],
                authors=r['authors'],
                year=r['year'],
                pub_date=r['pub_date'],
                pub_type=r['pub_type'],
                venue=r['venue'],
                journal=r['journal'],
                conference=r['conference'],
                pages=r['pages'],
                citation_count=r['citation_count'],
            )
            doc_apa = document.get_csl_formate('apa')
            ret_data.append({
                'doc_id': r['doc_id'],
                'collection_id': r['collection_id'],
                'collection_type': r['collection_type'],
                'title': r['title'],
                'doc_apa': doc_apa
            })
        return ret_data
    return []


def author_detail(user_id, author_id):
    author = RagAuthors.get_author(author_id)
    return AuthorsDetailSerializer(author).data


def author_documents(user_id, author_id, validated_data):
    vd = validated_data
    page_size = vd['page_size']
    page_num = vd['page_num']
    start_num = page_size * (page_num - 1)
    if cache_data := search_result_cache_data(user_id, author_id, search_type='author_papers'):
        documents = cache_data
    else:
        papers = RagAuthors.get_author_papers(author_id)
        documents = _rag_papers_to_documents(papers)
        document_ids = [d['id'] for d in documents]
        async_update_document.apply_async(args=[document_ids, papers])
        search_result_save_cache(user_id, author_id, documents, search_type='author_papers')

    documents, sources, authors = advance_search(documents, vd)
    total = len(documents)
    return {
        'list': documents[start_num:(page_size * page_num)] if total > start_num else [],
        'sources': sources,
        'authors': authors,
        'total': total,
    }


def search_authors(user_id, content, page_size=10, page_num=1, limit=100):
    start_num = page_size * (page_num - 1)
    logger.info(f"limit: [{start_num}: {page_size * page_num}]")
    if cache_data := search_result_from_cache(user_id, content, page_size, page_num, search_type='author'):
        return cache_data
    authors = RagAuthors.search_authors(content, limit=limit)
    authors_list = AuthorsDetailSerializer(authors, many=True).data
    search_result_save_cache(user_id, content, authors_list, search_type='author')
    return {
        'list': authors_list[start_num:(page_size * page_num)] if len(authors_list) > start_num else [],
        'total': len(authors_list),
    }


def get_documents_by_rag(rag_data):
    """
    批量处理 Document
    """
    rag_dict = {f"{d['collection_id']}-{d['doc_id']}": d for d in rag_data}
    rag_docs = [{'id': None, 'collection_id': d['collection_id'], 'doc_id': d['doc_id']} for d in rag_data]
    exit_d = Document.raw_by_docs(rag_docs) if rag_docs else []
    exit_dict = {f"{d.collection_id}-{d.doc_id}": d for d in exit_d}
    exit_documents = []
    exit_docs = [{'id': d.id, 'collection_id': d.collection_id, 'doc_id': d.doc_id} for d in exit_documents]
    diff_docs = Document.difference_docs(rag_docs, exit_docs)
    diff_rag = [rag_dict[f"{d['collection_id']}-{d['doc_id']}"] for d in diff_docs]

    # diff_documents = Document.objects.bulk_create([Document(**d) for d in diff_rag])
    if diff_rag:
        new_data = []
        for d in diff_rag:
            if exit_d := exit_dict.get(f"{d['collection_id']}-{d['doc_id']}"):
                d['id'] = exit_d.id
            else:
                d['id'] = str(uuid.uuid4())
            d['created_at'] = datetime.datetime.now()
            d['updated_at'] = datetime.datetime.now()
            new_data.append(d)
        bulk_insert_ignore_duplicates(Document, new_data)
        documents = Document.raw_by_docs(rag_docs) if rag_docs else []
    else:
        documents = exit_documents
    return {f"{d.collection_id}-{d.doc_id}": d for d in documents}


def search_result_save_cache(user_id, content, data, search_result_expires=600, search_type='paper', limit=None):
    if limit:
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}:{limit}'
    else:
        doc_search_redis_key_prefix = f'scinav:{search_type}:search:{user_id}'
    content_hash = str_hash(f'{content}')
    redis_key = f'{doc_search_redis_key_prefix}:{content_hash}'
    res = cache.set(redis_key, json.dumps(data), search_result_expires)
    return res


def get_document_library_list(user_id, list_type, page_size=10, page_num=1, keyword=None):
    # {'filename': '', 'document_title': '', 'status': '-', 'record_time': '-'}
    start_num = page_size * (page_num - 1)
    list_data = []
    public_total, subscribe_total, sub_add_list, my_total = 0, 0, [], 0
    if list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.ALL:
        # public
        filter_query = Q(id__in=['arxiv'], del_flag=False)
        if keyword:
            filter_query &= Q(title__contains=keyword)
        public_colles = Collection.objects.filter(filter_query).all()
        if public_colles:
            public_total = len(public_colles)
            if start_num == 0:
                for public_colle in public_colles:
                    list_data.append({
                        'id': public_colle.id,
                        'collection_id': public_colle.id,
                        'filename': public_colle.title,
                        'document_title': None,
                        'document_id': None,
                        'pages': None,
                        'status': '-',
                        'record_time': None,
                        'type': 'public',
                        'reference_type': 'public',
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
    filter_query = Q(user_id=user_id, del_flag=False)
    if keyword:
        filter_query &= Q(filename__contains=keyword) | Q(document__title__contains=keyword)
    if list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.ALL:
        filter_query &= Q(task_status__in=[
            DocumentLibrary.TaskStatusChoices.COMPLETED,
            DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
            DocumentLibrary.TaskStatusChoices.PENDING,
            DocumentLibrary.TaskStatusChoices.QUEUEING,
            DocumentLibrary.TaskStatusChoices.ERROR,
        ])
    elif list_type == DocumentLibraryListQuerySerializer.ListTypeChoices.IN_PROGRESS:
        filter_query &= Q(task_status__in=[
            DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
            DocumentLibrary.TaskStatusChoices.PENDING,
            DocumentLibrary.TaskStatusChoices.QUEUEING,
        ])
    elif list_type in [
        DocumentLibraryListQuerySerializer.ListTypeChoices.ERROR,
        DocumentLibraryListQuerySerializer.ListTypeChoices.FAILED
    ]:
        filter_query &= Q(task_status=DocumentLibrary.TaskStatusChoices.ERROR)
    else:
        filter_query &= Q(task_status=DocumentLibrary.TaskStatusChoices.COMPLETED)
    query_set = DocumentLibrary.objects.filter(filter_query).order_by('-updated_at')
    my_total = query_set.count()
    if len(list_data) < page_size:
        my_start_num = 0 if list_data else max(start_num - public_total - subscribe_total, 0)
        my_end_num = my_start_num + page_size - len(list_data)
        query_set = query_set[my_start_num:my_end_num]
        my_list_data = []
        document_ids = [str(doc_lib.document_id) for doc_lib in query_set if doc_lib.document_id]
        documents = Document.objects.filter(id__in=document_ids).all()
        documents_dict = {str(document.id): document for document in documents}
        for doc_lib in query_set:
            ref_type, document = None, documents_dict.get(str(doc_lib.document_id), None)
            document_title = document.title if document else '-'
            filename = doc_lib.filename if doc_lib.filename else document_title
            if document:
                if (
                    document.ref_doc_id and document.ref_collection_id
                    and document.collection_type == Collection.TypeChoices.PERSONAL
                ):
                    ref_type = 'reference'
                    if document.full_text_accessible:
                        ref_type = 'reference&full_text_accessible'
                elif document.collection_type == Collection.TypeChoices.PUBLIC:
                    ref_type = document.collection_id

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


def document_update_from_rag(collection_type, collection_id, doc_id):
    if not collection_type:
        collection_type = (
            Document.TypeChoices.PUBLIC
            if collection_id in ['arxiv', 's2']
            else Document.TypeChoices.PERSONAL
        )
    validated_data = {
        'collection_id': collection_id,
        'collection_type': collection_type,
        'doc_id': doc_id,
    }
    doc_info = RagDocument.get(validated_data)
    return document_update_from_rag_ret(doc_info)


def documents_update_from_rag(begin_id, end_id):
    documents = Document.objects.filter(doc_id__gte=begin_id, doc_id__lte=end_id).values_list(
        'doc_id', 'collection_id', 'collection_type', named=True).all()
    for d in documents:
        document_update_from_rag(d.collection_type, d.collection_id, d.doc_id)
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
            document = document_update_from_rag(collection_type, collection_id, doc_id)
        except Exception as e:
            logger.error(f"import_papers_to_collection error: {doc_id}, {e}")
            skip_ids.append(doc_id)
            continue
        count += 1
        c_doc_objs.append(CollectionDocument(
            collection_id=personal_collection_id,
            document_id=document.id,
            full_text_accessible=True,
            del_flag=False,
        ))
        coll_doc = {
            'collection_id': personal_collection_id,
            'document_id': document.id,
            'full_text_accessible': True,
            'del_flag': False,
        }
        collection, created = CollectionDocument.objects.update_or_create(
            coll_doc, collection_id=personal_collection_id, document_id=document.id)
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


def update_exist_documents():
    page_size = 200
    page_num = 1
    documents = Document.objects.filter(del_flag=False).values(
        'collection_type', 'doc_id', 'collection_id').order_by(
        'updated_at')[page_size * (page_num - 1):page_size * page_num]
    while documents:
        logger.debug(f'ddddddddd page_size: {page_size}, page_num: {page_num}')
        for d in documents:
            document_update_from_rag(d['collection_type'], d['collection_id'], d['doc_id'])
            logger.debug(f"ddddddddd success update doc_id: {d['doc_id']}")
        page_num += 1
        documents = Document.objects.filter(del_flag=False).values(
            'collection_type', 'doc_id', 'collection_id').order_by(
            'updated_at')[page_size * (page_num - 1):page_size * page_num]


def document_personal_upload(validated_data):
    vd = validated_data
    files = vd.get('files')
    openapi_key_id = vd.get('openapi_key_id')
    instances = []
    document_count = len(files)
    limit_info = LimitCheckSerializer.embedding_limit(vd['user_id'])
    if limit_info['daily'] and limit_info['daily'] < limit_info['used_day'] + document_count:
        return 130006, 'exceed day limit', {
            'used': limit_info['used_day'], 'limit': limit_info['daily'], 'need': document_count
        }
    elif limit_info['monthly'] and limit_info['monthly'] < limit_info['used_month'] + document_count:
        return 130007, 'exceed month limit', {
            'used': limit_info['used_month'], 'limit': limit_info['monthly'], 'need': document_count
        }

    for file in files:
        doc_lib_data = {
            'user_id': vd['user_id'],
            'filename': file['filename'],
            'object_path': file['object_path'],
            'del_flag': False,
            'task_status': DocumentLibrary.TaskStatusChoices.PENDING,
            'task_type': Document.TypeChoices.PERSONAL,
            'task_id': None,
            'error': None,
        }
        filename_count = DocumentLibrary.objects.filter(
            filename__startswith=file['filename'], user_id=vd['user_id'], del_flag=False).count()
        if filename_count:
            doc_lib_data['filename'] = f"{file['filename']}({filename_count})"
        try:
            rag_ret = RagDocument.ingest_personal_paper(vd['user_id'], file['object_path'])
            doc_lib_data['task_id'] = rag_ret['task_id']
            doc_lib_data['task_status'] = (
                rag_ret['task_status']
                if rag_ret['task_status'] != DocumentLibrary.TaskStatusChoices.COMPLETED
                else DocumentLibrary.TaskStatusChoices.IN_PROGRESS
            )
            if doc_lib_data['task_status'] == DocumentLibrary.TaskStatusChoices.ERROR:
                doc_lib_data['error'] = {'error_code': rag_ret['error_code'], 'error_message': rag_ret['error_message']}
        except Exception as e:
            logger.warning(f"RagDocument.ingest_personal_paper error: {e}")
        instance, _ = DocumentLibrary.objects.update_or_create(
            doc_lib_data, user_id=vd['user_id'], filename=file['filename'], object_path=file['object_path'])
        instances.append(instance)
        # add record to MemberUsageLog
        clock_time = MemberTimeClock.get_member_time_clock(vd['user_id'])
        if clock_time:
            now = clock_time
        else:
            now = datetime.datetime.now()
        member_ul = MemberUsageLog.objects.create(
            user_id=vd['user_id'],
            openapi_key_id=openapi_key_id,
            type=MemberUsageLog.UType.EMBEDDING,
            obj_id1=instance.id,
            obj_id2=instance.task_id,
            status=MemberUsageLog.Status.UNKNOWN,
            created_at=now,
        )
        if clock_time:
            MemberUsageLog.objects.filter(id=member_ul.id).update(created_at=now)
    return 0, 'success', instances


def document_library_add(
    user_id, document_ids, collection_id, bot_id, add_type, keyword=None, search_info=None
):
    """
    添加个人库：
     1. 搜索结果添加
     2. 收藏夹添加  all arxiv 全量库 个人库
     3. 文献列表添加
    """
    collection_ids = [collection_id] if collection_id else []
    is_all = True
    all_document_ids, ref_ds, bot = [], [], None
    if bot_id:
        bot = Bot.objects.filter(id=bot_id, del_flag=False).first()
    if add_type == DocLibAddQuerySerializer.AddTypeChoices.DOCUMENT_SEARCH or (
        search_info and search_info.get('content')
    ):
        search_info['page_num'] = 1
        search_info['page_size'] = search_info.get('limit', 100)
        search_result = search(user_id, search_info)
        if search_result:
            all_document_ids = [d['id'] for d in search_result['list']]
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.AUTHOR_SEARCH or (
        search_info and search_info.get('author_id')
    ):
        search_info['page_num'] = 1
        search_info['page_size'] = search_info.get('limit', 1000)
        search_result = author_documents(user_id, search_info.get('author_id'), search_info)
        if search_result:
            all_document_ids = [d['id'] for d in search_result['list']]
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_ARXIV:
        coll_documents, d1, d2, _ = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'arxiv')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_S2:
        coll_documents, d1, d2, _ = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 's2')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_SUBSCRIBE_FULL_TEXT:
        coll_documents, d1, d2, _ = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'subscribe_full_text', bot)
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_DOCUMENT_LIBRARY:
        if bot_id:
            collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).values('collection_id').all()
            collection_ids += [c['collection_id'] for c in collections]
        coll_documents, d1, d2, _ = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'document_library')
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
    elif add_type == DocLibAddQuerySerializer.AddTypeChoices.COLLECTION_ALL:
        if bot_id:
            collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).values('collection_id').all()
            collection_ids += [c['collection_id'] for c in collections]
        coll_documents, d1, d2, ref_ds = CollectionDocumentListSerializer.get_collection_documents(
            user_id, collection_ids, 'all', bot)
        all_document_ids = [d['document_id'] for d in coll_documents.all()] if coll_documents else []
        if ref_ds:
            all_document_ids += ref_ds
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
    # document_ids = _get_public_document_ids(user_id, document_ids)
    if ref_ds:
        document_ids = list(set(document_ids) | set(ref_ds))
    code, msg, data = update_document_lib(user_id, document_ids, keyword=keyword)
    if code == 0:
        async_document_library_task.apply_async()
    return code, msg, data


def _get_public_document_ids(user_id, document_ids):
    new_document_ids = []
    pub_documents = Document.objects.filter(
        id__in=document_ids, collection_type=Document.TypeChoices.PUBLIC).values('id').all()
    if pub_documents:
        new_document_ids = [d['id'] for d in pub_documents]
    personal_documents = Document.objects.filter(
        id__in=document_ids, collection_type=Document.TypeChoices.PERSONAL, ref_doc_id__gt=0).all()
    if personal_documents:
        docs = []
        for d in personal_documents:
            if d.collection_id == user_id:
                new_document_ids.append(d.id)
            else:
                docs.append({'id': None, 'doc_id': d.ref_doc_id, 'collection_id': d.ref_collection_id})
        if docs:
            per_documents = Document.raw_by_docs(docs, fileds='id')
            new_document_ids += [d.id for d in per_documents] if per_documents else []
    return new_document_ids


def doc_lib_batch_operation_check(user_id, validated_data):
    ids = validated_data.get('ids')
    list_type = validated_data.get('list_type')
    is_all = validated_data.get('is_all')
    keyword = validated_data.get('keyword')
    if is_all:
        if list_type == 'failed':
            filter_query = Q(user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.ERROR)
        elif list_type == 'all':
            filter_query = Q(user_id=user_id, del_flag=False)
        elif list_type == 'in_progress':
            filter_query = Q(user_id=user_id, del_flag=False, task_status__in=[
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS,
                DocumentLibrary.TaskStatusChoices.PENDING,
            ])
        else:
            filter_query = Q(user_id=user_id, del_flag=False, task_status=DocumentLibrary.TaskStatusChoices.COMPLETED)
        if ids:
            filter_query &= ~Q(id__in=ids, )
        if keyword:
            filter_query &= (Q(document_title__icontains=keyword) | Q(filename__icontains=keyword))
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
        return 130003, {}, '您选择的文件当前尚未收录完成，无法执行该操作，请您耐心等待或修改选择对象。'
    document_ids = [doclib.document_id for doclib in doc_libs.all() if doclib.document_id]
    return 0, {'document_ids': document_ids}, ''


def document_library_delete(user_id, ids, list_type, keyword=None):
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
    if keyword:
        filter_query &= (Q(document_title__icontains=keyword) | Q(filename__icontains=keyword))
    doc_libs = DocumentLibrary.objects.filter(filter_query)
    all_doc_libs = doc_libs.all()
    user_per_document_ids = [doclib.document_id for doclib in all_doc_libs if doclib.document_id and doclib.filename]
    user_pub_doc_ids = [doclib.document_id for doclib in all_doc_libs if doclib.task_type == 'public']
    in_progress_document_libs = [doclib for doclib in all_doc_libs if doclib.task_status in ['in_progress', 'queueing']]
    # delete CollectionDocument
    user_collections = Collection.objects.filter(user_id=user_id, del_flag=False).values('id').all()
    user_collection_ids = [c['id'] for c in user_collections]
    for coll_id in user_collection_ids:
        effect_num = CollectionDocument.objects.filter(
            document_id__in=user_per_document_ids,
            collection_id=coll_id,
        ).update(del_flag=True)
        if effect_num:
            coll_documents_total = CollectionDocument.objects.filter(collection_id=coll_id, del_flag=False).count()
            Collection.objects.filter(id=coll_id).update(total_personal=coll_documents_total)
            async_update_conversation_by_collection.apply_async(args=(coll_id,))
    effect_pub_coll_ids = CollectionDocument.objects.filter(
        collection_id__in=user_collection_ids, document_id__in=user_pub_doc_ids
    ).values_list('collection_id', flat=True).distinct('collection_id').all()
    for coll_id in effect_pub_coll_ids:
        async_update_conversation_by_collection.apply_async(args=(coll_id,))

    # delete Document
    Document.objects.filter(id__in=user_per_document_ids, collection_id=user_id).update(del_flag=True)
    # todo rag delete
    to_del_documents = Document.objects.filter(
        id__in=user_per_document_ids, collection_type=Document.TypeChoices.PERSONAL
    ).values('id', 'collection_id', 'doc_id').all()
    for document in to_del_documents:
        RagDocument.delete_personal_paper(document['collection_id'], document['doc_id'])
    failed_tasks = []
    for task in in_progress_document_libs:
        new_task, task_result = update_document_library_task(task)
        if new_task:
            if new_task.task_status == DocumentLibrary.TaskStatusChoices.COMPLETED and task.task_type == 'personal':
                RagDocument.delete_personal_paper(task_result['paper']['collection_id'], task_result['paper']['doc_id'])
            elif new_task.task_status in [
                DocumentLibrary.TaskStatusChoices.IN_PROGRESS, DocumentLibrary.TaskStatusChoices.PENDING
            ]:
                RagDocument.cancel_ingest_task(task.task_id)
        else:
            failed_tasks.append(task)
    # delete search cache when delete personal document_library
    if user_per_document_ids:
        search_result_delete_cache(user_id)
    # delete DocumentLibrary
    effected_num = doc_libs.update(del_flag=True)
    for failed_task in failed_tasks:
        failed_task.del_flag = False
        failed_task.save()
        effected_num -= 1
    return effected_num


def get_reference_formats(document):
    """
        APA 格式 （参考 https://wordvice.cn/citation-guide/apa）
            作者姓氏, 名字首字母 中间名首字母. (出版日期). 网页标题. 网站名称. URL
        MLA 格式 （参考 https://wordvice.cn/citation-guide/mla）
            作者姓氏 作者名字 & 作者姓氏 作者名字. “文章标题.” 期刊标题, 出版日期.
        GB/T 7714-2015
            https://lgc0208.github.io/reference_format_generation/
            作者. 会议文集名：会议文集其他信息[C]. 出版地：出版者，出版年. 获取和访问路径.
        BibTeX（中间无空格）

    """
    # authors = ','.join(document['authors'])
    # title = document['title']
    # year = document['year']
    # source = document['journal'] if document['journal'] else document['conference'] \
    #     if document['conference'] else document['venue']
    # pages = document['pages'] if document['pages'] else ''
    # venue = document['venue'] if document['venue'] else ''
    # pub_type = (
    #     document['pub_type']
    #     if document['pub_type'] else 'conference'
    #     if document['conference'] else 'journal'
    #     if document['journal'] else ''
    # )
#     pub_data = document['pub_date'] if document['pub_date'] else ''
#     # apa
#     apa = Document.get_doc_apa(document['authors'], year, title, source)
#     mla = Document.get_doc_mla(document['authors'], year, title, source)
#     pub_type_tag = '[C]' if pub_type == 'conference' else '[J]' if pub_type == 'journal' else ''
#     gbt = Document.get_doc_gbt(document['authors'], year, title, source, pub_type_tag)
#     # bibtex
#     # conference
#     # @conference{RN04,
#     #   author    = "Holleis, Paul and Wagner, Matthias and Koolwaaij, Johan",
#     #   title     = "Studying mobile context-aware social services in the wild",
#     #   booktitle = "Proc. of the 6th Nordic Conf. on Human-Computer Interaction",
#     #   series    = "NordiCHI",
#     #   year      = 2010,
#     #   pages     = "207--216",
#     #   publisher = "ACM",
#     #   address   = "New York, NY"
#     # }
#     bibtex = ''
#     info = {
#         'authors': authors,
#         'title': title,
#         'venue': venue,
#         'year': year,
#         'pages': f'number={pages}' if pages else '',
#     }
#     if pub_type == 'conference':
#         template = '''@inproceedings{{CitekeyInproceedings,
#     author={authors},
#     title={title},
#     booktitle={venue},
#     year={year}
# }}'''
#         bibtex = template.format(**info)
#     # journal
#     # @article{RN01,
#     #   author   = "P. J. Cohen",
#     #   title    = "The independence of the continuum hypothesis",
#     #   journal  = "Proceedings of the National Academy of Sciences",
#     #   year     = 1963,
#     #   volume   = "50",
#     #   number   = "6",
#     #   pages    = "1143--1148",
#     # }
#     else:  # pub_type == 'journal':
#         template = '''@article{{CitekeyArticle,
#     author={{{authors}}},
#     title={{{title}}},
#     journal={{{venue}}},
#     year={{{year}}}
# }}'''
#         bibtex = template.format(**info)

    return {
        'GB/T': document.get_csl_formate('gbt'),
        'MLA': document.get_csl_formate('mla'),
        'APA': document.get_csl_formate('apa'),
        'BibTex': document.get_bibtex_format(),
    }


def get_csl_reference_formats(document: Document):
    return {
        'GB/T': document.get_csl_formate('gbt'),
        'MLA': document.get_csl_formate('mla'),
        'APA': document.get_csl_formate('apa'),
        'BibTex': document.get_bibtex_format(),
    }
