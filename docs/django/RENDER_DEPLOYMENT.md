# Render Deployment

This project can run on Render without Docker by using the production Django settings module and the standard process scripts already in the repository.

## Required Environment Variables

Set these in Render before the first deploy:

- `SECRET_KEY`
- `DEBUG=False`
- `DJANGO_SETTINGS_MODULE=config.settings.prod`
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CHAPA_SECRET_KEY`
- `CHAPA_WEBHOOK_SECRET`
- `CHAPA_CALLBACK_URL`
- `FRONTEND_URL`
- `MAP_PROVIDER=geoapify`
- `GEOAPIFY_API_KEY`
- `AFRO_MESSAGE_TOKEN`
- `AFRO_MESSAGE_IDENTIFIER_ID`
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

Use `.env.example` as the template source for the remaining optional values.

## Suggested Render Commands

- Build command: `python -m pip install --upgrade pip && python -m pip install -r requirements/prod.txt`
- Pre-deploy command: `python manage.py migrate --noinput && python manage.py collectstatic --noinput`
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

## Post-Deploy Commands

Run these from the Render shell or a one-off job when needed:

- Seed data: `python manage.py seed_data`
- Create superuser: `python manage.py createsuperuser`

## Health Check

Use:

- `/healthz`

## Important Notes

- Production services must use `config.settings.prod`.
- Celery worker and beat should use the same environment as the web service.
- Do not commit real secrets into `.env.example` or documentation.
