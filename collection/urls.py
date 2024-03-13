from django.urls import path

from . import views

urlpatterns = [
    path('collection/index', views.Index.as_view()),
    path('collections', views.Collections.as_view()),
    path('collections/<str:collection_id>', views.Collections.as_view()),
    path('collections/<str:collection_id>/documents', views.CollectionDocument.as_view()),
    path('collections/documents', views.CollectionDocument.as_view()),
]
