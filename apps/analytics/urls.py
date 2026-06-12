from django.urls import path

from .views import (
    AdminOverviewMetricsView,
    AdminPayoutFailureMetricsView,
    AdminRevenueMetricsView,
    CompanyActivityView,
    CompanyOverviewView,
    CompanyRevenueView,
    FrontDeskAvailabilityView,
    FrontDeskStatsView,
)

urlpatterns = [
    path("company/overview/", CompanyOverviewView.as_view(), name="company-overview"),
    path("company/revenue/", CompanyRevenueView.as_view(), name="company-revenue"),
    path("company/activity/", CompanyActivityView.as_view(), name="company-activity"),
    path("frontdesk/stats/", FrontDeskStatsView.as_view(), name="frontdesk-stats"),
    path("frontdesk/availability/", FrontDeskAvailabilityView.as_view(), name="frontdesk-availability"),
    path("admin/overview/", AdminOverviewMetricsView.as_view(), name="admin-overview"),
    path("admin/revenue/", AdminRevenueMetricsView.as_view(), name="admin-revenue"),
    path("admin/payout-failures/", AdminPayoutFailureMetricsView.as_view(), name="admin-payout-failures"),
]
