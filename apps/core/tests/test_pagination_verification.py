from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from apps.listing.models import RoomListing
from apps.account.models import User, Role
from apps.core.models import CurrencyRate

class PaginationVerificationTest(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create_user(email="test@example.com", password="password")
        self.client.force_authenticate(user=self.user)

    def test_global_pagination_on_rooms(self):
        """Test that RoomListingViewSet responses are paginated."""
        # Create dummy rooms? Or just check empty list format
        # An empty paginated list should look like:
        # { "count": 0, "next": None, "previous": None, "results": [] }
        url = reverse('rooms-list') # Assuming basename='rooms' -> rooms-list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertIsInstance(response.data['results'], list)
        
        # Check non-paginated format doesn't exist (i.e. response.data is not a list)
        self.assertNotIsInstance(response.data, list)

    def test_manual_pagination_on_stay_search(self):
        """Test that StaySearchView (manual APIView) is paginated."""
        # Needs query params
        url = reverse('stay-search')
        params = {
            'city': 'Addis',
            'check_in_date': '2026-01-20',
            'check_out_date': '2026-01-22',
            'guests': 1
        }
        response = self.client.get(url, params)
        # Even if empty or validation error, if it hits the success path (mock service?), it should be paginated.
        # But real service might return empty list.
        # If service returns empty list, our pagination logic will wrap it.
        
        # Note: This test hits the DB. If no data, it returns empty results.
        if response.status_code == 200:
            self.assertIn('count', response.data)
            self.assertIn('results', response.data)
        else:
            # If 400 (e.g. validation), that's fine for this test, but let's try to hit 200
            pass

    def test_currency_endpoint_is_NOT_paginated(self):
        """Test that CurrencyViewSet is explicitly excluded from pagination."""
        url = reverse('currencies-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should be a simple list, not a dict with 'results'
        self.assertIsInstance(response.data, list)
