
import os
import ssl
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rnchealth.settings')

app = Celery('rnchealth')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# so the worker doesn't crash when passing notification events back to Daphne
app.conf.broker_use_ssl = {
    'ssl_cert_reqs': ssl.CERT_NONE
}
app.conf.redis_backend_use_ssl = {
    'ssl_cert_reqs': ssl.CERT_NONE
}
    

from celery.signals import task_postrun
from django.db import connections

@task_postrun.connect
def close_db_connections(**kwargs):
    for conn in connections.all():
        conn.close()