from django.urls import path
from .views import CompanyOverviewView, CompanyRevenueView, CompanyActivityView

urlpatterns = [
    path("company/overview/", CompanyOverviewView.as_view(), name="company-overview"),
    path("company/revenue/", CompanyRevenueView.as_view(), name="company-revenue"),
    path("company/activity/", CompanyActivityView.as_view(), name="company-activity"),
]
