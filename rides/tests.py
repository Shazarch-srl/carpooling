from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Ride


class RideTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="driver", password="pass")
        self.ride = Ride.objects.create(
            driver=self.user,
            origin="A",
            destination="B",
            departure_time=timezone.now(),
            seats=3,
            cost=10,
        )

    def test_ride_list_view(self):
        response = self.client.get(reverse("ride_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A")
