import os
from celery import Celery
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('michot_marefia_backend')

# Load task settings from django settings file (CELERY_BROKER_URL, etc.)
app.config_from_object('django.conf:settings', namespace='CELERY')

# discover tasks from  INSTALLED_APPS.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# test task for verification
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')