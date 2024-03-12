from django.urls import path

from . import views

urlpatterns = [
    path('chat', views.Index.as_view(), name='index'),
]

