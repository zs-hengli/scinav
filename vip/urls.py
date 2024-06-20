from django.urls import path

from . import views

urlpatterns = [
    path('vip/index', views.Index.as_view(), name='index'),

    path('pay', views.Pay.as_view(), name='notify'),
    path('pay/notify', views.WeixinNotify.as_view(), name='notify'),
    #
]
