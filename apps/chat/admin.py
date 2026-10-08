from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.basics.admin import AuditAdminMixin

from .models import Conversation, Message, MessageVersion


@admin.register(Conversation)
class ConversationAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("title", "user", "company", "created_at", "updated_at")
    list_filter = ("company", "created_at")
    search_fields = ("title", "user__email")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
    date_hierarchy = "created_at"


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ("conversation", "role", "content_preview", "has_chart", "model_name", "created_at")
    list_filter = ("role", "model_name", "created_at")
    search_fields = ("content", "conversation__title")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("conversation", "parent")

    def content_preview(self, obj):
        return obj.content[:60]
    content_preview.short_description = "Content"

    @admin.display(boolean=True, description="Chart")
    def has_chart(self, obj):
        return bool(obj.chart_data)


@admin.register(MessageVersion)
class MessageVersionAdmin(ModelAdmin):
    list_display = ("message", "version", "created_at")
    list_filter = ("version",)
    readonly_fields = ("id", "created_at")
