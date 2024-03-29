import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import check_keys, extract_json, my_json_response
from document.models import Document
from document.serializers import DocumentUpdateSerializer, DocumentRagGetSerializer, DocumentUrlSerializer, \
    DocumentDetailSerializer
from document.service import gen_s3_presigned_post, search, documents_update_from_rag
from bot.rag_service import Document as RagDocument

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
@method_decorator(require_http_methods(['GET']), name='dispatch')
# @permission_classes([AllowAny])
class GenPresignedUrl(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        query = kwargs['request_data']['GET']
        check_keys(query, ['bucket', 'path'])
        ret = gen_s3_presigned_post(bucket=query['bucket'], path=query['path'])
        data = ret
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
# @permission_classes([AllowAny])
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
# @permission_classes([AllowAny])
class Documents(APIView):
    @staticmethod
    def put(request, *args, **kwargs):
        """
        update or create document by (doc_id,collection_type,collection_id)
        from rag paper info
        """
        query = request.data
        serial = DocumentUpdateSerializer(data=query)
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
        data = DocumentUpdateSerializer(document).data
        return my_json_response(data)

    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).first()
        if not document:
            return my_json_response(code=1, msg=f'document not found by document_id={document_id}')
        return my_json_response(DocumentDetailSerializer(document).data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
# @permission_classes([AllowAny])
class DocumentsUrl(APIView):
    @staticmethod
    def get(request, document_id, *args, **kwargs):
        document = Document.objects.filter(id=document_id).values_list('id', 'object_path', named=True).first()
        if not document:
            return my_json_response(code=1, msg=f'document not found by document_id={document_id}')
        data = DocumentUrlSerializer(document).data
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['PUT']), name='dispatch')
# @permission_classes([AllowAny])
class DocumentsRagUpdate(APIView):
    @staticmethod
    def put(request, begin_id, end_id, *args, **kwargs):
        data = documents_update_from_rag(begin_id, end_id)
        return my_json_response(data)
