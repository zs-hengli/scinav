from django.urls import path

from . import views

urlpatterns = [
    path('bot/index', views.Index.as_view()),

    path('bots/hot', views.HotBots.as_view()),
    path('bots/<str:bot_id>/hot', views.HotBots.as_view()),
    path('bots/<str:bot_id>/hot/order/<int:order>', views.HotBots.as_view()),

    path('bots', views.Bots.as_view()),
    path('bots/tools', views.BotsTools.as_view()),
    path('bots/plaza', views.BotsPlaza.as_view()),
    path('bots/advance/share', views.BotsAdvanceShare.as_view()),
    path('bots/<str:bot_id>', views.Bots.as_view()),

    path('bots/<str:bot_id>/subscribe/<str:action>', views.BotSubscribe.as_view()),
    path('bots/<str:bot_id>/documents', views.BotDocuments.as_view()),

    path('bots/<str:bot_id>/publish', views.BotPublish.as_view()),
    path('bots/<str:bot_id>/unpublish', views.BotUnPublish.as_view()),
    path('bots/<str:bot_id>/publish/order/<int:order>', views.BotPublish.as_view()),
]
