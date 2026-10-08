from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.basics.admin import AuditAdminMixin

from .models import Company, CompanyMembership


@admin.register(Company)
class CompanyAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("name", "slug", "website", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug", "website")
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "created_at"


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("user", "company", "role", "status", "joined_at")
    list_filter = ("role", "status", "company")
    search_fields = ("user__email", "company__name")
    raw_id_fields = ("user", "company")
    readonly_fields = ("id", "joined_at")
