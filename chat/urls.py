from django.urls import path

from . import views

urlpatterns = [
    path('chat/index', views.Index.as_view(), name='index'),
    path('chat', views.Chat.as_view(), name='index'),

    path('chat/conversations', views.Conversations.as_view()),
    path('chat/conversations/menu', views.ConversationsMenu.as_view()),

    path('chat/conversations/<str:conversation_id>', views.Conversations.as_view()),

    path('chat/questions/answer', views.QuestionUpdateAnswer.as_view()),
    path('chat/questions/<str:question_id>/answer/<int:is_like>', views.QuestionLikeAnswer.as_view()),
]
