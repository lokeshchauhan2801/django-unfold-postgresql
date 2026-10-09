from uuid import UUID

from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.permissions import SAFE_METHODS, BasePermission

from company.models import Company, CompanyMembership

from .serializers import CompanyMembershipSerializer, CompanySerializer


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CanManageMemberships(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.method in SAFE_METHODS:
            return True
        if getattr(view, "action", None) == "create":
            company_id = request.data.get("company")
            try:
                company_id = UUID(str(company_id))
            except (TypeError, ValueError):
                return False
            return bool(
                company_id
                and CompanyMembership.objects.filter(
                    user=request.user,
                    company_id=company_id,
                    role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
                    status=CompanyMembership.Status.ACTIVE,
                    company__is_active=True,
                ).exists()
            )
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.method in SAFE_METHODS:
            return True
        return CompanyMembership.objects.filter(
            user=request.user,
            company_id=obj.company_id,
            role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
            status=CompanyMembership.Status.ACTIVE,
        ).exists()


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [SearchFilter]
    search_fields = ["name", "slug"]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Company.objects.all()
        return Company.objects.filter(
            memberships__user=self.request.user,
            memberships__status=CompanyMembership.Status.ACTIVE,
            is_active=True,
        ).distinct()

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [permissions.IsAuthenticated()]
        return [IsSystemAdmin()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class CompanyMembershipViewSet(viewsets.ModelViewSet):
    queryset = CompanyMembership.objects.select_related("user", "company")
    serializer_class = CompanyMembershipSerializer

    def get_queryset(self):
        queryset = super().get_queryset().order_by("company__name", "user__username")
        if self.request.user.is_superuser:
            return queryset

        admin_company_ids = CompanyMembership.objects.filter(
            user=self.request.user,
            role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
            status=CompanyMembership.Status.ACTIVE,
            company__is_active=True,
        ).values_list("company_id", flat=True)
        return queryset.filter(
            Q(user=self.request.user) | Q(company_id__in=admin_company_ids)
        ).distinct()

    def get_permissions(self):
        return [CanManageMemberships()]

    def perform_create(self, serializer):
        company = serializer.validated_data["company"]
        if not self.request.user.is_superuser and not CompanyMembership.objects.filter(
            user=self.request.user,
            company=company,
            role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
            status=CompanyMembership.Status.ACTIVE,
        ).exists():
            raise PermissionDenied("You cannot add members to this company.")
        serializer.save()
