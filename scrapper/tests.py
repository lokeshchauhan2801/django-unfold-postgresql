from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from company.models import Company, CompanyMembership
from scrapper.models import Document, DocumentChunk


class ScrapperCompanyScopeTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="acme-member",
            email="acme-member@example.com",
            password="member-password",
        )
        other_user = user_model.objects.create_user(
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
        self.company_document = Document.objects.create(
            title="Acme handbook",
            company=self.company,
            created_by=other_user,
        )
        other_document = Document.objects.create(
            title="Globex handbook",
            company=self.other_company,
            created_by=other_user,
        )
        DocumentChunk.objects.create(
            document=self.company_document,
            chunk_index=0,
            content="Acme-only text",
        )
        DocumentChunk.objects.create(
            document=other_document,
            chunk_index=0,
            content="Globex-only text",
        )
        self.client.force_login(self.user)

    def test_document_and_chunk_lists_are_limited_to_member_companies(self):
        documents = self.client.get(reverse("scrapper-document-list"))
        chunks = self.client.get(reverse("scrapper-document-chunk-list"))

        self.assertEqual(documents.status_code, 200)
        self.assertEqual(
            [item["title"] for item in documents.json()["results"]],
            ["Acme handbook"],
        )
        self.assertEqual(chunks.status_code, 200)
        self.assertEqual(
            [item["content"] for item in chunks.json()["results"]],
            ["Acme-only text"],
        )

    def test_document_api_rejects_unrelated_company_uploads(self):
        response = self.client.post(
            reverse("scrapper-document-list"),
            {
                "title": "unauthorized.txt",
                "source_url": "https://example.com/file.txt",
                "company": str(self.other_company.pk),
            },
        )

        self.assertEqual(response.status_code, 403)

    @patch("scrapper.api.views.create_document_from_url")
    def test_document_creation_uses_the_only_active_company(self, create_document):
        document = Document.objects.create(
            title="Company policy",
            company=self.company,
            created_by=self.user,
        )
        create_document.return_value = document

        response = self.client.post(
            reverse("scrapper-document-list"),
            {"title": "Company policy", "source_url": "https://example.com/policy"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            create_document.call_args.kwargs["company_id"],
            str(self.company.pk),
        )
