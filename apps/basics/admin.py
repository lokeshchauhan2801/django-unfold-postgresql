from django.contrib import admin


class AuditAdminMixin:
    """
    Mixin for ModelAdmin that automatically populates created_by / updated_by
    and makes those fields readonly.
    """

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for f in ("id", "created_at", "updated_at", "created_by", "updated_by"):
            if f not in readonly:
                readonly.append(f)
        return readonly

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
