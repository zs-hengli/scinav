from django.urls import path

from . import views

urlpatterns = [
    path('collection/index', views.Index.as_view()),
    path('collections', views.Collection.as_view()),
    path('collections/<str:collection_id>/documents', views.CollectionDocument.as_view()),
    path('collections/documents', views.CollectionDocument.as_view()),
]
