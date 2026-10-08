"""Celery application factory."""
from celery import Celery


def create_celery_app(django_settings_module: str = 'config.settings.local') -> Celery:
    app = Celery('aiplatform')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    app.autodiscover_tasks()
    return app
