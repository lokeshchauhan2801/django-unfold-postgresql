from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Company, CompanyMembership
from .serializers import CompanySerializer, CompanyMembershipSerializer


class CompanyListCreateView(generics.ListCreateAPIView):
    """List companies the authenticated user belongs to, or create a new one."""
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Company.objects.filter(
            memberships__user=self.request.user,
            memberships__status='active',
        ).distinct()

    def perform_create(self, serializer):
        company = serializer.save()
        CompanyMembership.objects.create(
            user=self.request.user,
            company=company,
            role=CompanyMembership.Role.OWNER,
            status=CompanyMembership.Status.ACTIVE,
        )


class CompanyDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Company.objects.filter(
            memberships__user=self.request.user,
            memberships__status='active',
        )


class MyCompaniesView(APIView):
    """Return all companies the current user belongs to with membership details."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = CompanyMembership.objects.filter(
            user=request.user,
            status='active',
        ).select_related('company')
        serializer = CompanyMembershipSerializer(memberships, many=True)
        return Response({'success': True, 'data': serializer.data})
