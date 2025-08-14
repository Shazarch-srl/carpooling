from django.conf import settings
from django.db import models


class Ride(models.Model):
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rides")
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    departure_time = models.DateTimeField()
    seats = models.PositiveIntegerField()
    cost = models.DecimalField(max_digits=6, decimal_places=2)
    car_make = models.CharField(max_length=50, blank=True)
    car_model = models.CharField(max_length=50, blank=True)
    car_color = models.CharField(max_length=30, blank=True)
    plate = models.CharField(max_length=20, blank=True)
    pickup_notes = models.TextField(blank=True)
    dropoff_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.origin} to {self.destination} on {self.departure_time:%Y-%m-%d %H:%M}"


class Booking(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("confirmed", "Confirmed"),
    ]
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name="bookings")
    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    seats = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="requested")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rider} -> {self.ride} ({self.status})"
