from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView

from .forms import RideForm, BookingForm
from .models import Ride, Booking
from .services.chatbot import filter_rides, run_chat, sanitize_filters

CHAT_HISTORY_KEY = "ride_chat_history"
CHAT_FILTERS_KEY = "ride_chat_filters"
CHAT_HISTORY_LIMIT = 8


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["now"] = timezone.now()
        return context


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


def _serialize_filters(filters: dict) -> dict:
    serialized = {}
    for key, value in filters.items():
        if hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        elif hasattr(value, "as_tuple"):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def _filters_to_labels(filters: dict) -> list[str]:
    labels = []
    origin = filters.get("origin")
    destination = filters.get("destination")
    if origin:
        labels.append(f"From {origin}")
    if destination:
        labels.append(f"To {destination}")
    if origin and destination:
        labels = [f"{origin} → {destination}"]
    min_seats = filters.get("min_seats")
    if min_seats:
        labels.append(f"{min_seats}+ seats")
    max_cost = filters.get("max_cost")
    if max_cost is not None:
        labels.append(f"Up to €{max_cost}")
    earliest = filters.get("earliest_departure")
    latest = filters.get("latest_departure")
    if earliest and latest:
        labels.append("Date range set")
    elif earliest:
        labels.append("After selected time")
    elif latest:
        labels.append("Before selected time")
    driver_name = filters.get("driver_name")
    if driver_name:
        labels.append(f"Driver: {driver_name}")
    include_past = filters.get("include_past")
    if include_past is True:
        labels.append("Including past rides")
    elif include_past is False:
        labels.append("Upcoming only")
    sort_by = filters.get("sort_by")
    sort_direction = filters.get("sort_direction")
    if sort_by:
        direction_label = "desc" if sort_direction == "desc" else "asc"
        labels.append(f"Sorted by {sort_by} ({direction_label})")
    return labels


def ride_chat(request):
    history = request.session.get(CHAT_HISTORY_KEY, [])
    stored_filters = request.session.get(CHAT_FILTERS_KEY, {})
    sanitized_filters = sanitize_filters(stored_filters)
    rides, match_count = filter_rides(sanitized_filters)
    assistant_reply = None

    chat_enabled = bool(getattr(settings, "OPENAI_API_KEY", ""))

    if request.method == "POST":
        if "clear" in request.POST:
            request.session.pop(CHAT_HISTORY_KEY, None)
            request.session.pop(CHAT_FILTERS_KEY, None)
            return redirect("ride_chat")

        user_message = request.POST.get("message", "").strip()
        if not chat_enabled:
            messages.warning(request, "OpenAI API key not configured.")
        elif not user_message:
            messages.info(request, "Enter a message to search rides.")
        else:
            try:
                result = run_chat(user_message, history, sanitized_filters)
                assistant_reply = result.answer
                sanitized_filters = result.filters
                rides = result.rides
                match_count = result.match_count
                history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_reply},
                ]
                history = history[-CHAT_HISTORY_LIMIT * 2 :]
                request.session[CHAT_HISTORY_KEY] = history
                request.session[CHAT_FILTERS_KEY] = _serialize_filters(sanitized_filters)
            except Exception as exc:
                messages.error(request, f"Chatbot error: {exc}")

    showing_count = len(rides)
    filter_labels = _filters_to_labels(sanitized_filters)

    context = {
        "chat_history": history,
        "rides": rides,
        "match_count": match_count,
        "showing_count": showing_count,
        "filter_labels": filter_labels,
        "chat_enabled": chat_enabled,
        "now": timezone.now(),
    }
    return render(request, "rides/chat.html", context)
