from django.contrib import admin

from .models import Ride, Booking


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ("driver", "origin", "destination", "departure_time", "seats")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("ride", "rider", "seats", "status")
