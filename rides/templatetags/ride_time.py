import re

from django import template
from django.utils import timezone
from django.utils.timesince import timeuntil

register = template.Library()


@register.filter
def timeuntil_compact(value, now=None):
    if not value:
        return ""
    if now is None:
        now = timezone.now()
    text = timeuntil(value, now)
    text = text.replace("\u00a0", " ")
    replacements = (
        ("days", "d"),
        ("day", "d"),
        ("hours", "h"),
        ("hour", "h"),
        ("minutes", "m"),
        ("minute", "m"),
        ("seconds", "s"),
        ("second", "s"),
    )
    for word, repl in replacements:
        text = re.sub(rf"\b{word}\b", repl, text)
    text = text.replace(",", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text
