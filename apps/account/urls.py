from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.account import views

router = DefaultRouter()

router.register("users", views.UserViewSet, basename="users")
router.register("companies", views.CompanyProfileViewSet, basename="companies")
router.register("hotels", views.HotelProfileViewSet, basename="hotels")
router.register("individual-owners", views.IndividualOwnerProfileViewSet, basename="individual_owners")
router.register("staff", views.StaffViewSet, basename="staff")
router.register("roles", views.RoleViewSet, basename="roles")


urlpatterns = [
    path('password-reset/', views.PasswordResetView.as_view(), name='password_reset'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('verify-email-change/', views.VerifyEmailChangeView.as_view(), name='verify_email_change'),
    path('profile/agreement/', views.OwnerProfileAgreementView.as_view(), name='owner_profile_agreement'),
    path('', include(router.urls)),
]
