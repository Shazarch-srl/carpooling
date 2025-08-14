from django import forms

from .models import Ride, Booking


class RideForm(forms.ModelForm):
    class Meta:
        model = Ride
        fields = [
            "origin",
            "destination",
            "departure_time",
            "seats",
            "cost",
            "car_make",
            "car_model",
            "car_color",
            "plate",
            "pickup_notes",
            "dropoff_notes",
        ]
        widgets = {
            "departure_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["seats"]
