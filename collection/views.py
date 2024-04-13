import logging

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from collection.models import Collection
from collection.serializers import (CollectionCreateSerializer,
                                    CollectionDetailSerializer,
                                    CollectionDocUpdateSerializer,
                                    CollectionUpdateSerializer, CollectionDeleteQuerySerializer,
                                    CollectionDocumentListQuerySerializer, CollectionCheckQuerySerializer)
from collection.service import (collection_list, collections_docs, generate_collection_title, collection_delete,
                                collections_delete, collection_chat_operation_check, collection_delete_operation_check)
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
class Collections(APIView):

    @staticmethod
    def get(request, collection_id=None, list_type='my', *args, **kwargs):
        logger.info(f'collection_id: {collection_id}, list_type: {list_type}')
        list_type = list_type.split(',')
        types = ['my', 'public', 'subscribe']
        if set(list_type) - set(types):
            return my_json_response({}, code=-1, msg='list_type error')
        query = request.query_params
        page_size = int(query.get('page_size', 10))
        page_num = int(query.get('page_num', 1))

        user_id = request.user.id
        if collection_id:
            collection = Collection.objects.get(pk=collection_id, user_id=user_id)

            data = CollectionDetailSerializer(collection).data
        else:
            data = collection_list(user_id, list_type=list_type, page_size=page_size, page_num=page_num)
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        query['user_id'] = request.user.id
        serial = CollectionCreateSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        if vd.get('document_ids'):
            title = generate_collection_title(document_titles=vd['document_titles'])
            vd['title'] = title
        elif vd.get('search_content'):
            vd['title'] = generate_collection_title(content=vd['search_content'])

        collection = serial.create({
            'title': vd['title'],
            'user_id': vd['user_id'],
            'type': vd['type']
        })
        # update collection document
        update_data = {
            'user_id': vd['user_id'],
            'collection_id': str(collection.id),
            'document_ids': vd.get('document_ids'),
            'is_all': vd.get('is_all', False),
            'action': 'add',
        }
        if vd.get('search_content'):
            update_data['search_content'] = vd['search_content']
        update_serial = CollectionDocUpdateSerializer(data=update_data)
        update_serial.is_valid(raise_exception=True)
        update_serial.create(update_serial.validated_data)

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
    def delete(request, collection_id=None, *args, **kwargs):
        def has_public_collection(c_ids):
            return Collection.objects.filter(id__in=c_ids, del_flag=False, type=Collection.TypeChoices.PUBLIC).exists()

        user_id = request.user.id
        if collection_id:
            collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
            if not collection:
                return my_json_response({}, code=-1, msg='收藏夹不存在')
            if collection.type == Collection.TypeChoices.PUBLIC:
                return my_json_response({}, code=-2, msg=_('您无法删除公共库或订阅专题收藏夹，请重新选择。'))
            collection_delete(collection)
        else:
            query = request.data
            query['user_id'] = user_id
            serial = CollectionDeleteQuerySerializer(data=query)
            if not serial.is_valid():
                return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
            query_data = serial.validated_data
            if not query_data['is_all'] and query_data.get('ids') and has_public_collection(query_data['ids']):
                return my_json_response({}, code=-2, msg=_('您无法删除公共库或订阅专题收藏夹，请重新选择。'))
            collections_delete(query_data)
        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET', 'PUT']), name='dispatch')
class CollectionDocuments(APIView):

    @staticmethod
    def get(request, collection_id=None, *args, **kwargs):
        query = request.query_params.dict()
        query['user_id'] = request.user.id
        if collection_id:
            query['collection_ids'] = [collection_id]
        check_keys(query, ['collection_ids'])
        if isinstance(query['collection_ids'], str):
            query['collection_ids'] = query['collection_ids'].split(',')

        serial = CollectionDocumentListQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        data = collections_docs(serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def put(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=-1, msg='收藏夹不存在')
        if collection.type == Collection.TypeChoices.PUBLIC:
            return my_json_response({}, code=-2, msg='此收藏夹不支持添加文献')

        post_data = request.data
        post_data['user_id'] = user_id
        post_data['collection_id'] = collection_id
        serial = CollectionDocUpdateSerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=-1, msg=f'validate error, {list(serial.errors.keys())}')
        if serial.validated_data['action'] == 'add':
            serial.create(serial.validated_data)
        else:
            serial.delete_document(serial.validated_data)

        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class CollectionChatOperationCheck(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        query['user_id'] = request.user.id
        serial = CollectionCheckQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        code, data = collection_chat_operation_check(request.user.id, serial.validated_data)
        if code == 0:
            return my_json_response(data)
        else:
            return my_json_response({}, code=code, msg=data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class CollectionDeleteOperationCheck(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        query['user_id'] = request.user.id
        serial = CollectionCheckQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        code, data = collection_delete_operation_check(request.user.id, serial.validated_data)
        if code == 0:
            return my_json_response(data)
        else:
            return my_json_response(data, code=code, msg=data['msg'])


