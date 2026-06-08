from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, NotificationPreferenceView, NotificationTemplateViewSet

router = DefaultRouter()
router.register(r'templates', NotificationTemplateViewSet, basename='notification-template')
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('', include(router.urls)),
]
