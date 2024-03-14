from django.urls import path

from . import views

urlpatterns = [
    path('collection/index', views.Index.as_view()),

    # must before 'collections/<str:collection_id>...'
    path('collections/documents', views.CollectionDocuments.as_view()),
    path('collections/<str:collection_id>/documents', views.CollectionDocuments.as_view()),

    path('collections', views.Collections.as_view()),
    path('collections/<str:collection_id>', views.Collections.as_view()),
    path('collections/<str:collection_id>/name', views.Collections.as_view()),

]
