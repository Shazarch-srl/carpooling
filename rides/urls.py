from django.urls import path

from .views import (
    RideCreateView,
    RideDetailView,
    RideListView,
    book_ride,
    ride_chat,
    update_booking,
)

urlpatterns = [
    path("", RideListView.as_view(), name="ride_list"),
    path("chat/", ride_chat, name="ride_chat"),
    path("create/", RideCreateView.as_view(), name="ride_create"),
    path("<int:pk>/", RideDetailView.as_view(), name="ride_detail"),
    path("<int:pk>/book/", book_ride, name="book_ride"),
    path("booking/<int:pk>/<str:status>/", update_booking, name="update_booking"),
]
