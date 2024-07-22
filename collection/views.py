import datetime
import logging

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from collection.base_service import generate_collection_title
from collection.models import Collection
from collection.serializers import (CollectionCreateSerializer,
                                    CollectionDetailSerializer,
                                    CollectionUpdateSerializer, CollectionDeleteQuerySerializer,
                                    CollectionDocumentListQuerySerializer, CollectionCheckQuerySerializer,
                                    CollectionCreateBotCheckQuerySerializer, CollectionDocumentSelectedQuerySerializer,
                                    CollectionListQuerySerializer, AddDocument2CollectionQuerySerializer)
from collection.service import (collection_list, collections_docs,
                                collections_delete, collection_chat_operation_check, collection_delete_operation_check,
                                collections_published_bot_titles, collections_create_bot_check,
                                collections_reference_bot_titles, collection_document_add, collection_document_delete,
                                collection_documents_select_list, get_documents_titles,
                                get_search_documents_4_all_selected)
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

        user_id = request.user.id
        if collection_id:
            collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
            if not collection:
                return my_json_response(code=100002, msg='collection not found')
            data = CollectionDetailSerializer(collection).data
        else:
            query = request.query_params.dict()
            serial = CollectionListQuerySerializer(data=query)
            if not serial.is_valid():
                return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
            query_data = serial.validated_data
            data = collection_list(
                user_id,
                list_type=query_data['list_type'],
                page_size=query_data['page_size'],
                page_num=query_data['page_num'],
                keyword=query_data['keyword'],
            )
        return my_json_response(data)

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        user_id = request.user.id
        serial = CollectionCreateSerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        if vd.get('is_all'):
            documents = get_search_documents_4_all_selected(
                user_id, vd.get('document_ids'), vd['search_info'])
            vd['document_ids'] = [doc['id'] for doc in documents]
            vd['document_titles'] = [doc['title'] for doc in documents]
        else:
            vd['document_titles'] = get_documents_titles(vd['document_ids'])

        if vd.get('document_titles'):
            title = generate_collection_title(document_titles=vd['document_titles'])
        elif vd.get('search_info') and vd['search_info'].get('content'):
            title = vd['search_info']['content']
        else:
            title = generate_collection_title(document_titles=[])

        collection = serial.create({
            'title': title,
            'user_id': user_id,
            'type': vd['type'],
            'updated_at': datetime.datetime.now()
        })
        # update collection document
        update_data = {
            'user_id': user_id,
            'collection_id': str(collection.id),
            'document_ids': vd.get('document_ids'),
            'is_all': vd.get('is_all', False),
            'action': 'add',
        }
        collection_document_add(update_data)

        data = CollectionDetailSerializer(collection).data
        return my_json_response(data)

    @staticmethod
    def put(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=100002, msg='validate collection_id error')

        request_data = request.data
        serial = CollectionUpdateSerializer(data=request_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')

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
                return my_json_response({}, code=100002, msg='收藏夹不存在')
            if collection.type == Collection.TypeChoices.PUBLIC:
                return my_json_response({}, code=100003, msg=_('您无法删除公共库或订阅专题收藏夹，请重新选择。'))
            # collection_delete(collection)
            query = {
                'ids': [collection_id]
            }
        else:
            query = request.data
        query['user_id'] = user_id
        serial = CollectionDeleteQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        query_data = serial.validated_data
        if not query_data['is_all'] and query_data.get('ids') and has_public_collection(query_data['ids']):
            return my_json_response({}, code=100003, msg=_('您无法删除公共库或订阅专题收藏夹，请重新选择。'))
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
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        data = collections_docs(request.user.id, serial.validated_data)
        return my_json_response(data)

    @staticmethod
    def put(request, collection_id, *args, **kwargs):
        user_id = request.user.id
        collection = Collection.objects.filter(pk=collection_id, user_id=user_id).first()
        if not collection:
            return my_json_response({}, code=100002, msg='收藏夹不存在')
        if collection.type == Collection.TypeChoices.PUBLIC:
            return my_json_response({}, code=100003, msg='此收藏夹不支持添加文献')

        post_data = request.data
        serial = AddDocument2CollectionQuerySerializer(data=post_data)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        validated_data = serial.validated_data
        validated_data['user_id'] = user_id
        validated_data['collection_id'] = collection_id
        if validated_data.get('search_into') and (
            validated_data['search_into'].get('content') or validated_data['search_into'].get('author_id')
        ):
            documents = get_search_documents_4_all_selected(user_id, validated_data.get('document_ids'), validated_data)
            validated_data['document_ids'] = [doc['id'] for doc in documents]
        if serial.validated_data['action'] != 'delete':
            collection_document_add(validated_data)
        else:
            collection_document_delete(validated_data)

        return my_json_response({})


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class CollectionDocumentsSelected(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = CollectionDocumentSelectedQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        document_ids = collection_documents_select_list(request.user.id, serial.validated_data)
        return my_json_response(document_ids)


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
        return my_json_response(data, code=code)


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
        return my_json_response(data, code=code, msg=data.get('msg'))


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['POST']), name='dispatch')
class CollectionsCreateBotCheck(APIView):

    @staticmethod
    def post(request, *args, **kwargs):
        query = request.data
        serial = CollectionCreateBotCheckQuerySerializer(data=query)
        if not serial.is_valid():
            return my_json_response(serial.errors, code=100001, msg=f'validate error, {list(serial.errors.keys())}')
        vd = serial.validated_data
        code, msg = collections_create_bot_check(request.user.id, vd['ids'], vd['bot_id'])
        return my_json_response({}, code=code, msg=msg)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class PublishedBotTitles(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        check_keys(query, ['collection_ids'])
        if isinstance(query['collection_ids'], str):
            query['collection_ids'] = query['collection_ids'].split(',')
        is_in_published_bot, bot_titles = collections_published_bot_titles(query['collection_ids'])
        data = {
            'is_in_published_bot': is_in_published_bot,
            'bot_titles': bot_titles,
        }
        return my_json_response(data)


@method_decorator([extract_json], name='dispatch')
@method_decorator(require_http_methods(['GET']), name='dispatch')
class ReferenceBotTitles(APIView):
    @staticmethod
    def get(request, *args, **kwargs):
        query = request.query_params.dict()
        check_keys(query, ['collection_ids'])
        if isinstance(query['collection_ids'], str):
            query['collection_ids'] = query['collection_ids'].split(',')
        has_reference_bots, bot_titles = collections_reference_bot_titles(request.user.id, query['collection_ids'])
        data = {
            'has_reference_bots': has_reference_bots,
            'bot_titles': bot_titles,
        }
        return my_json_response(data)
