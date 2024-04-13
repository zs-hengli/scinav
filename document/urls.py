from django.urls import path

from . import views

urlpatterns = [
    path('documents/index', views.Index.as_view()),
    path('documents', views.Documents.as_view()),
    path('documents/personal', views.DocumentsPersonal.as_view()),
    path('documents/presigned-url', views.GenPresignedUrl.as_view()),
    # List Documents Library
    path('documents/library', views.DocumentsLibrary.as_view()),
    path('documents/library/operation/check', views.DocumentsLibraryOperationCheck.as_view()),
    path('documents/library/<str:document_library_id>', views.DocumentsLibrary.as_view()),

    path('documents/<str:document_id>', views.Documents.as_view()),
    path('documents/<str:document_id>/url', views.DocumentsUrl.as_view()),

    path('documents/rag/update', views.DocumentsRagUpdate.as_view()),
    path('documents/rag/update/<int:begin_id>/<int:end_id>', views.DocumentsRagUpdate.as_view()),


    path('search', views.Search.as_view()),
]
