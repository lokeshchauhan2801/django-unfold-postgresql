"""
Shared mixins for serializers and views across the project.
"""


class AuditSerializerMixin:
    """
    DRF serializer mixin that makes audit fields read-only.
    """

    def get_read_only_fields(self):
        base = list(getattr(self.Meta, "read_only_fields", []))
        for f in ("id", "created_at", "updated_at", "created_by", "updated_by"):
            if f not in base:
                base.append(f)
        return tuple(base)


class CompanyFilterMixin:
    """
    DRF view mixin that filters queryset by the company of the current user.
    Assumes the model has a `company` FK.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        company_id = self.request.query_params.get("company")
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
