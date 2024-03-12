from django.urls import path

from . import views

urlpatterns = [
    path('bot/index', views.Index.as_view()),

    path('bots/hot', views.HotBot.as_view()),
    path('bots', views.Bot.as_view()),
    path('bots/<str:bot_id>', views.Bot.as_view()),

    path('bots/<str:bot_id>/subscribe/<str:action>', views.BotSubscribe.as_view()),
    path('bots/<str:bot_id>/documents', views.BotDocuments.as_view()),


    path('bots/rag/search', views.RagSearch.as_view())
]
