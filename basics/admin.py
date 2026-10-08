from django.contrib import admin
from unfold.admin import ModelAdmin

from company.access import is_active_company_admin
from company.models import CompanyMembership

from .models import SystemSetting


class CompanyScopedAdminMixin:
    """Show company administrators only records owned by their active companies."""

    def company_ids(self, request):
        return CompanyMembership.objects.filter(
            user=request.user,
            status=CompanyMembership.Status.ACTIVE,
            role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
            company__is_active=True,
        ).values_list("company_id", flat=True)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset

        company_ids = self.company_ids(request)
        if not is_active_company_admin(request.user, company_ids):
            return queryset.none()

        model = self.model
        if model._meta.app_label == "company" and model._meta.model_name == "company":
            return queryset.filter(pk__in=company_ids)
        if model._meta.app_label == "company" and model._meta.model_name == "companymembership":
            return queryset.filter(company_id__in=company_ids)
        if any(field.name == "company" for field in model._meta.get_fields()):
            return queryset.filter(company_id__in=company_ids)
        if model._meta.app_label == "chat":
            relation = {
                "message": "conversation__company_id__in",
                "messageversion": "message__conversation__company_id__in",
            }.get(model._meta.model_name)
            if relation:
                return queryset.filter(**{relation: company_ids})
        if model._meta.app_label == "documents" and model._meta.model_name == "documentchunk":
            return queryset.filter(document__company_id__in=company_ids)
        return queryset.none()

    def has_module_permission(self, request):
        return request.user.is_superuser or is_active_company_admin(request.user)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not is_active_company_admin(request.user):
            return False
        return obj is None or self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class AuditAdminMixin:
    """
    Mixin for ModelAdmin that automatically populates created_by / updated_by
    and makes those fields readonly.
    """

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        model_field_names = {field.name for field in self.model._meta.get_fields()}
        for f in ("id", "created_at", "updated_at", "created_by", "updated_by"):
            if f in model_field_names and f not in readonly:
                readonly.append(f)
        return readonly

    def save_model(self, request, obj, form, change):
        model_field_names = {field.name for field in self.model._meta.get_fields()}
        if not change and "created_by" in model_field_names:
            obj.created_by = request.user
        if "updated_by" in model_field_names:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SystemSetting)
class SystemSettingAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("key", "value", "description", "updated_at")
    search_fields = ("key",)
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
