from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.urls import path

from . import views
from . import views_openapi

urlpatterns = [
    path('openapi/index', views.Index.as_view(), name='Index'),

    path('api-key', views.ApiKey.as_view(), name='ApiKey'),
    path('api-key/<int:openapi_id>', views.ApiKey.as_view(), name='ApiKey'),
    path('api-key/usage/extract', views.DocumentExtractUsage.as_view(), name='DocumentExtractUsage'),
    path('api-key/usage/chat', views.ConversationUsage.as_view(), name='ConversationUsage'),
]