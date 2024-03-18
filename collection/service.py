import logging

from django.utils.translation import gettext_lazy as _

from bot.rag_service import Collection as RagCollection
from collection.models import Collection, CollectionDocument
from document.models import Document
from document.serializers import DocumentListSerializer

logger = logging.getLogger(__name__)


def collection_list(user_id, include_public=False):
    coll_list = []
    if include_public:
        public_collections = RagCollection.list()
        coll_list = [
            {'id': c['id'], 'name': c['name'], 'total': c['total'], 'type': Collection.TypeChoices.PUBLIC}
            for c in public_collections
        ]
        ids = [c['id'] for c in public_collections]
        if Collection.objects.filter(id__in=ids).count() != len(ids):
            _save_public_collection(Collection.objects.filter(id__in=ids).all(), public_collections)
    collections = Collection.objects.filter(user_id=user_id, del_flag=False).all()
    coll_list += [
        {'id': c.id, 'name': c.title, 'total': c.total_public + c.total_personal,
         'type': Collection.TypeChoices.PERSONAL
         } for c in collections
    ]
    return coll_list


def collection_detail(user_id, collection_id):
    pass


def _save_public_collection(saved_collections, public_collections):
    saved_collections_dict = {c["id"]: c for c in saved_collections}
    for pc in public_collections:
        if pc['id'] not in saved_collections_dict.keys() or pc['total'] != saved_collections_dict[pc['id']]['total']:
            coll_data = {
                'id': pc['id'],
                'title': pc['name'],
                'user_id': None,
                'type': Collection.TypeChoices.PUBLIC,
                'total': pc['total']
            }
            Collection.objects.update_or_create(coll_data, id=pc['id'])


def collection_docs(collection_id, page_size=10, page_num=1):
    query_set = CollectionDocument.objects.filter(collection_id=collection_id, del_flag=False).order_by('-updated_at')
    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)]
    docs = [cd.document for cd in c_docs]

    docs_data = DocumentListSerializer(docs, many=True).data
    for i, d_data in enumerate(docs_data):
        docs_data[i]['doc_apa'] = f"[{i + 1}] {d_data['doc_apa']}"

    if c_docs:
        collection = c_docs[0].collection
        return {
            'collection_id': collection_id,
            'collection_type': collection.type,
            'collection_title': collection.title,
            'list': docs_data,
            'total': total
        }
    return {}


def collections_docs(collection_ids, page_size=10, page_num=1):
    query_set = CollectionDocument.objects.filter(
        collection_id__in=collection_ids, del_flag=False).values('document_id') \
        .order_by('-updated_at').distinct().all()
    public_collections = Collection.objects.filter(id__in=collection_ids, type=Collection.TypeChoices.PUBLIC).all()
    res_data = []
    if public_collections:
        for p_c in public_collections:
            res_data.append({
                'id': None,
                'doc_apa': f"{_('公共库')}: {p_c.title}"
            })
    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)]
    docs = Document.objects.filter(id__in=[cd['document_id'] for cd in c_docs]).all()

    docs_data = DocumentListSerializer(docs, many=True).data
    for i, d in enumerate(docs_data):
        d['doc_apa'] = f"[{i + 1}] {d['doc_apa']}"
        res_data.append(d)
    return {
        'list': res_data,
        'total': total
    }
