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


def dispatch_document_processing(
    document_id: str, backend: str | None = None
) -> tuple[str, str]:
    """Dispatch chunk+embed processing for a document.

    ``backend`` selects the strategy (``celery``/``kafka``/``temporal``). When
    omitted, the configured ``DOCUMENT_PROCESSING_BACKEND`` is used.

    For the Celery/default path in local development (``DEBUG``) we run the work
    inline on a managed background executor so Redis and a Celery worker are not
    required. Kafka and Temporal always dispatch through the
    ``ProcessingDispatcher`` strategy so the selected backend handles the job.
    """
    requested = (backend or getattr(settings, "DOCUMENT_PROCESSING_BACKEND", "celery")).lower()

    if requested in {"celery", "local-background"} and settings.DEBUG:
        task_id = str(uuid4())
        _local_executor.submit(
            process_document_task.run,
            document_id,
            backend="local-background",
        )
        return task_id, "local-background"

    if requested == "celery":
        task = process_document_task.apply_async(args=[document_id], retry=False)
        return task.id, "celery"

    # Kafka / Temporal (and any non-default backend) go through the strategy
    # dispatcher so the selected infrastructure handles the document.
    from infrastructure.processing.dispatcher import ProcessingDispatcher
    from infrastructure.processing.interfaces import ProcessingRequest

    document = Document.objects.filter(pk=document_id).first()
    dispatcher = ProcessingDispatcher.from_name(requested)
    job_id = dispatcher.dispatch(
        ProcessingRequest(
            document_id=str(document_id),
            company_id=str(document.company_id) if document and document.company_id else "",
            user_id=str(document.uploaded_by_id) if document else "",
            backend=requested,
        )
    )
    return job_id, requested
