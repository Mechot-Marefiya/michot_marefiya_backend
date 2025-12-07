from django.urls import path
from .views import CompanyOverviewView, CompanyRevenueView

urlpatterns = [
    path("company/overview/", CompanyOverviewView.as_view(), name="company-overview"),
    path("company/revenue/", CompanyRevenueView.as_view(), name="company-revenue"),
]
