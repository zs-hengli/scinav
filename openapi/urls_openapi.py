from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.urls import path

from . import views
from . import views_openapi

urlpatterns = [
    # openapi
    path('index', views_openapi.Index.as_view(), name='Index'),
    path('papers/search', views_openapi.Search.as_view(), name='Search', ),
    path('papers/pdf/<str:filename>', views_openapi.UploadPaper.as_view(), name='UploadPaper'),
    path('topics/paza', views_openapi.TopicPlaza.as_view(), name='TopicPlaza'),
    path('topics/my', views_openapi.MyTopics.as_view(), name='MyTopics'),
    path('personal/library', views_openapi.PersonalLibrary.as_view(), name='PersonalLibrary'),
    path('chat', views_openapi.Chat.as_view(), name='Chat'),

    # Optional UI:
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('openapi.yaml', SpectacularAPIView.as_view(), name='schema-yaml'),
    path('swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

]