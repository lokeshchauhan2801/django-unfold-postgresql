from rest_framework.permissions import BasePermission


class IsCompanyMember(BasePermission):
    """Requires the user to be a member of the company specified in the request."""
    message = "You are not a member of this company."

    def has_permission(self, request, view):
        company_id = (
            view.kwargs.get("company_id")
            or request.data.get("company_id")
            or request.query_params.get("company_id")
        )
        if not company_id:
            return True  # Let object-level permission handle it
        if not request.user or not request.user.is_authenticated:
            return False
        from apps.company.models import CompanyMembership
        return CompanyMembership.objects.filter(
            user=request.user,
            company_id=company_id,
            status="active",
        ).exists()


class IsCompanyAdmin(BasePermission):
    """Requires the user to be OWNER or ADMIN of the company."""
    message = "You must be a company admin or owner."

    def has_permission(self, request, view):
        company_id = view.kwargs.get("company_id") or request.data.get("company_id")
        if not company_id or not request.user or not request.user.is_authenticated:
            return False
        from apps.company.models import CompanyMembership
        return CompanyMembership.objects.filter(
            user=request.user,
            company_id=company_id,
            role__in=["owner", "admin"],
            status="active",
        ).exists()
