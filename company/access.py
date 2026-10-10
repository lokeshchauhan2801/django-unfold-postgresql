"""Centralised multi-tenant access control.

Every company-scoped query in the project (conversations, messages, documents,
files, chunks, members) must go through the helpers in this module so tenant
isolation and role rules live in one place.

Access model
------------
* **System administrator** (``user.is_superuser``) — may act within any active
  company. They pick a company the same way members do (via the active-company
  session key) and then see *all* of that company's data. They may also list
  every company to switch between them.
* **Company admin/owner** — an active ``owner``/``admin`` membership. Within
  their own company they see *all* conversations, documents and members. They
  can never reach another company's data.
* **Regular member/viewer** — an active membership that is not owner/admin.
  They see only their *own* conversations and the documents they can access
  for their active company, never another company's data.
"""

# Role tuple is resolved lazily (see ``_admin_roles``) because models cannot be
# imported at module load time: ``base.admin_config`` imports this module while
# the app registry is still initialising.
def _admin_roles():
    from company.models import CompanyMembership

    return (CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN)


# --------------------------------------------------------------------------- #
#  Membership / company resolution                                            #
# --------------------------------------------------------------------------- #
def active_memberships_for_user(user):
    """Active memberships in active companies for ``user``."""
    from company.models import CompanyMembership

    if not user.is_authenticated:
        return CompanyMembership.objects.none()
    return CompanyMembership.objects.filter(
        user=user,
        status=CompanyMembership.Status.ACTIVE,
        company__is_active=True,
    ).select_related("company")


def active_companies_for_user(user):
    """Companies a user may open.

    Superusers may open any active company; everyone else only companies where
    they hold an active membership.
    """
    from company.models import Company, CompanyMembership

    if not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        return Company.objects.filter(is_active=True).order_by("name")
    return (
        Company.objects.filter(
            memberships__user=user,
            memberships__status=CompanyMembership.Status.ACTIVE,
            is_active=True,
        )
        .distinct()
        .order_by("name")
    )


def company_options_for_request(request):
    return list(
        active_companies_for_user(request.user).values("id", "name", "slug", "logo")
    )


def active_company_for_request(request):
    """Resolve the company the current request operates within.

    Honours an explicit session selection (validated against the user's
    allowed companies). Auto-selects when exactly one company is available.
    Returns ``None`` when the user still has to choose.
    """
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


def can_access_company(user, company):
    """Whether ``user`` may operate inside ``company`` at all."""
    if company is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return bool(getattr(company, "is_active", False))
    return active_memberships_for_user(user).filter(company=company).exists()


# --------------------------------------------------------------------------- #
#  Role resolution                                                            #
# --------------------------------------------------------------------------- #
def membership_role(user, company):
    """Return the user's role string in ``company`` (or ``None``)."""
    if company is None or not user.is_authenticated:
        return None
    membership = active_memberships_for_user(user).filter(company=company).first()
    return membership.role if membership else None


def is_company_admin(user, company):
    """Owner/admin of ``company`` — superusers are always treated as admins."""
    if company is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        active_memberships_for_user(user)
        .filter(company=company, role__in=_admin_roles())
        .exists()
    )


def is_active_company_admin(user, company_ids=None):
    """Whether the user is an active owner/admin of any (optionally filtered)
    company. Used by the Unfold admin to gate module/page access.
    """
    from company.models import CompanyMembership

    if not user.is_authenticated:
        return False
    memberships = CompanyMembership.objects.filter(
        user=user,
        status=CompanyMembership.Status.ACTIVE,
        role__in=_admin_roles(),
        company__is_active=True,
    )
    if company_ids is not None:
        memberships = memberships.filter(company_id__in=company_ids)
    return memberships.exists()


def effective_role_label(user, company):
    """Human/UI-facing role for the active company."""
    if user.is_superuser:
        return "system_admin"
    role = membership_role(user, company)
    if role in _admin_roles():
        return "company_admin"
    return role or "member"


def company_permissions(user, company):
    """Permission flags the frontend uses to toggle dashboard capabilities."""
    admin = is_company_admin(user, company)
    return {
        "is_system_admin": bool(user.is_superuser),
        "is_company_admin": bool(admin),
        "can_view_all_conversations": bool(admin),
        "can_view_members": bool(admin),
        "can_switch_company": active_companies_for_user(user).count() > 1,
    }


# --------------------------------------------------------------------------- #
#  Company metadata (name + logo) for the frontend                            #
# --------------------------------------------------------------------------- #
def company_metadata(company):
    """Serialise company name/logo/slug for API + bootstrap config."""
    if company is None:
        return None
    logo_url = ""
    if getattr(company, "logo", None):
        try:
            logo_url = company.logo.url
        except ValueError:
            logo_url = ""
    return {
        "id": str(company.pk),
        "name": company.name,
        "slug": company.slug,
        "logo_url": logo_url,
    }


# --------------------------------------------------------------------------- #
#  Query scoping — the single source of truth for tenant isolation            #
# --------------------------------------------------------------------------- #
def scoped_conversations(user, company, base_queryset=None):
    """Conversations the user may see in ``company``.

    Company admins/owners and system admins see *all* of the company's
    conversations; regular members see only their own. When ``company`` is
    ``None`` (legacy personal workspace, no membership) the user sees only
    their own unscoped conversations — never a global view.
    """
    from chat.models import Conversation

    queryset = (
        base_queryset if base_queryset is not None else Conversation.objects.all()
    )
    if not user.is_authenticated:
        return queryset.none()
    if company is None:
        return queryset.filter(user=user, company__isnull=True)
    if not can_access_company(user, company):
        return queryset.none()
    queryset = queryset.filter(company=company)
    if is_company_admin(user, company):
        return queryset
    return queryset.filter(user=user)


def scoped_documents(user, company, base_queryset=None):
    """Documents the user may see in ``company``.

    Company admins/owners and system admins see *all* company documents;
    regular members see only documents they uploaded within the company. When
    ``company`` is ``None`` (personal workspace) the user sees only their own
    unscoped uploads.
    """
    from docs.models import Document

    queryset = base_queryset if base_queryset is not None else Document.objects.all()
    if not user.is_authenticated:
        return queryset.none()
    if company is None:
        return queryset.filter(uploaded_by=user, company__isnull=True)
    if not can_access_company(user, company):
        return queryset.none()
    queryset = queryset.filter(company=company)
    if is_company_admin(user, company):
        return queryset
    return queryset.filter(uploaded_by=user)


def scoped_members(user, company):
    """Active memberships of ``company`` — admins only.

    Regular members may not enumerate the company's roster.
    """
    from company.models import CompanyMembership

    if company is None or not is_company_admin(user, company):
        return CompanyMembership.objects.none()
    return (
        CompanyMembership.objects.filter(company=company)
        .select_related("user", "company")
        .order_by("role", "user__email")
    )
