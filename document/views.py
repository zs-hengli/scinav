import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.views import check_keys, extract_json, my_json_response
from document.service import gen_s3_presigned_post, search

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


# update_document_lib
