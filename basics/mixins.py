"""
Shared mixins for serializers and views across the project.
"""

from uuid import UUID

from django.db.models import Q

from company.models import CompanyMembership


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

    def filter_by_company(self, queryset, company_id):
        if (
            queryset.model._meta.app_label == "scrapper"
            and queryset.model._meta.model_name == "documentchunk"
        ):
            return queryset.filter(document__company_id=company_id)
        return queryset.filter(company_id=company_id)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            company_id = self.request.query_params.get("company")
            if company_id:
                try:
                    company_id = UUID(company_id)
                except (TypeError, ValueError):
                    return queryset.none()
                return self.filter_by_company(queryset, company_id)
            return queryset

        company_ids = CompanyMembership.objects.filter(
            user=user,
            status=CompanyMembership.Status.ACTIVE,
            company__is_active=True,
        ).values_list("company_id", flat=True)
        requested_company_id = self.request.query_params.get("company")
        if requested_company_id:
            try:
                requested_company_id = UUID(requested_company_id)
            except (TypeError, ValueError):
                return queryset.none()
            if not company_ids.filter(company_id=requested_company_id).exists():
                return queryset.none()
            return self.filter_by_company(queryset, requested_company_id)

        if (
            queryset.model._meta.app_label == "scrapper"
            and queryset.model._meta.model_name == "documentchunk"
        ):
            return queryset.filter(
                Q(document__company_id__in=company_ids)
                | Q(document__company__isnull=True, document__created_by=user)
            )
        if any(field.name == "company" for field in queryset.model._meta.get_fields()):
            return queryset.filter(
                Q(company_id__in=company_ids)
                | Q(company__isnull=True, created_by=user)
            )
        return queryset.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
