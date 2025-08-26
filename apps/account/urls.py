from django.urls import path

from apps.account.views import SignupAPIView, UserAPIView, UserDetailAPIView


urlpatterns = [
    path("users/", UserAPIView.as_view(), name="users"),
    path("signup/", SignupAPIView.as_view(), name="signup"),
    path("users/<uuid:pk>/", UserDetailAPIView.as_view(), name="user_detail"),
]
