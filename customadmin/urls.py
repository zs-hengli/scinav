from django.urls import path

from . import views

urlpatterns = [
    path('index', views.Index.as_view(), name='index'),

    path('config', views.GlobalConfigs.as_view(), name='index'),
    path('superuser/<str:user_id>', views.SuperUser.as_view(), name='superuser'),
    path('superuser/<str:user_id>/<int:is_superuser>', views.SuperUser.as_view(), name='superuser'),

    path('members', views.Members.as_view(), name='members'),
    path('members/award', views.MembersAward.as_view(), name='members_award'),
    path('members/trades', views.MembersTrades.as_view(), name='members_trades'),
    #
]

