from celery import Celery

celery_app = Celery(
    "outbound_campaigns",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/1",
    include=["server.scheduling.scheduler"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
