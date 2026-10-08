def active_companies_for_user(user):
    from company.models import Company, CompanyMembership

    if not user.is_authenticated:
        return Company.objects.none()
    return Company.objects.filter(
        memberships__user=user,
        memberships__status=CompanyMembership.Status.ACTIVE,
        is_active=True,
    ).distinct().order_by("name")


def company_options_for_request(request):
    return list(
        active_companies_for_user(request.user).values("id", "name")
    )


def active_company_for_request(request):
    companies = active_companies_for_user(request.user)
    company_id = request.session.get("active_company_id")
    if company_id:
        company = companies.filter(pk=company_id).first()
        if company:
            return company
        request.session.pop("active_company_id", None)

    if companies.count() == 1:
        company = companies.first()
        request.session["active_company_id"] = str(company.pk)
        return company
    return None


def company_selection_required(request):
    return (
        active_companies_for_user(request.user).count() > 1
        and not active_company_for_request(request)
    )


def is_active_company_admin(user, company_ids=None):
    from company.models import CompanyMembership

    if not user.is_authenticated:
        return False
    memberships = CompanyMembership.objects.filter(
        user=user,
        status=CompanyMembership.Status.ACTIVE,
        role__in=(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN),
        company__is_active=True,
    )
    if company_ids is not None:
        memberships = memberships.filter(company_id__in=company_ids)
    return memberships.exists()
