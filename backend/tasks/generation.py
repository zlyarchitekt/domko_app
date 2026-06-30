from tasks.celery_app import celery_app


@celery_app.task
def generate_variants_task(project_id: str):
    return {"project_id": project_id, "status": "done"}
