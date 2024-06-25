import logging
from time import sleep

from django.core.cache import cache
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.rag_service import Document as RagDocument
from collection.models import Collection
from core.utils.views import check_keys, extract_json, my_json_response
from document.models import Document, DocumentLibrary
from document.serializers import DocumentDetailSerializer, GenPresignedUrlQuerySerializer, \
    DocumentUploadQuerySerializer, \
    DocumentLibraryListQuerySerializer, DocumentRagUpdateSerializer, DocLibUpdateNameQuerySerializer, \
    DocLibAddQuerySerializer, DocLibDeleteQuerySerializer, DocLibCheckQuerySerializer, DocumentRagCreateSerializer, \
    ImportPapersToCollectionSerializer, AuthorsSearchQuerySerializer, AuthorsDocumentsQuerySerializer, \
    DocumentUploadResultSerializer
from document.service import search, presigned_url, document_personal_upload, \
    get_document_library_list, document_library_add, document_library_delete, doc_lib_batch_operation_check, \
    get_url_by_object_path, get_reference_formats, update_exist_documents, import_papers_to_collection, \
    document_update_from_rag, search_authors, author_detail, author_documents, get_csl_reference_formats
from document.tasks import async_add_user_operation_log

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'document index'}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class GenPresignedUrl(APIView):

    def post(self, request, *args, **kwargs):  # noqa
        query = request.data
        query['user_id'] = request.user.id
        serial = GenPresignedUrlQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, 400)
        validated_data = serial.validated_data
        ret = presigned_url(request.user.id, validated_data['filename'])
        data = ret
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class Search(APIView):

    def post(self, request, *args, **kwargs):  # noqa
        body = request.data
        user_id = request.user.id
        check_keys(body, ['content'])
        post_data = {
            'content': body['content'],
            'page_size': int(body.get('page_size', 10)),
            'page_num': int(body.get('page_num', 1)),
            'limit': min(int(body.get('limit', 100)), 1000),
        }
        data = search(user_id, body['content'], post_data['page_size'], post_data['page_num'], limit=post_data['limit'])
        async_add_user_operation_log.apply_async(kwargs={
            'user_id': user_id,
            'operation_type': 'search',
            'operation_content': body['content'],
        })
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class Authors(APIView):

    def get(self, request, author_id, *args, **kwargs):  # noqa
        user_id = request.user.id
        data = author_detail(user_id, author_id)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class AuthorsSearch(APIView):

    def post(self, request, *args, **kwargs):  # noqa
        body = request.data
        user_id = request.user.id
        serial = AuthorsSearchQuerySerializer(data=body)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = search_authors(
            user_id, vd['content'], vd['page_size'], vd['page_num'], topn=vd['topn'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class AuthorsDocuments(APIView):
    def get(self, request, author_id, *args, **kwargs):  # noqa
        user_id = request.user.id
        query = request.GET
        serial = AuthorsDocumentsQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        data = author_documents(user_id, author_id, vd['page_size'], vd['page_num'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT', 'GET']), name='dispatch')
class Documents(APIView):

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        user_id = request.user.id
        document = Document.objects.filter(id=document_id).first()
        if not document:
            return my_json_response(code=100002, msg=f'document not found by document_id={document_id}')
        document_data = DocumentDetailSerializer(document).data
        document_data['citation_count'] = len(document_data['citations']) if document_data['citations'] else document_data['citation_count']
        document_data['reference_count'] = len(document_data['references']) if document_data['references'] else document_data['reference_count']
        document_data['reference_formats'] = get_reference_formats(document)
        async_add_user_operation_log.apply_async(kwargs={
            'user_id': user_id,
            'operation_type': 'document_detail',
            'obj_id1': document.id,
            'obj_id2': document.collection_id,
            'obj_id3': document.doc_id,
        })
        return my_json_response(document_data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT', 'GET']), name='dispatch')
class DocumentsByDocId(APIView):

    @staticmethod
    def get(request, collection_id, doc_id, *args, **kwargs):
        user_id = request.user.id
        document = Document.objects.filter(collection_id=collection_id, doc_id=doc_id).first()
        if not document:
            document = document_update_from_rag(None, collection_id, doc_id)
        document_data = DocumentDetailSerializer(document).data
        document_data['citation_count'] = len(document_data['citations']) if document_data['citations'] else document_data['citation_count']
        document_data['reference_count'] = len(document_data['references']) if document_data['references'] else document_data['reference_count']
        document_data['reference_formats'] = get_reference_formats(document)
        async_add_user_operation_log.apply_async(kwargs={
            'user_id': user_id,
            'operation_type': 'document_detail',
            'obj_id1': document.id,
            'obj_id2': document.collection_id,
            'obj_id3': document.doc_id,
        })
        return my_json_response(document_data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsCitations(APIView):

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).first()
        if not document:
            return my_json_response(code=100002, msg=f'document not found by document_id={document_id}')
        citations = DocumentDetailSerializer.get_citations(document)
        data = {
            'list': citations,
            'total': len(citations)
        }
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsReferences(APIView):

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).first()
        if not document:
            return my_json_response(code=100002, msg=f'document not found by document_id={document_id}')
        references = DocumentDetailSerializer.get_references(document)
        data = {
            'list': references,
            'total': len(references)
        }
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsReferencesFormats(APIView):

    @staticmethod
    def get(request, document_id=None, collection_id=None, doc_id=None, *args, **kwargs):
        if document_id:
            document = Document.objects.filter(id=document_id).first()
        else:
            if not collection_id or not doc_id:
                return my_json_response(code=100001, msg='invalid query data')
            document = Document.objects.filter(collection_id=collection_id, doc_id=doc_id).first()
        if not document:
            return my_json_response(code=100002, msg=f'document not found')
        reference_formats = get_csl_reference_formats(document)
        return my_json_response(reference_formats)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', "POST", 'PUT', 'DELETE']), name='dispatch')
class DocumentsLibrary(APIView):
    @staticmethod
    def get(request, document_library_id=None, *args, **kwargs):
        """
        get documents by user_id
        """
        user_id = request.user.id
        if document_library_id:
            document_library = DocumentLibrary.objects.filter(id=document_library_id).first()
            if not document_library:
                return my_json_response(code=100002, msg=f'document_library not found by id={document_library_id}')
            status = (
                'completed' if document_library.task_status == DocumentLibrary.TaskStatusChoices.COMPLETED
                else 'in_progress' if document_library.task_status in [
                    DocumentLibrary.TaskStatusChoices.PENDING,
                    DocumentLibrary.TaskStatusChoices.QUEUEING,
                    DocumentLibrary.TaskStatusChoices.IN_PROGRESS
                ] else 'failed'
            )
            data = {
                'id': document_library_id,
                'status': status,
                'document_id': document_library.document_id,
                'task_type': document_library.task_type,
                'task_id': document_library.task_id,
                'object_path': document_library.object_path,
            }
        else:
            serial = DocumentLibraryListQuerySerializer(data=request.query_params)
            if not serial.is_valid():
                return my_json_response(serial.errors, code=100001, msg='invalid query data')
            vd = serial.validated_data
            data = get_document_library_list(user_id, vd['list_type'], vd['page_size'], vd['page_num'], vd['keyword'])
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = DocLibAddQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        vd = serial.validated_data
        document_libraries = document_library_add(
            request.user.id, vd['document_ids'], vd['collection_id'], vd['bot_id'], vd['add_type'],
            vd['search_content'], vd['author_id'], keyword=vd['keyword'], search_limit=vd['search_limit']
        )
        data = DocumentUploadResultSerializer(document_libraries, many=True).data
        return my_json_response({'list': data})

    @staticmethod
    def put(request, document_library_id, *args, **kwargs):
        query = request.data
        serial = DocLibUpdateNameQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid query data')
        vd = serial.validated_data
        filter_query = Q(filename=vd['filename'], del_flag=False) & ~Q(id=document_library_id)
        if DocumentLibrary.objects.filter(filter_query).exists():
            # todo msg_code
            return my_json_response(code=130001, msg=f'名称"{vd["filename"]}"已被占用请使用其他名称')
        DocumentLibrary.objects.filter(id=document_library_id, user_id=request.user.id).update(filename=vd['filename'])
        return my_json_response({})

    @staticmethod
    def delete(request, *args, **kwargs):
        user_id = request.user.id
        serial = DocLibDeleteQuerySerializer(data=request.data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid query data')
        vd = serial.validated_data
        document_library_delete(user_id, vd.get('ids'), vd.get('list_type'))
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class DocumentsLibraryOperationCheck(APIView):
    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = DocLibCheckQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        code, data, msg = doc_lib_batch_operation_check(request.user.id, serial.validated_data)
        return my_json_response(data, code=code, msg=data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class DocumentsPersonal(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        """
        upload personal paper to document
        """
        query = request.data
        query['user_id'] = request.user.id
        serial = DocumentUploadQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        validated_data = serial.validated_data
        document_libraries = document_personal_upload(validated_data)
        data = DocumentUploadResultSerializer(document_libraries, many=True).data
        return my_json_response({'list': data})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsUrl(APIView):
    @staticmethod
    def get(request, document_id=None, collection_id=None, doc_id=None, *args, **kwargs):
        user_id = request.user.id
        query = request.query_params.dict()
        is_paper_chat = int(query.pop('is_paper_chat', '0'))
        if document_id:
            document = Document.objects.filter(id=document_id).values(
                'id', 'title', 'object_path', 'collection_id', 'doc_id', 'collection_type',
                'ref_doc_id', 'ref_collection_id'
            ).first()
        elif collection_id and doc_id:
            document = Document.objects.filter(collection_id=collection_id, doc_id=doc_id).values(
                'id', 'title', 'object_path', 'collection_id', 'doc_id', 'collection_type',
                'ref_doc_id', 'ref_collection_id'
            ).first()
            if not document:
                document = document_update_from_rag(None, collection_id, doc_id)
        else:
            return my_json_response(code=100001, msg=f'document_id or (collection_id, doc_id) not found')
        if not document:
            return my_json_response(code=100002, msg=f'document not found')
        url_document = None
        if is_paper_chat and document['collection_id'] != 'arxiv' and not DocumentLibrary.objects.filter(
                user_id=user_id, document_id=document['id'], del_flag=False,
                task_status=DocumentLibrary.TaskStatusChoices.COMPLETED
        ).exists():
            url = ''
        elif document['collection_type'] == Document.TypeChoices.PERSONAL and user_id != document['collection_id']:
            url = None
            if document['ref_doc_id'] and document['ref_collection_id']:
                if (
                    ref_document := Document.objects.filter(
                        doc_id=document['ref_doc_id'], collection_id=document['ref_collection_id']
                    ).values('id', 'collection_id', 'doc_id', 'object_path').first()
                ):
                    url = get_url_by_object_path(user_id, ref_document['object_path'])
                    url_document = ref_document
        else:
            url = get_url_by_object_path(user_id, document['object_path'])
            url_document = document
        if url_document:
            async_add_user_operation_log.apply_async(kwargs={
                'user_id': user_id,
                'operation_type': 'document_url',
                'obj_id1': url_document['id'],
                'obj_id2': url_document['collection_id'],
                'obj_id3': url_document['doc_id'],
            })

        return my_json_response({
            'id': document['id'],
            'collection_id': document['collection_id'],
            'doc_id': document['doc_id'],
            'title': document['title'],
            'url': url
        })


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class DocumentsRagUpdate(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        data = {}
        update_exist_documents()
        return my_json_response(data)

    @staticmethod
    def put(request, *args, **kwargs):
        query = request.data
        serial = ImportPapersToCollectionSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid query data')
        data = import_papers_to_collection(serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        """
        update or create document by (doc_id,collection_type,collection_id)
        from rag paper info
        """
        query = request.data
        serial = DocumentRagUpdateSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid query data')
        doc_info = RagDocument.get(serial.validated_data)
        serial = DocumentRagCreateSerializer(data=doc_info)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100000, msg='invalid get rag paper info')
        document, _ = Document.objects.update_or_create(
            serial.validated_data,
            doc_id=serial.validated_data['doc_id'],
            collection_type=serial.validated_data['collection_type'],
            collection_id=serial.validated_data['collection_id']
        )
        data = DocumentRagUpdateSerializer(document).data
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsLibraryStatus(APIView):

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        status = DocumentDetailSerializer.get_document_library_status(request.user.id, document_id)
        return my_json_response({'status': status})
