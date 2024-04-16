from django.urls import path

from . import views

urlpatterns = [
    path('collection/index', views.Index.as_view()),

    # must before 'collections/<str:collection_id>...'
    path('collections/documents', views.CollectionDocuments.as_view()),
    path('collections/documents/<str:list_type>', views.CollectionDocuments.as_view()),

    path('collections/chat/operation/check', views.CollectionChatOperationCheck.as_view()),
    path('collections/delete/operation/check', views.CollectionDeleteOperationCheck.as_view()),
    path('collections/create/bot/check', views.CollectionsCreateBotCheck.as_view()),

    path('collections/published/bot/titles', views.PublishedBotTitles.as_view()),

    path('collections/<str:collection_id>/documents', views.CollectionDocuments.as_view()),
    path('collections/<str:collection_id>/documents/<str:list_type>', views.CollectionDocuments.as_view()),

    path('collections', views.Collections.as_view()),
    path('collections/list/<str:list_type>', views.Collections.as_view()),
    path('collections/<str:collection_id>', views.Collections.as_view()),
    path('collections/<str:collection_id>/name', views.Collections.as_view()),

]
