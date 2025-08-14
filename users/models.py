from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone = models.CharField(max_length=20, blank=True)
    home_area = models.CharField(max_length=255, blank=True)
    commute_start = models.TimeField(null=True, blank=True)
    commute_end = models.TimeField(null=True, blank=True)
    profile_photo = models.ImageField(upload_to="profiles/", blank=True)

    def __str__(self):
        return self.username or self.email
