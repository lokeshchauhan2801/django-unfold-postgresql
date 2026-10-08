from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action

from basics.admin import AuditAdminMixin, CompanyScopedAdminMixin

from .models import Document, DocumentChunk, QueueMessage


@admin.register(Document)
class DocumentAdmin(CompanyScopedAdminMixin, AuditAdminMixin, ModelAdmin):
    # Matches screenshot: ID, Title, Document type, Status, Chunks, Actions, Created by, Created at
    list_display = (
        "id_short",
        "title",
        "document_type",
        "status_badge",
        "chunk_count",
        "company",
        "created_by",
        "created_at",
    )
    list_filter = ("document_type", "status", "created_at", "company")
    search_fields = ("title",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        ("Document", {"fields": ("title", "document_type", "status", "company")}),
        ("Source", {"fields": ("file", "source_url")}),
        ("Metadata", {"fields": ("file_size", "content_type", "chunk_count", "processing_error", "processing_task_id")}),
        ("Audit", {"fields": ("id", "created_by", "updated_by", "created_at", "updated_at")}),
    )
    readonly_fields = (
        "id",
        "chunk_count",
        "file_size",
        "content_type",
        "processing_error",
        "processing_task_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    @admin.display(description="ID")
    def id_short(self, obj):
        return str(obj.id)[:8]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "done": "#6c757d",
            "pending": "#ffc107",
            "queued": "#0d6efd",
            "processing": "#0dcaf0",
            "failed": "#dc3545",
        }
        colour = colours.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{}</span>',
            colour,
            obj.get_status_display(),
        )

    @admin.display(description="Document type")
    def document_type_display(self, obj):
        return obj.get_document_type_display()


@admin.register(DocumentChunk)
class DocumentChunkAdmin(CompanyScopedAdminMixin, ModelAdmin):
    list_display = ("id", "document", "chunk_index", "page_number", "source_location", "created_at")
    list_filter = ("document",)
    search_fields = ("id", "document__title", "content")
    readonly_fields = ("id", "document", "chunk_index", "page_number", "source_location", "content", "created_at")
    list_display_links = ("id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(QueueMessage)
class QueueMessageAdmin(CompanyScopedAdminMixin, AuditAdminMixin, ModelAdmin):
    list_display = ("document", "status", "progress", "stage", "task_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("document__title", "task_id")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
