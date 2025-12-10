from django.test import TestCase
from django.urls import reverse


class AnalyticsUnauthenticatedTests(TestCase):
    def test_overview_requires_auth(self):
        url = reverse("company-overview")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 401)

    def test_revenue_requires_auth(self):
        url = reverse("company-revenue")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 401)
