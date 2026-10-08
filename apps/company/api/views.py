from rest_framework import permissions, viewsets
from rest_framework.filters import SearchFilter

from apps.basics.mixins import CompanyFilterMixin
from apps.company.models import Company, CompanyMembership

from .serializers import CompanyMembershipSerializer, CompanySerializer


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ["name", "slug"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class CompanyMembershipViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = CompanyMembership.objects.select_related("user", "company")
    serializer_class = CompanyMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
