"""
Scrapper service layer — handles document ingestion logic.
"""
import mimetypes
import os
from urllib.parse import urlparse

from django.core.files.uploadedfile import UploadedFile

from .models import Document, QueueMessage


def _infer_document_type(filename: str) -> str:
    """Guess the DocumentType from a filename or extension."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mapping = {
        "pdf": Document.DocumentType.PDF,
        "csv": Document.DocumentType.CSV,
        "docx": Document.DocumentType.DOCX,
        "doc": Document.DocumentType.DOCX,
        "xlsx": Document.DocumentType.XLSX,
        "xls": Document.DocumentType.XLSX,
        "txt": Document.DocumentType.TXT,
        "md": Document.DocumentType.MD,
        "json": Document.DocumentType.JSON,
    }
    return mapping.get(ext, Document.DocumentType.OTHER)


def create_document_from_file(
    *,
    uploaded_file: UploadedFile,
    company_id,
    created_by,
    title: str | None = None,
) -> Document:
    """
    Persist an uploaded file as a Document and enqueue it for processing.
    """
    name = uploaded_file.name or "unnamed"
    doc_type = _infer_document_type(name)
    doc = Document.objects.create(
        title=title or name,
        document_type=doc_type,
        file=uploaded_file,
        file_size=uploaded_file.size,
        content_type=uploaded_file.content_type or "",
        status=Document.Status.QUEUED,
        company_id=company_id,
        created_by=created_by,
        updated_by=created_by,
    )
    _enqueue(doc, created_by)
    return doc


def create_document_from_url(
    *,
    url: str,
    company_id,
    created_by,
    title: str | None = None,
) -> Document:
    """
    Create a Document from a URL and enqueue it for scraping.
    """
    parsed = urlparse(url)
    inferred_title = title or parsed.netloc + parsed.path
    doc = Document.objects.create(
        title=inferred_title,
        document_type=Document.DocumentType.URL,
        source_url=url,
        status=Document.Status.QUEUED,
        company_id=company_id,
        created_by=created_by,
        updated_by=created_by,
    )
    _enqueue(doc, created_by)
    return doc


def _enqueue(document: Document, created_by) -> QueueMessage:
    """Create a QueueMessage and optionally dispatch to Celery."""
    msg = QueueMessage.objects.create(
        document=document,
        company=document.company,
        created_by=created_by,
        updated_by=created_by,
        status=QueueMessage.MessageStatus.QUEUED,
    )
    # Dispatch async task (Celery task defined in tasks.py)
    try:
        from .tasks import process_scrapper_document

        result = process_scrapper_document.delay(str(document.id))
        msg.task_id = result.id
        msg.save(update_fields=["task_id"])
        document.processing_task_id = result.id
        document.save(update_fields=["processing_task_id"])
    except Exception:
        # Celery may not be available in dev; processing will be handled manually
        pass
    return msg
