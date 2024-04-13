from document.models import Document
from document.serializers import DocumentRagGetSerializer


def document_update_from_rag_ret(rag_ret):
    serial = DocumentRagGetSerializer(data=rag_ret)
    if not serial.is_valid():
        raise Exception(serial.errors)
    document, _ = Document.objects.update_or_create(
        serial.validated_data,
        doc_id=serial.validated_data['doc_id'],
        collection_type=serial.validated_data['collection_type'],
        collection_id=serial.validated_data['collection_id']
    )
    return document