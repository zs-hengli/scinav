import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from collection.service import (collection_detail, collection_docs,
                                collection_list, collections_docs)
from core.utils.views import check_keys, extract_json, my_json_response

logger = logging.getLogger(__name__)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Index(APIView):

    def get(self, request, *args, **kwargs):  # noqa
        logger.debug(f'kwargs: {kwargs}')
        data = {'desc': 'collection index'}

        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
@permission_classes([AllowAny])
class Collection(APIView):

    def get(self, request, collection_id=None, *args, **kwargs):  # noqa
        user_id = request.user.id
        if collection_id:
            data = collection_detail(user_id, collection_id)
        else:
            data = {'list': collection_list(user_id, True)}
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
@permission_classes([AllowAny])
class CollectionDocument(APIView):

    @staticmethod
    def get(request, collection_id=None, *args, **kwargs):  # noqa
        if collection_id:
            data = collection_docs(collection_id)
        else:
            query = kwargs['request_data']['GET']
            check_keys(query, ['collection_ids'])
            if isinstance(query['collection_ids'], str):
                query['collection_ids'] = query['collection_ids'].split(',')
            query_data = {
                'collection_ids': query['collection_ids'],
                'page_size': int(query.get('page_size', 10)),
                'page_num': int(query.get('page_num', 1)),
            }
            data = collections_docs(query_data['collection_ids'], query_data['page_size'], query_data['page_num'])
        return my_json_response(data)
