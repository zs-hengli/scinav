from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.urls import path

from . import views
from . import views_openapi

urlpatterns = [
    # Optional UI:
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('openapi.yaml', SpectacularAPIView.as_view(), name='schema-yaml'),
    path('swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # openapi
    path('index', views_openapi.Index.as_view(), name='Index'),
    path('search', views_openapi.Search.as_view(), name='Search', ),
    path('chat', views_openapi.Chat.as_view(), name='Chat'),
    path('upload/papers/<str:filename>', views_openapi.UploadPaper.as_view(), name='UploadPaper'),
    path('topic/paza', views_openapi.TopicPlaza.as_view(), name='TopicPlaza'),
    path('my/topics', views_openapi.MyTopics.as_view(), name='MyTopics'),
    path('personal/library', views_openapi.PersonalLibrary.as_view(), name='PersonalLibrary'),
]