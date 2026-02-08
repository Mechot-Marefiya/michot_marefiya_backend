"""
URL configuration for marefiya project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.account.views import CustomTokenObtainPairView, LogoutView, MeView, CustomTokenRefreshView

urlpatterns = [
    path("api/admin/", admin.site.urls),
    path("api/v1/account/", include("apps.account.urls")),
    path("api/v1/core/", include("apps.core.urls")),
    path("api/v1/listing/", include("apps.listing.urls")),
    path("api/v1/favorites/", include("apps.favorites.urls")),
    path(
        "api/v1/auth/token/",
        CustomTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/v1/auth/token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"
    ),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="token_blacklist"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth_me"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    
    path("api/v1/payment/", include("apps.payment.urls")),
    path("api/v1/analytics/", include("apps.analytics.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
