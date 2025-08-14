from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView

from .forms import RideForm, BookingForm
from .models import Ride, Booking


class RideListView(ListView):
    model = Ride
    template_name = "rides/ride_list.html"
    context_object_name = "rides"
    paginate_by = 20

    def get_queryset(self):
        qs = Ride.objects.all().order_by("departure_time")
        origin = self.request.GET.get("origin")
        destination = self.request.GET.get("destination")
        if origin:
            qs = qs.filter(origin__icontains=origin)
        if destination:
            qs = qs.filter(destination__icontains=destination)
        return qs


class RideCreateView(LoginRequiredMixin, CreateView):
    model = Ride
    form_class = RideForm
    template_name = "rides/ride_form.html"
    success_url = reverse_lazy("ride_list")

    def form_valid(self, form):
        form.instance.driver = self.request.user
        return super().form_valid(form)


class RideDetailView(DetailView):
    model = Ride
    template_name = "rides/ride_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["booking_form"] = BookingForm()
        return context


@login_required
def book_ride(request, pk):
    ride = get_object_or_404(Ride, pk=pk)
    if request.method == "POST":
        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.ride = ride
            booking.rider = request.user
            booking.save()
    return redirect("ride_detail", pk=pk)


@login_required
def update_booking(request, pk, status):
    booking = get_object_or_404(Booking, pk=pk, ride__driver=request.user)
    if status in dict(Booking.STATUS_CHOICES):
        booking.status = status
        booking.save()
    return redirect("ride_detail", pk=booking.ride.pk)
