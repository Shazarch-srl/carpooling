# Carpooling

A simple carpooling web application built with Django and Bootstrap.

## Features

- Email-based authentication powered by [django-allauth](https://github.com/pennersr/django-allauth)
- Drivers can post rides with origin, destination, departure time and car details
- Riders can search rides and request bookings
- Drivers manage booking requests (accept/decline)

## Development

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Docker (development)

Alternatively, run the project in Docker with the development settings:

```bash
docker compose up --build
```
