from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.basics.admin import AuditAdminMixin

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(AuditAdminMixin, ModelAdmin):
    list_display = (
        "title",
        "file_type",
        "file_size",
        "uploaded_by",
        "company",
        "status",
        "processing_stage",
        "processing_progress",
        "chunk_count",
        "processing_backend",
        "created_at",
    )
    list_filter = ("file_type", "status", "processing_backend", "company", "created_at")
    search_fields = ("title", "uploaded_by__email")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "processing_stage",
        "processing_progress",
        "processing_task_id",
        "processing_error",
        "chunk_count",
        "file_size",
        "content_type",
    )
    date_hierarchy = "created_at"


@admin.register(DocumentChunk)
class DocumentChunkAdmin(ModelAdmin):
    list_display = ("id", "document", "chunk_index", "source_location", "page_number", "created_at")
    list_filter = ("document",)
    search_fields = ("id", "document__title", "content")
    readonly_fields = ("id", "document", "chunk_index", "source_location", "page_number", "content", "created_at")
    list_display_links = ("id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
