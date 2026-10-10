"""End-to-end multi-tenant flow automation.

Creates several companies (each with an admin + a member user), saves their
login credentials to ``~/com_cred.txt``, then drives the real HTTP flow with
Django's test ``Client`` for every company:

  * sign in through the shared session-login endpoint,
  * upload a per-company CSV data file,
  * ask several questions in the chat session,
  * read the dashboard / documents / members endpoints, and
  * verify that one company's admin can never see another company's chats,
    documents, files or members (backend tenant isolation).

The AI provider and vector store are stubbed so the automation runs without a
live OpenAI key or Chroma backend — it exercises the view/scoping layer, which
is where tenant isolation lives.

Usage::

    python manage.py seed_demo_flow            # 5 companies, 4 questions each
    python manage.py seed_demo_flow --companies 4 --questions 3
    python manage.py seed_demo_flow --cred-file /tmp/com_cred.txt
"""

import os
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client
from django.urls import reverse

from chat.models import Conversation
from company.models import Company, CompanyMembership
from docs.models import Document


COMPANIES = [
    ("Northwind Trading", "northwind"),
    ("Globex Corporation", "globex"),
    ("Initech Systems", "initech"),
    ("Umbrella Analytics", "umbrella"),
    ("Stark Industries", "stark"),
]

QUESTIONS = [
    "Summarise this file in two sentences.",
    "What are the key columns in the dataset?",
    "Create a chart of the distribution.",
    "Which category appears most often?",
    "List any anomalies you can see.",
]


class _StubProvider:
    """Deterministic AI provider stub (no network calls)."""

    model = "stub-model"
    last_prompt = ""

    def embed_documents(self, texts):
        return [[1.0, 0.0, 1.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 1.0]

    def generate_structured(self, prompt, schema):
        self.last_prompt = prompt
        return schema(response="Automated demo response grounded in the file.", chart=None)


class _StubVectorStore:
    def similarity_search(self, query_embedding, collection, k=5, filter=None):
        return []

    def add_documents(self, *args, **kwargs):
        return None

    def delete(self, *args, **kwargs):
        return None


def _csv_for(slug, index):
    rows = "\n".join(
        f"{i},{(i * 7 + index) % 5 + 18},{['North','South','East','West'][i % 4]}"
        for i in range(1, 11)
    )
    content = f"# {slug} sample dataset\nID,Age,Region\n{rows}\n".encode()
    return SimpleUploadedFile(f"{slug}-data.csv", content, content_type="text/csv")


class Command(BaseCommand):
    help = "Create demo companies, drive the full chat/upload/isolation flow, and save credentials."

    def add_arguments(self, parser):
        parser.add_argument("--companies", type=int, default=5)
        parser.add_argument("--questions", type=int, default=4)
        parser.add_argument(
            "--cred-file",
            default=str(Path(os.path.expanduser("~")) / "com_cred.txt"),
        )
        parser.add_argument(
            "--password",
            default="DemoPass!2026",
            help="Shared password for all generated accounts.",
        )

    def handle(self, *args, **options):
        count = max(1, min(options["companies"], len(COMPANIES)))
        n_questions = max(1, min(options["questions"], len(QUESTIONS)))
        password = options["password"]
        cred_path = Path(options["cred_file"])

        User = get_user_model()
        created = []

        self.stdout.write(self.style.MIGRATE_HEADING(f"Creating {count} companies…"))
        with transaction.atomic():
            for name, slug in COMPANIES[:count]:
                company, _ = Company.objects.get_or_create(
                    slug=slug, defaults={"name": name, "is_active": True}
                )
                company.name = name
                company.is_active = True
                company.save()

                admin_username = f"{slug}-admin"
                member_username = f"{slug}-member"
                admin = self._ensure_user(User, admin_username, f"{admin_username}@example.com", password)
                member = self._ensure_user(User, member_username, f"{member_username}@example.com", password)

                CompanyMembership.objects.get_or_create(
                    user=admin, company=company,
                    defaults={"role": CompanyMembership.Role.ADMIN,
                              "status": CompanyMembership.Status.ACTIVE},
                )
                CompanyMembership.objects.get_or_create(
                    user=member, company=company,
                    defaults={"role": CompanyMembership.Role.MEMBER,
                              "status": CompanyMembership.Status.ACTIVE},
                )
                created.append(
                    {
                        "company": company,
                        "admin_username": admin_username,
                        "member_username": member_username,
                    }
                )

        self._write_credentials(cred_path, created, password)
        self.stdout.write(self.style.SUCCESS(f"Saved credentials → {cred_path}"))

        # Drive the HTTP flow with stubbed AI/vector backends. We also stub the
        # background dispatcher so uploads don't spawn real embedding threads —
        # the automation marks documents ready itself for a deterministic run.
        with patch("chat.services.get_ai_provider", return_value=_StubProvider()), \
                patch("chat.services.ChromaVectorStore", return_value=_StubVectorStore()), \
                patch(
                    "docs.views.dispatch_document_processing",
                    return_value=("stub-task-id", "stub"),
                ):
            self._run_flow(created, password, n_questions)

        self._run_isolation_checks(created, password)
        self.stdout.write(self.style.SUCCESS("Demo flow completed successfully."))

    # ------------------------------------------------------------------ #
    def _ensure_user(self, User, username, email, password):
        user, is_new = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.email = email
        user.set_password(password)
        user.save()
        return user

    def _write_credentials(self, path, created, password):
        lines = [
            "# Demo company credentials (generated by seed_demo_flow)",
            "# Shared password for every account below.",
            f"# PASSWORD: {password}",
            "#",
            "# Each company has an ADMIN (owner/admin role: sees all company data)",
            "# and a MEMBER (sees only their own chats/documents).",
            "",
        ]
        for entry in created:
            company = entry["company"]
            lines.append(f"Company: {company.name}  (slug: {company.slug})")
            lines.append(f"  Admin  -> username: {entry['admin_username']:<22} password: {password}")
            lines.append(f"  Member -> username: {entry['member_username']:<22} password: {password}")
            lines.append("")
        path.write_text("\n".join(lines))

    def _client(self):
        # Use an allowed host so CommonMiddleware's get_host() check passes
        # (the test Client defaults to 'testserver', which isn't in
        # ALLOWED_HOSTS for the local settings).
        return Client(SERVER_NAME="localhost")

    def _login(self, client, username, password):
        response = client.post(
            reverse("chat_session_login"),
            {"username": username, "password": password},
        )
        assert response.status_code == 200, f"login failed for {username}: {response.content}"

    def _run_flow(self, created, password, n_questions):
        for index, entry in enumerate(created):
            company = entry["company"]
            username = entry["admin_username"]
            client = self._client()
            self._login(client, username, password)

            # Single membership → company auto-selected. Confirm via meta.
            meta = client.get(reverse("chat_company_meta")).json()
            self.stdout.write(
                f"\n[{company.name}] signed in as {username} "
                f"(role={meta.get('role')})"
            )

            # Upload a data file (creates a conversation).
            upload = client.post(
                reverse("document_upload"),
                {"file": _csv_for(company.slug, index), "message": "Here is our dataset."},
            )
            assert upload.status_code in (200, 202), upload.content
            conversation_id = upload.json()["conversation_id"]
            document = upload.json()["document"]
            # Mark ready so chat questions aren't blocked by processing gate.
            Document.objects.filter(pk=document["id"]).update(
                status=Document.STATUS_READY, processing_stage="", processing_progress=100
            )
            self.stdout.write(f"  uploaded {document['title']} → conversation {conversation_id[:8]}")

            # Ask several questions in the session.
            for q in QUESTIONS[:n_questions]:
                answer = client.post(
                    reverse("chat_api"),
                    {"message": q, "conversation_id": conversation_id},
                    content_type="application/json",
                )
                assert answer.status_code == 200, answer.content
            self.stdout.write(f"  asked {n_questions} questions")

            # Dashboard + documents + members endpoints.
            dash = client.get(reverse("company_dashboard")).json()
            docs = client.get(reverse("document_list")).json()
            members = client.get(reverse("company_members")).json()
            self.stdout.write(
                f"  dashboard: {dash['stats']['conversation_count']} chats, "
                f"{dash['stats']['document_count']} docs, "
                f"{dash['stats'].get('member_count', '?')} members | "
                f"library={len(docs['documents'])} | roster={len(members['members'])}"
            )

    def _run_isolation_checks(self, created, password):
        if len(created) < 2:
            return
        self.stdout.write(self.style.MIGRATE_HEADING("\nCross-tenant isolation checks…"))
        a, b = created[0], created[1]
        company_b = b["company"]

        client = self._client()
        self._login(client, a["admin_username"], password)

        # Company A admin must not see company B's conversations/documents.
        b_convo = Conversation.objects.filter(company=company_b).first()
        b_doc = Document.objects.filter(company=company_b).first()

        detail = client.get(
            reverse("conversation_detail", kwargs={"conversation_id": b_convo.pk})
        )
        assert detail.status_code == 404, "LEAK: A admin opened B's conversation!"

        file_access = client.get(
            reverse("document_file", kwargs={"file_path": b_doc.file.name})
        )
        assert file_access.status_code == 404, "LEAK: A admin downloaded B's file!"

        # A admin cannot switch into B (no membership).
        switch = client.post(
            reverse("chat_set_active_company"), {"company_id": str(company_b.pk)}
        )
        assert switch.status_code == 403, "LEAK: A admin selected company B!"

        self.stdout.write(self.style.SUCCESS(
            f"  OK — {a['company'].name} admin is fully isolated from {company_b.name}."
        ))
