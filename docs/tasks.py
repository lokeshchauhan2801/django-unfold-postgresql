"""Celery tasks for document processing."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from docs.models import Document
from docs.services import process_document

logger = logging.getLogger(__name__)
_local_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="document-index",
)


@shared_task(name="apps.documents.process_document")
def process_document_task(
    document_id: str,
    company_id: str | None = None,
    user_id: str | None = None,
    backend: str = "celery",
):
    """Extract, embed, and index one persisted document."""
    try:
        document = Document.objects.get(pk=document_id)
    except ObjectDoesNotExist:
        logger.error("Cannot process missing document %s", document_id)
        raise

    try:
        process_document(document, backend=backend)
    except Exception:
        logger.exception("Document processing failed for %s", document_id)
        raise
    return {"status": Document.STATUS_READY, "document_id": document_id}


def dispatch_document_processing(document_id: str) -> tuple[str, str]:
    """Use the local background executor in development and Celery elsewhere."""
    if settings.DEBUG:
        task_id = str(uuid4())
        _local_executor.submit(
            process_document_task.run,
            document_id,
            backend="local-background",
        )
        return task_id, "local-background"

    task = process_document_task.apply_async(args=[document_id], retry=False)
    return task.id, "celery"
