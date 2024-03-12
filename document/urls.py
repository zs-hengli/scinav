from django.urls import path

from . import views

urlpatterns = [
    path('documents', views.Index.as_view()),
    path('documents/presigned-url', views.GenPresignedUrl.as_view()),
    path('search', views.Search.as_view()),
]
