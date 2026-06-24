# Django Backend Setup Without Docker
# For: running `michot_marefiya_backend` on a normal computer without containers
# Last updated: 2026-06-24

## 1. Overview

This guide explains how to run the backend directly on your computer without Docker.

It covers:
- installing the required software
- creating a Python virtual environment
- setting up PostgreSQL and Redis
- configuring `.env`
- running migrations
- creating a superuser
- seeding demo data
- starting Django, Celery worker, and Celery beat
- getting the backend ready for the frontend

This project is Docker-first, but it can also run fine without Docker if PostgreSQL, Redis, Python, and the required env values are configured correctly.

## 2. What You Need Installed

Install these first:
- Git
- Python `3.12+`
- PostgreSQL
- Redis

Recommended:
- Python `3.13`
- pgAdmin or another PostgreSQL client
- Postman or Insomnia
- a code editor like VS Code

## 3. Clone The Project

```bash
git clone <REPOSITORY_URL> michot_marefiya_backend
cd michot_marefiya_backend
```

If you already have the project as a zip, extract it and open the project folder in a terminal.

## 4. Create And Activate A Virtual Environment

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Then activate again:

```powershell
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 5. Install Python Dependencies

Install the backend dependencies:

```bash
pip install --upgrade pip
pip install -r requirements/dev.txt -r requirements/prod.txt
```

This installs:
- Django
- Django REST Framework
- PostgreSQL driver
- Celery
- Redis client
- Swagger/OpenAPI packages
- test and lint tooling

## 6. Set Up PostgreSQL

Install PostgreSQL and make sure the database server is running.

Create a database user and database for the project.

Example SQL:

```sql
CREATE USER marefiya_user WITH PASSWORD 'change-me';
CREATE DATABASE marefiya_db OWNER marefiya_user;
GRANT ALL PRIVILEGES ON DATABASE marefiya_db TO marefiya_user;
```

You can do this from:
- `psql`
- pgAdmin
- another PostgreSQL client

If you prefer different names, that is fine, but your `.env` must match them.

## 7. Set Up Redis

Install Redis and start the Redis server locally.

Typical default local Redis URL:

```text
redis://127.0.0.1:6379/1
```

Celery broker URL:

```text
redis://127.0.0.1:6379/0
```

Make sure Redis is running before you start Celery.

## 8. Create The `.env` File

Copy the example file:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

## 9. Update `.env` For A Non-Docker Local Setup

Open `.env` and update the Docker-style host values to your local machine values.

Use this as a good local starting point:

```env
SECRET_KEY=replace-with-a-long-random-secret-key
DEBUG=True
DJANGO_SETTINGS_MODULE=config.settings.dev

POSTGRES_USER=marefiya_user
POSTGRES_PASSWORD=change-me
POSTGRES_DB=marefiya_db
DB_HOST=127.0.0.1
DB_PORT=5432
DATABASE_URL=postgres://marefiya_user:change-me@127.0.0.1:5432/marefiya_db

REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

CHAPA_SECRET_KEY=change-me
CHAPA_WEBHOOK_SECRET=change-me
CHAPA_CALLBACK_URL=http://127.0.0.1:8000/api/v1/payment/callback/chapa/
FRONTEND_URL=http://localhost:5173/
CHAPA_BASE_URL=https://api.chapa.co/v1/
CHAPA_ENV=test

AFRO_MESSAGE_TOKEN=change-me
AFRO_MESSAGE_IDENTIFIER_ID=change-me
AFRO_MESSAGE_SENDER_NAME=Mechot Marefiya

EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=localhost
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Michot Marefiya <noreply@example.com>

REQUIRE_GUEST_BOOKING_OTP=True
BOOKING_FORWARD_WINDOW_DAYS=5

MAP_PROVIDER=geoapify
GEOAPIFY_API_KEY=change-me
GEOAPIFY_GEOCODING_URL=https://api.geoapify.com/v1/geocode/search
GEOAPIFY_REVERSE_GEOCODING_URL=https://api.geoapify.com/v1/geocode/reverse
GEOAPIFY_AUTOCOMPLETE_URL=https://api.geoapify.com/v1/geocode/autocomplete
GEOAPIFY_PLACE_DETAIL_URL=https://api.geoapify.com/v2/place-details
```

Important notes:
- `DB_HOST` must be `127.0.0.1` or `localhost`, not `db`
- `REDIS_URL` must point to your local Redis, not `redis`
- `DJANGO_SETTINGS_MODULE=config.settings.dev` is correct for local non-Docker work
- `FRONTEND_URL` should match the frontend dev server, usually `http://localhost:5173/`
- if you want real email sending, replace the console email backend with real SMTP values
- if you want maps autocomplete to work, add a valid `GEOAPIFY_API_KEY`

## 10. Run Database Migrations

Apply migrations:

```bash
python manage.py migrate
```

If you want to confirm migration status:

```bash
python manage.py showmigrations
```

## 11. Create A Superuser

Create an admin account so you can access Django admin:

```bash
python manage.py createsuperuser
```

Admin URL:

```text
http://127.0.0.1:8000/api/admin/
```

## 12. Seed Demo Data

To get a frontend-ready local dataset, run:

```bash
python manage.py seed_data --clear --seed 20260616 --days 45
```

What this does:
- clears previously seeded app data
- creates demo users and business records
- seeds listings, bookings, inventory, payments, and related data

Useful seed options:

```bash
python manage.py seed_data --help
```

Shared seed command options currently available:
- `--clear`
- `--seed`
- `--days`
- `--users`

## 13. Start The Backend API

Run Django:

```bash
python manage.py runserver
```

The backend will be available at:

```text
http://127.0.0.1:8000/
```

Useful URLs:
- API root: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/api/docs/`
- Redoc: `http://127.0.0.1:8000/api/schema/redoc/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Health check: `http://127.0.0.1:8000/healthz`
- Django admin: `http://127.0.0.1:8000/api/admin/`

## 14. Start Celery Worker

Open a second terminal, activate the virtual environment, then run:

```bash
celery -A config.celery worker -l info
```

Celery is important for background work such as notifications and async processing.

## 15. Start Celery Beat

Open a third terminal, activate the virtual environment, then run:

```bash
celery -A config.celery beat -l info
```

Celery beat is important for scheduled tasks and cleanup jobs.

## 16. Minimum Setup Needed For The Frontend

To get the backend ready for the frontend team or the local React app, make sure all of these are true:

1. PostgreSQL is running
2. Redis is running
3. `.env` points to local PostgreSQL and local Redis
4. migrations have been applied
5. seed data has been loaded
6. Django is running on port `8000`
7. `FRONTEND_URL` matches the frontend dev server
8. `GEOAPIFY_API_KEY` is present if the frontend will use address autocomplete
9. Celery worker is running
10. Celery beat is running

If you want the shortest frontend-ready path:

```bash
python manage.py migrate
python manage.py seed_data --clear --seed 20260616 --days 45
python manage.py runserver
```

And in separate terminals:

```bash
celery -A config.celery worker -l info
celery -A config.celery beat -l info
```

## 17. Seeded Login Credentials

The shared seed flow usually creates demo users like:
- `admin@demo.michot / DemoPass123!`
- `guest1@demo.michot / DemoPass123!`
- `company1@demo.michot / DemoPass123!`
- `frontdesk1@demo.michot / DemoPass123!`

If seed data changes later, rerun:

```bash
python manage.py seed_data --help
```

or inspect the seed command implementation in:

- `apps/listing/management/commands/seed_data.py`

## 18. Useful Daily Commands

Run tests:

```bash
pytest
```

Run one test area:

```bash
pytest apps/listing/tests
```

Run Django checks:

```bash
python manage.py check
```

Open Django shell:

```bash
python manage.py shell
```

Collect static files:

```bash
python manage.py collectstatic --noinput
```

## 19. Troubleshooting

### `ModuleNotFoundError` when running Django

Your virtual environment is probably not activated, or dependencies are not installed.

Fix:

```bash
pip install -r requirements/dev.txt -r requirements/prod.txt
```

### Database connection error

Check:
- PostgreSQL is running
- `DATABASE_URL` is correct
- database user and password are correct
- database exists

### Redis connection error

Check:
- Redis server is running
- `REDIS_URL` is correct
- `CELERY_BROKER_URL` is correct

### Maps autocomplete is not working

Check:
- `MAP_PROVIDER=geoapify`
- `GEOAPIFY_API_KEY` is valid
- backend is running
- frontend is calling backend maps endpoints, not Geoapify directly

### Frontend cannot call the backend

Check:
- backend is on `http://127.0.0.1:8000`
- frontend dev server URL matches `FRONTEND_URL`
- `CSRF_TRUSTED_ORIGINS` includes the frontend URL
- backend `/api/docs/` opens in the browser

### Admin opens but static files look broken

Run:

```bash
python manage.py collectstatic --noinput
```

### Want a fully fresh reset without Docker

1. Drop or recreate the PostgreSQL database
2. Recreate `.env` if needed
3. Run:

```bash
python manage.py migrate
python manage.py seed_data --clear --seed 20260616 --days 45
```

## 20. Quick Start Summary

If you only want the shortest non-Docker path:

```bash
git clone <REPOSITORY_URL> michot_marefiya_backend
cd michot_marefiya_backend
python -m venv .venv
pip install -r requirements/dev.txt -r requirements/prod.txt
cp .env.example .env
```

Then update `.env` for:
- local PostgreSQL
- local Redis
- your Geoapify key

Then run:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --clear --seed 20260616 --days 45
python manage.py runserver
```

And in separate terminals:

```bash
celery -A config.celery worker -l info
celery -A config.celery beat -l info
```
