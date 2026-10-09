"""Celery tasks for the scrapper app."""

from celery import shared_task


@shared_task(bind=True, max_retries=3)
def process_scrapper_document(self, document_id: str):
    """
    Process a scrapper Document:
    - If it has a file: extract text and split into chunks.
    - If it has a source_url: fetch, extract text, split into chunks.
    """
    from .models import Document, QueueMessage

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return

    queue_msg = doc.queue_messages.order_by("-created_at").first()

    try:
        _update_status(doc, queue_msg, Document.Status.PROCESSING, "started")

        if doc.is_url:
            _process_url(doc)
        else:
            _process_file(doc)

        _update_status(doc, queue_msg, Document.Status.DONE, "completed", progress=100)

    except Exception as exc:
        error_msg = str(exc)
        doc.processing_error = error_msg
        doc.status = Document.Status.FAILED
        doc.save(update_fields=["status", "processing_error"])
        if queue_msg:
            queue_msg.status = QueueMessage.MessageStatus.FAILED
            queue_msg.error = error_msg
            queue_msg.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)


def _update_status(doc, queue_msg, status, stage, progress=None):
    from .models import Document

    doc.status = status
    update_fields = ["status"]
    if progress is not None:
        doc.chunk_count = doc.chunks.count()
        update_fields.append("chunk_count")
    doc.save(update_fields=update_fields)
    if queue_msg:
        queue_msg.status = status
        queue_msg.stage = stage
        if progress is not None:
            queue_msg.progress = progress
        queue_msg.save(update_fields=["status", "stage", "progress"])


def _process_file(doc):
    """Stub: extract text from file and create chunks."""
    # Real implementation would use a text extractor (pdfminer, docx, etc.)
    pass


def _process_url(doc):
    """Stub: fetch URL, extract text, and create chunks."""
    # Real implementation would use httpx + BeautifulSoup / readability
    pass
