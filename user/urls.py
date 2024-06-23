from django.urls import path

from . import views

urlpatterns = [
    path('users/sync', views.Users.as_view(), name='user'),
    path('user/auth/callback', views.Callback.as_view(), name='index'),
    path('user/auth/callback/<str:app_id>', views.Callback.as_view(), name='index'),
    path('user/apit/<str:app_id>', views.ApiT.as_view(), name='index'),

    #
]
