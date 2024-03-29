from django.urls import path

from . import views

urlpatterns = [
    path('documents/index', views.Index.as_view()),
    path('documents', views.Documents.as_view()),
    path('documents/presigned-url', views.GenPresignedUrl.as_view()),
    path('documents/<str:document_id>', views.Documents.as_view()),
    path('documents/<str:document_id>/url', views.DocumentsUrl.as_view()),

    path('documents/rag/update/<int:begin_id>/<int:end_id>', views.DocumentsRagUpdate.as_view()),


    path('search', views.Search.as_view()),
]
