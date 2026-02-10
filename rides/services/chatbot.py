import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from openai import OpenAI

from rides.models import Ride

DEFAULT_MAX_RESULTS = 20
DEFAULT_SORT_BY = "departure_time"
DEFAULT_SORT_DIRECTION = "asc"

CLEARABLE_FIELDS = {
    "origin",
    "destination",
    "earliest_departure",
    "latest_departure",
    "min_seats",
    "max_cost",
    "driver_name",
    "include_past",
    "sort_by",
    "sort_direction",
    "max_results",
}

SYSTEM_PROMPT = (
    "You are a concise, helpful ride assistant for a carpooling service. "
    "Always call the search_rides tool to access actual trip listings. "
    "You will receive CURRENT_FILTERS and CURRENT_TIME_UTC in system context. "
    "If the user is refining a previous query, keep prior filters and update only what changed. "
    "If the user says 'start over', 'reset', or similar, set reset_filters=true. "
    "If the user says to remove a constraint (e.g., 'any price', 'no destination'), "
    "use clear_fields to remove the specific filter. "
    "If the user gives relative dates like 'today', 'tomorrow', or 'this weekend', "
    "translate them to ISO-8601 dates in UTC. If time is not specified, use a full-day range."
)

ANSWER_PROMPT = (
    "Provide a concise answer based only on the tool results. "
    "Mention the number of matches and highlight up to 3 best options "
    "with departure time, price, and seats. "
    "If key info is missing (origin, destination, or date), ask one clarifying question. "
    "If there are no rides, suggest a single, concrete alternative filter. "
    "Keep the response under 90 words."
)


@dataclass
class ChatResult:
    answer: str
    rides: list[Ride]
    match_count: int
    filters: dict


def _parse_iso_datetime(value: str | datetime | date | None, use_end_of_day: bool = False):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, timezone=timezone.utc)
    if isinstance(value, date):
        dt = timezone.datetime.combine(
            value,
            timezone.datetime.max.time() if use_end_of_day else timezone.datetime.min.time(),
        )
        return timezone.make_aware(dt, timezone=timezone.utc)
    value = value.strip()
    dt = parse_datetime(value)
    if dt:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=timezone.utc)
        return dt
    date_value = parse_date(value)
    if not date_value:
        return None
    if use_end_of_day:
        dt = timezone.datetime.combine(date_value, timezone.datetime.max.time())
    else:
        dt = timezone.datetime.combine(date_value, timezone.datetime.min.time())
    return timezone.make_aware(dt, timezone=timezone.utc)


def _coerce_int(value, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if minimum is not None and number < minimum:
        return minimum
    if maximum is not None and number > maximum:
        return maximum
    return number


def _coerce_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def sanitize_filters(filters: dict) -> dict:
    cleaned = {}
    for key in ("origin", "destination", "driver_name"):
        text = filters.get(key)
        if isinstance(text, str) and text.strip():
            cleaned[key] = text.strip()
    min_seats = _coerce_int(filters.get("min_seats"), minimum=1)
    if min_seats:
        cleaned["min_seats"] = min_seats
    max_cost = _coerce_decimal(filters.get("max_cost"))
    if max_cost is not None:
        cleaned["max_cost"] = max_cost
    earliest = _parse_iso_datetime(filters.get("earliest_departure"))
    if earliest:
        cleaned["earliest_departure"] = earliest
    latest = _parse_iso_datetime(filters.get("latest_departure"), use_end_of_day=True)
    if latest:
        cleaned["latest_departure"] = latest
    include_past = _coerce_bool(filters.get("include_past"))
    cleaned["include_past"] = include_past if include_past is not None else False
    sort_by = filters.get("sort_by")
    cleaned["sort_by"] = sort_by if sort_by in {"departure_time", "cost", "seats"} else DEFAULT_SORT_BY
    sort_direction = filters.get("sort_direction")
    cleaned["sort_direction"] = (
        sort_direction if sort_direction in {"asc", "desc"} else DEFAULT_SORT_DIRECTION
    )
    max_results = _coerce_int(filters.get("max_results"), minimum=1, maximum=DEFAULT_MAX_RESULTS)
    cleaned["max_results"] = max_results or DEFAULT_MAX_RESULTS
    return cleaned


def merge_filters(previous: dict | None, new_filters: dict) -> dict:
    merged = dict(previous or {})
    reset = _coerce_bool(new_filters.get("reset_filters")) is True
    clear_fields = new_filters.get("clear_fields") or []
    if reset:
        merged = {}
    for key, value in new_filters.items():
        if key in {"reset_filters", "clear_fields"}:
            continue
        if value is None:
            continue
        merged[key] = value
    if isinstance(clear_fields, list):
        for field in clear_fields:
            if field in CLEARABLE_FIELDS:
                merged.pop(field, None)
    sanitized = sanitize_filters(merged)
    if not sanitized.get("include_past"):
        now = timezone.now()
        earliest = sanitized.get("earliest_departure")
        if not earliest or earliest < now:
            sanitized["earliest_departure"] = now
    return sanitized


def filter_rides(filters: dict):
    qs = Ride.objects.select_related("driver").all().order_by("departure_time")
    origin = filters.get("origin")
    destination = filters.get("destination")
    driver_name = filters.get("driver_name")
    if origin:
        qs = qs.filter(origin__icontains=origin)
    if destination:
        qs = qs.filter(destination__icontains=destination)
    if driver_name:
        qs = qs.filter(
            Q(driver__first_name__icontains=driver_name)
            | Q(driver__last_name__icontains=driver_name)
        )
    min_seats = filters.get("min_seats")
    if min_seats:
        qs = qs.filter(seats__gte=min_seats)
    max_cost = filters.get("max_cost")
    if max_cost is not None:
        qs = qs.filter(cost__lte=max_cost)
    earliest = filters.get("earliest_departure")
    if earliest:
        qs = qs.filter(departure_time__gte=earliest)
    latest = filters.get("latest_departure")
    if latest:
        qs = qs.filter(departure_time__lte=latest)
    include_past = filters.get("include_past")
    now = timezone.now()
    if not include_past:
        if earliest:
            if earliest < now:
                qs = qs.filter(departure_time__gte=now)
        else:
            qs = qs.filter(departure_time__gte=now)
    sort_by = filters.get("sort_by", DEFAULT_SORT_BY)
    sort_direction = filters.get("sort_direction", DEFAULT_SORT_DIRECTION)
    if sort_by in {"departure_time", "cost", "seats"}:
        order = sort_by if sort_direction != "desc" else f"-{sort_by}"
        qs = qs.order_by(order)
    match_count = qs.count()
    qs = qs[: filters.get("max_results", DEFAULT_MAX_RESULTS)]
    return qs, match_count


def _serialize_rides(rides):
    serialized = []
    for ride in rides:
        driver_name = ride.driver.get_full_name() or ride.driver.username
        serialized.append(
            {
                "id": ride.id,
                "origin": ride.origin,
                "destination": ride.destination,
                "departure_time": ride.departure_time.isoformat(),
                "seats": ride.seats,
                "cost": str(ride.cost),
                "driver_name": driver_name,
                "car_make": ride.car_make,
                "car_model": ride.car_model,
                "car_color": ride.car_color,
            }
        )
    return serialized


def _build_tool_schema():
    return [
        {
            "type": "function",
            "name": "search_rides",
            "description": "Search ride listings for matches based on user preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": ["string", "null"],
                        "description": "Origin city or area.",
                    },
                    "destination": {
                        "type": ["string", "null"],
                        "description": "Destination city or area.",
                    },
                    "earliest_departure": {
                        "type": ["string", "null"],
                        "description": "ISO-8601 date or datetime in UTC.",
                    },
                    "latest_departure": {
                        "type": ["string", "null"],
                        "description": "ISO-8601 date or datetime in UTC.",
                    },
                    "min_seats": {
                        "type": ["integer", "null"],
                        "description": "Minimum seats needed.",
                    },
                    "max_cost": {"type": ["number", "null"], "description": "Maximum price in EUR."},
                    "driver_name": {
                        "type": ["string", "null"],
                        "description": "Driver name to match.",
                    },
                    "max_results": {
                        "type": ["integer", "null"],
                        "description": "Maximum rides to return (1-20).",
                    },
                    "include_past": {
                        "type": ["boolean", "null"],
                        "description": "Whether to include past rides.",
                    },
                    "sort_by": {
                        "type": ["string", "null"],
                        "description": "Sort field for the results (departure_time, cost, seats).",
                    },
                    "sort_direction": {
                        "type": ["string", "null"],
                        "description": "Sort direction for the results (asc, desc).",
                    },
                    "reset_filters": {
                        "type": ["boolean", "null"],
                        "description": "Reset previous filters when true.",
                    },
                    "clear_fields": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "string",
                            "enum": sorted(CLEARABLE_FIELDS),
                        },
                        "description": "Filters to remove from the previous search.",
                    },
                },
                "required": [
                    "origin",
                    "destination",
                    "earliest_departure",
                    "latest_departure",
                    "min_seats",
                    "max_cost",
                    "driver_name",
                    "max_results",
                    "include_past",
                    "sort_by",
                    "sort_direction",
                    "reset_filters",
                    "clear_fields",
                ],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]


def run_chat(user_message: str, history: list[dict], current_filters: dict | None = None) -> ChatResult:
    client = OpenAI()
    tools = _build_tool_schema()

    input_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    input_messages.append(
        {
            "role": "system",
            "content": f"CURRENT_TIME_UTC: {timezone.now().isoformat()}",
        }
    )
    if current_filters:
        sanitized_current = sanitize_filters(current_filters)
        serialized_current = {
            key: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value)
                if hasattr(value, "as_tuple")
                else value
            )
            for key, value in sanitized_current.items()
        }
        input_messages.append(
            {
                "role": "system",
                "content": f"CURRENT_FILTERS: {json.dumps(serialized_current)}",
            }
        )
    input_messages.extend(history)
    input_messages.append({"role": "user", "content": user_message})

    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=input_messages,
        tools=tools,
        tool_choice="required",
        temperature=0.2,
    )

    tool_call = next((item for item in response.output if item.type == "function_call"), None)
    filters = {}
    if tool_call and getattr(tool_call, "arguments", None):
        try:
            filters = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            filters = {}

    merged_filters = merge_filters(current_filters or {}, filters)
    rides, match_count = filter_rides(merged_filters)

    tool_output = {
        "filters": {
            key: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value)
                if hasattr(value, "as_tuple")
                else value
            )
            for key, value in merged_filters.items()
        },
        "match_count": match_count,
        "rides": _serialize_rides(rides),
    }

    followup_input = list(input_messages)
    if tool_call:
        followup_input.append(tool_call)
        followup_input.append(
            {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(tool_output),
            }
        )

    final_response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=followup_input,
        instructions=ANSWER_PROMPT,
        temperature=0.2,
    )

    return ChatResult(
        answer=final_response.output_text.strip(),
        rides=list(rides),
        match_count=match_count,
        filters=merged_filters,
    )
