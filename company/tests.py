from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from chat.models import Conversation
from company.admin import CompanyMembershipAdmin
from company.models import Company, CompanyMembership
from docs.models import Document


class CompanyMembershipAdminTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="Admin-password-123",
        )
        self.client.force_login(self.admin_user)

    def test_membership_add_page_loads(self):
        response = self.client.get(reverse("admin:company_companymembership_add"))

        self.assertEqual(response.status_code, 200)

    def test_membership_admin_does_not_inject_missing_audit_fields(self):
        model_admin = CompanyMembershipAdmin(CompanyMembership, admin.site)
        readonly_fields = model_admin.get_readonly_fields(request=None)

        self.assertNotIn("created_at", readonly_fields)
        self.assertNotIn("updated_at", readonly_fields)
        self.assertNotIn("created_by", readonly_fields)
        self.assertNotIn("updated_by", readonly_fields)


class CompanyAdminSiteTests(TestCase):
    def test_company_admin_can_open_admin_without_staff_flag(self):
        user = get_user_model().objects.create_user(
            username="company-admin",
            email="company-admin@example.com",
            password="Company-admin-password-123",
        )
        company = Company.objects.create(name="Acme", slug="acme")
        CompanyMembership.objects.create(
            user=user,
            company=company,
            role=CompanyMembership.Role.ADMIN,
        )
        self.client.force_login(user)

        login_redirect = self.client.get(reverse("shared_admin_login"))
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(login_redirect.status_code, 302)
        self.assertEqual(login_redirect.headers["Location"], "/admin/")
        self.assertEqual(response.status_code, 200)


class CompanyApiScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="acme-member",
            email="acme-member@example.com",
            password="member-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="globex-member",
            email="globex-member@example.com",
            password="other-password",
        )
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.other_company = Company.objects.create(name="Globex", slug="globex")
        CompanyMembership.objects.create(
            user=self.user,
            company=self.company,
            role=CompanyMembership.Role.MEMBER,
        )
        CompanyMembership.objects.create(
            user=self.other_user,
            company=self.company,
            role=CompanyMembership.Role.MEMBER,
        )
        CompanyMembership.objects.create(
            user=self.other_user,
            company=self.other_company,
            role=CompanyMembership.Role.MEMBER,
        )
        self.client.force_login(self.user)

    def test_company_and_membership_lists_do_not_expose_other_tenants(self):
        companies = self.client.get(reverse("company-list"))
        memberships = self.client.get(reverse("company-membership-list"))

        self.assertEqual(companies.status_code, 200)
        self.assertEqual(
            [item["slug"] for item in companies.json()["results"]],
            ["acme"],
        )
        self.assertEqual(memberships.status_code, 200)
        self.assertEqual(
            {item["company"] for item in memberships.json()["results"]},
            {str(self.company.pk)},
        )

    def test_non_admin_cannot_create_a_company_or_company_membership(self):
        create_company = self.client.post(
            reverse("company-list"),
            {"name": "New Co", "slug": "new-co"},
        )
        create_membership = self.client.post(
            reverse("company-membership-list"),
            {
                "user": str(self.other_user.pk),
                "company": str(self.company.pk),
                "role": CompanyMembership.Role.ADMIN,
            },
        )

        self.assertEqual(create_company.status_code, 403)
        self.assertEqual(create_membership.status_code, 403)


class CompanyMembershipDataAssignmentTests(TestCase):
    def test_first_company_membership_assigns_unscoped_user_chats_and_files(self):
        user = get_user_model().objects.create_user(
            username="legacy-user",
            email="legacy-user@example.com",
            password="legacy-password",
        )
        conversation = Conversation.objects.create(user=user, title="Older chat")
        document = Document.objects.create(
            uploaded_by=user,
            conversation=conversation,
            title="older.txt",
            file="documents/older.txt",
            file_type="txt",
        )
        company = Company.objects.create(name="Acme", slug="acme")

        CompanyMembership.objects.create(
            user=user,
            company=company,
            role=CompanyMembership.Role.OWNER,
        )

        conversation.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(conversation.company, company)
        self.assertEqual(document.company, company)
