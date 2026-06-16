# Django Backend Local Setup
# For: App developers and backend contributors
# Last updated: 2026-06-16

## 1. Overview

This guide explains how to run the backend locally from a fresh clone all the way to:
- installing dependencies
- starting the local services
- running database migrations
- seeding demo data
- accessing the API and docs

This project is Docker-first for local development.

Main local services:
- Django API
- PostgreSQL
- Redis
- Celery worker
- Celery beat
- pgAdmin

## 2. Prerequisites

Install these before starting:
- Git
- Docker Desktop
- Docker Compose

Recommended:
- a terminal with Docker available
- Postman or Insomnia for testing APIs

## 3. Clone The Project

Clone the repository and move into it:

```bash
git clone <REPOSITORY_URL> michot_marefiya_backend
cd michot_marefiya_backend
```

If the repository was shared as a zip, extract it and open the extracted project folder in your terminal.

## 4. Create The Environment File

Copy the example env file:

```bash
cp .env.example .env
```

If you are on Windows PowerShell and `cp` does not work, use:

```powershell
Copy-Item .env.example .env
```

Important notes:
- the project reads from `.env`
- the default local Docker setup expects the database host to stay as `db`
- the default local Docker setup expects Redis to stay on its default container URL

For most local setups, `.env.example` is enough to get started without changes.

## 5. Review Important Local Values

Before starting the stack, confirm these values in `.env`:

- `DATABASE_URL=postgres://...@db:5432/...`
- `DB_HOST=db`
- `DB_PORT=5432`
- `DJANGO_DEBUG=True`
- `ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,...`

If you are only running locally, keep:
- `CHAPA_ENV=test`

Do not switch payment keys to production values for local development.

## 6. Start The Local Stack

Build and start the containers:

```bash
docker compose up --build -d
```

This starts:
- `db`
- `redis`
- `api`
- `celery`
- `celery-beat`
- `pgadmin4`

To confirm everything is running:

```bash
docker compose ps
```

## 7. Run Database Migrations

Apply all migrations:

```bash
docker compose exec api python manage.py migrate
```

If this is the first time the project is being started locally, wait until the database container is healthy before running migrations.

## 8. Seed Demo Data

Seed the project with the shared demo dataset:

```bash
docker compose exec api python manage.py seed_data --clear --seed 20260616 --days 45
```

What this does:
- clears previously seeded app data safely
- recreates demo users, companies, owners, hotels, rooms, guest houses, event spaces, cars, properties, bookings, payments, notifications, favorites, and related records

Shared demo credentials created by the seed command:
- `admin@demo.michot / DemoPass123!`
- `guest1@demo.michot / DemoPass123!`
- `company1@demo.michot / DemoPass123!`
- `frontdesk1@demo.michot / DemoPass123!`

## 9. Access The Running Project

Once the containers are up, use these URLs:

- API root: `http://localhost:8000/`
- API docs: `http://localhost:8000/api/docs/`
- API schema: `http://localhost:8000/api/schema/`
- pgAdmin: `http://localhost:8001/`

If the backend is running correctly, the docs endpoint should load and seeded endpoints should return data.

## 10. Useful Daily Commands

Start services:

```bash
docker compose up -d
```

Stop services:

```bash
docker compose down
```

Stop services and remove volumes:

```bash
docker compose down -v
```

View API logs:

```bash
docker compose logs api
```

Follow API logs live:

```bash
docker compose logs -f api
```

Follow Celery logs:

```bash
docker compose logs -f celery
docker compose logs -f celery-beat
```

Open a Django shell:

```bash
docker compose exec api python manage.py shell
```

Create a superuser manually:

```bash
docker compose exec api python manage.py createsuperuser
```

Run tests:

```bash
docker compose exec api pytest
```

Run a focused test module:

```bash
docker compose exec api pytest apps/listing/tests
```

## 11. Recommended First-Time Verification

After migrations and seeding, verify these:

1. `http://localhost:8000/api/docs/` opens
2. login works with one seeded account
3. at least one listing endpoint returns seeded data
4. the seed command finished without error
5. `docker compose ps` shows all expected containers up

## 12. Common Troubleshooting

### Docker containers do not start

Run:

```bash
docker compose logs
```

Check for:
- port conflicts on `8000`, `8001`, or `6379`
- Docker Desktop not running
- image build failures

### Migration fails because a table is missing or a migration is unapplied

Run:

```bash
docker compose exec api python manage.py showmigrations
docker compose exec api python manage.py migrate
```

Then rerun the seed command.

### Seed command fails

Make sure migrations were applied first:

```bash
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_data --clear --seed 20260616 --days 45
```

### API container exits early

Check logs:

```bash
docker compose logs api
```

Common causes:
- invalid `.env`
- broken database connection
- missing dependency inside the container

### Port 8000 is already in use

Stop the process using it, or update the port mapping in `compose.yaml`.

### Want a fully fresh local reset

Use:

```bash
docker compose down -v
docker compose up --build -d
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_data --clear --seed 20260616 --days 45
```

This removes existing local database and Redis volumes and recreates the local environment from scratch.

## 13. Important Project Notes

- `manage.py` defaults to `config.settings.dev`
- the app is meant to be run locally through Docker for the smoothest setup
- the backend already exposes OpenAPI docs through `schema.yaml` generation and `/api/docs/`
- seeded data is intended for local and demo environments, not production

## 14. Minimal Local Workflow Summary

If you just need the shortest happy path:

```bash
git clone <REPOSITORY_URL> michot_marefiya_backend
cd michot_marefiya_backend
cp .env.example .env
docker compose up --build -d
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_data --clear --seed 20260616 --days 45
```

Then open:

```text
http://localhost:8000/api/docs/
```
