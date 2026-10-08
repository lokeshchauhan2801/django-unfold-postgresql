from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ('action', 'user', 'company', 'resource_type', 'resource_id', 'ip_address', 'created_at')
    list_filter = ('action', 'resource_type', 'created_at')
    search_fields = ('action', 'user__username', 'resource_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'user', 'company', 'action', 'resource_type', 'resource_id', 'metadata', 'ip_address')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
