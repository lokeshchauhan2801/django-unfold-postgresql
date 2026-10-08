from django.db import models

from apps.basics.models import BaseModel


class Document(BaseModel):
    """
    Represents a scraped/uploaded document.
    Supports both file uploads (any type) and URL-based documents.
    Columns visible in admin: ID, Title, Document type, Status, Chunks, Actions,
    Created by, Created at.
    """

    class DocumentType(models.TextChoices):
        PDF = "PDF", "PDF"
        CSV = "CSV", "CSV"
        DOCX = "DOCX", "DOCX"
        XLSX = "XLSX", "XLSX"
        TXT = "TXT", "TXT"
        MD = "MD", "Markdown"
        JSON = "JSON", "JSON"
        URL = "URL", "URL"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=500)
    document_type = models.CharField(
        max_length=10,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    chunk_count = models.PositiveIntegerField(default=0)

    # Source — one of these will be filled in
    file = models.FileField(upload_to="scrapper/documents/%Y/%m/%d/", null=True, blank=True)
    source_url = models.URLField(max_length=2000, blank=True)

    # Optional metadata
    file_size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=150, blank=True)
    processing_error = models.TextField(blank=True)
    processing_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "scrapper_document"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["document_type"]),
            models.Index(fields=["company", "status"]),
        ]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self) -> str:
        return self.title

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.file and not self.source_url:
            raise ValidationError("A document must have either a file upload or a source URL.")

    @property
    def is_url(self) -> bool:
        return bool(self.source_url)


class DocumentChunk(models.Model):
    """Individual text chunk extracted from a Document."""

    import uuid as _uuid

    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(default=0)
    source_location = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scrapper_document_chunk"
        ordering = ["document", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="scrapper_document_chunk_idx_uniq",
            ),
        ]
        verbose_name = "Document Chunk"
        verbose_name_plural = "Document Chunks"

    def __str__(self) -> str:
        return f"{self.document.title} · chunk {self.chunk_index}"


class QueueMessage(BaseModel):
    """
    Represents a message in the processing queue for a document.
    Tracks async task state and progress.
    """

    class MessageStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        RETRYING = "retrying", "Retrying"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="queue_messages")
    task_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=MessageStatus.choices, default=MessageStatus.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(max_length=60, blank=True)
    error = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "scrapper_queue_message"
        ordering = ["-created_at"]
        verbose_name = "Queue Message"
        verbose_name_plural = "Queue Messages"

    def __str__(self) -> str:
        return f"QueueMessage({self.document.title}, {self.status})"
