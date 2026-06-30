from celery import Celery

from core.config import settings

celery_app = Celery("pzt", broker=settings.celery_broker_url)
