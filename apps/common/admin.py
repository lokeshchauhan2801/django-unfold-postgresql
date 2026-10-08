from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(ModelAdmin):
    list_display = ('key', 'value', 'description', 'updated_at')
    search_fields = ('key', 'description')
    readonly_fields = ('created_at', 'updated_at')
