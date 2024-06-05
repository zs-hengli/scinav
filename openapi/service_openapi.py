import logging

from django.db.models import Q
from bot.rag_service import Document as Rag_Document
from collection.models import Collection
from document.serializers import DocumentRagCreateSerializer
from document.service import get_documents_by_rag, get_reference_formats
from document.tasks import async_update_document
from openapi.serializers_openapi import CollectionListSerializer

logger = logging.getLogger(__name__)


def search(user_id, content, topn=100):
    rag_ret = Rag_Document.search(user_id, content, limit=topn)
    rag_ret = DocumentRagCreateSerializer(rag_ret, many=True).data
    ret_data = []
    documents_dict = get_documents_by_rag(rag_ret)
    document_ids = [d.id for d in documents_dict.values()]
    for doc in rag_ret:
        data = DocumentRagCreateSerializer(doc).data
        data['id'] = str(documents_dict[f"{doc['collection_id']}-{doc['doc_id']}"].id)
        venue = (
            data['journal'] if data['journal'] else
            data['conference'] if data['conference'] else
            data['venue'] if data['venue'] else ''
        )
        ret_data.append({
            'id': data['id'],
            'title': data['title'],
            'abstract': data['abstract'],
            'authors': data['authors'],
            'pub_date': data['pub_date'],
            'citation_count': data['citation_count'],
            'venue': venue,
            'doi': data['doi'],
            'categories': data['categories'],
            'source': {
                'collection_type': data['collection_type'],
                'collection_id': str(data['collection_id']),
                'doc_id': data['doc_id'],
            },
            'reference_formats': get_reference_formats(data),
        })
    async_update_document.apply_async(args=[document_ids])
    return ret_data


def collection_list_mine(user_id, page_size=10, page_num=1, keyword=None):
    filter_query = Q(user_id=user_id, del_flag=False)
    if keyword:
        filter_query &= Q(title__icontains=keyword)
    collections = Collection.objects.filter(filter_query).order_by('-updated_at')
    query_set = collections[page_size*(page_num-1):page_size*page_num]
    return CollectionListSerializer(query_set, many=True).data
