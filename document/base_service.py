from document.models import Document
from document.serializers import DocumentRagCreateSerializer


def document_update_from_rag_ret(rag_ret):
    serial = DocumentRagCreateSerializer(data=rag_ret)
    if not serial.is_valid():
        raise Exception(serial.errors)
    vd = serial.validated_data
    document, _ = Document.objects.update_or_create(
        vd,
        doc_id=vd['doc_id'],
        collection_type=vd['collection_type'],
        collection_id=vd['collection_id']
    )
    return document