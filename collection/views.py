import logging

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from collection.models import Collection
from collection.serializers import (CollectionCreateSerializer,
                                    CollectionDetailSerializer,
                                    CollectionDocUpdateSerializer,
                                    CollectionUpdateSerializer)
from collection.service import (collection_docs, collection_list,
                                collections_docs)
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
@method_decorator(require_http_methods(['GET', 'POST', 'PUT', 'DELETE']), name='dispatch')
@permission_classes([AllowAny])
class Collections(APIView):

    @staticmethod
    def get(request, collection_id=None, *args, **kwargs):
        user_id = request.user.id
        if collection_id:
            collection = Collection.objects.get(pk=collection_id, user_id=user_id)
            data = CollectionDetailSerializer(collection).data
        else:
            data = {'list': collection_list(user_id, True)}
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        request_data = request.data
        request_data['user_id'] = request.user.id
        serial = CollectionCreateSerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        collection = serial.create(serial.validated_data)
        data = CollectionDetailSerializer(collection).data
        return my_json_response(data)

    @staticmethod
    def put(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=-1, msg='validate collection_id error')

        request_data = request.data
        serial = CollectionUpdateSerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')

        collection = serial.update(collection, validated_data=serial.validated_data)
        data = CollectionUpdateSerializer(collection).data
        return my_json_response(data)

    @staticmethod
    def delete(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=-1, msg='validate collection_id error')
        collection.del_flag = True
        collection.save()
        return my_json_response({'collection_id': collection_id})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT']), name='dispatch')
@permission_classes([AllowAny])
class CollectionDocuments(APIView):

    @staticmethod
    def get(request, collection_id=None, *args, **kwargs):
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

    @staticmethod
    def put(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=-1, msg='validate collection_id error')
        post_data = request.data
        post_data['user_id'] = user_id
        post_data['collection_id'] = collection_id
        serial = CollectionDocUpdateSerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        serial.create(serial.validated_data)
        data = {'document_ids': serial.validated_data['document_ids']}

        return my_json_response(data)
