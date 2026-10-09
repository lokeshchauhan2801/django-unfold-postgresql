import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    STATUS_UPLOADED = "uploaded"
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        db_index=True,
    )
    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/%Y/%m/%d/")
    file_type = models.CharField(max_length=20, default="pdf")
    content_type = models.CharField(max_length=150, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    processing_backend = models.CharField(max_length=50, default="celery")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    processing_stage = models.CharField(max_length=40, blank=True)
    processing_progress = models.PositiveSmallIntegerField(default=0)
    processing_task_id = models.CharField(max_length=255, blank=True)
    processing_error = models.TextField(blank=True)
    chunk_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_created",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_updated",
        editable=False,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["uploaded_by", "status"])]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField()
    source_location = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="document_chunk_index_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.document.title} · page {self.page_number} · chunk {self.chunk_index}"
