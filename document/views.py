import logging

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bot.rag_service import Document as RagDocument
from core.utils.views import check_keys, extract_json, my_json_response
from document.models import Document, DocumentLibrary
from document.serializers import DocumentRagGetSerializer, DocumentUrlSerializer, \
    DocumentDetailSerializer, GenPresignedUrlQuerySerializer, DocumentUploadQuerySerializer, \
    DocumentLibraryListQuerySerializer, DocumentRagUpdateSerializer, DocLibUpdateNameQuerySerializer, \
    DocLibAddQuerySerializer, DocLibDeleteQuerySerializer, DocLibCheckQuerySerializer
from document.service import search, documents_update_from_rag, presigned_url, document_personal_upload, \
    get_document_library_list, document_library_add, document_library_delete, doc_lib_batch_operation_check

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
        body = kwargs['request_data']['JSON']
        user_id = request.user.id
        check_keys(body, ['content'])
        post_data = {
            'content': body['content'],
            'page_size': int(body.get('page_size', 10)),
            'page_num': int(body.get('page_num', 1)),
        }
        data = search(user_id, body['content'], post_data['page_size'], post_data['page_num'])
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT', 'GET']), name='dispatch')
class Documents(APIView):

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).first()
        if not document:
            return my_json_response(code=1, msg=f'document not found by document_id={document_id}')
        return my_json_response(DocumentDetailSerializer(document).data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', "POST", 'PUT', 'DELETE']), name='dispatch')
class DocumentsLibrary(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        """
        get documents by user_id
        """
        user_id = request.user.id
        serial = DocumentLibraryListQuerySerializer(data=request.query_params)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        vd = serial.validated_data
        data = get_document_library_list(user_id, vd['list_type'], vd['page_size'], vd['page_num'])
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = DocLibAddQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        vd = serial.validated_data
        document_library_add(
            request.user.id, vd['document_ids'], vd['collection_id'], vd['bot_id'], vd['add_type'], vd['search_content']
        )
        return my_json_response({})

    @staticmethod
    def put(request, document_library_id, *args, **kwargs):
        query = request.data
        serial = DocLibUpdateNameQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
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
            return my_json_response(serial.errors, code=100001, msg='invalid post data')
        vd = serial.validated_data
        document_library_delete(user_id, vd.get('ids'), vd.get('is_all'))
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
        code, data = doc_lib_batch_operation_check(request.user.id, serial.validated_data)
        if code == 0:
            return my_json_response({'document_ids': data})
        else:
            return my_json_response(code=code, msg=data, data={})


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
            return my_json_response(serial.errors, code=1, msg='invalid post data')
        data = document_personal_upload(serial.validated_data)
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class DocumentsUrl(APIView):
    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).values_list('id', 'object_path', named=True).first()
        if not document:
            return my_json_response(code=1, msg=f'document not found by document_id={document_id}')
        data = DocumentUrlSerializer(document).data
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT']), name='dispatch')
class DocumentsRagUpdate(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        data = {}
        # data = import_documents_from_json()
        return my_json_response(data)

    @staticmethod
    def put(request, begin_id, end_id, *args, **kwargs):
        data = documents_update_from_rag(begin_id, end_id)
        return my_json_response(data)

    @staticmethod
    def POST(request, *args, **kwargs):
        """
        update or create document by (doc_id,collection_type,collection_id)
        from rag paper info
        """
        query = request.data
        serial = DocumentRagUpdateSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=1, msg='invalid put data')
        doc_info = RagDocument.get(serial.validated_data)
        serial = DocumentRagGetSerializer(data=doc_info)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=2, msg='invalid get rag paper info')
        document, _ = Document.objects.update_or_create(
            serial.validated_data,
            doc_id=serial.validated_data['doc_id'],
            collection_type=serial.validated_data['collection_type'],
            collection_id=serial.validated_data['collection_id']
        )
        data = DocumentRagUpdateSerializer(document).data
        return my_json_response(data)
