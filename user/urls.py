from django.urls import path

from . import views

urlpatterns = [
    path('user', views.Index.as_view(), name='index'),
    path('user/callback', views.Callback.as_view(), name='index'),
    path('user/callback/<str:app_id>', views.Callback.as_view(), name='index'),
    path('user/apit/<str:app_id>', views.ApiT.as_view(), name='index'),

    #
]
