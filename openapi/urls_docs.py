from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.urls import path

from . import views
from . import views_openapi

urlpatterns = [
    # Optional UI:
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('openapi.yaml', SpectacularAPIView.as_view(), name='schema-yaml'),
    path('swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('docs', SpectacularRedocView.as_view(url_name='schema'), name='docs'),

]