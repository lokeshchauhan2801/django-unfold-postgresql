from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from chat.models import Conversation, Message
from chat.services import ChatProviderError, ChatService
from company.models import Company, CompanyMembership
from docs.models import Document, DocumentChunk


class TestAIProvider:
    model = "test-model"
    last_prompt = ""

    def __init__(self):
        self.chart = None

    def embed_documents(self, texts):
        return [[1.0, 0.0, 1.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 1.0]

    def generate_structured(self, prompt, schema):
        self.last_prompt = prompt
        return schema(
            response="Test response grounded in the retrieved passages.",
            chart=self.chart,
        )


class ChatbotApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alice",
            email="alice@example.com",
            password="secret123",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.provider = TestAIProvider()
        self.provider_patcher = patch(
            "chat.services.get_ai_provider",
            return_value=self.provider,
        )
        self.provider_patcher.start()
        self.addCleanup(self.provider_patcher.stop)

    def test_chat_api_returns_response(self):
        response = self.client.post(
            reverse("chat_api"),
            {"message": "Hello"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"], "Test response grounded in the retrieved passages.")
        self.assertTrue(Conversation.objects.exists())
        self.assertEqual(Message.objects.count(), 2)

    def test_new_conversation_is_assigned_to_the_users_company(self):
        company = Company.objects.create(name="Acme", slug="acme")
        CompanyMembership.objects.create(
            user=self.user,
            company=company,
            role=CompanyMembership.Role.MEMBER,
        )

        response = self.client.post(
            reverse("chat_api"),
            {"message": "Company question"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        conversation = Conversation.objects.get(pk=response.json()["conversation_id"])
        self.assertEqual(conversation.company, company)

    def test_multiple_company_memberships_require_and_apply_selection(self):
        first_company = Company.objects.create(name="Acme", slug="acme")
        second_company = Company.objects.create(name="Globex", slug="globex")
        for company in (first_company, second_company):
            CompanyMembership.objects.create(
                user=self.user,
                company=company,
                role=CompanyMembership.Role.MEMBER,
            )

        blocked = self.client.get(reverse("conversation_list"))
        self.assertEqual(blocked.status_code, 409)

        selected = self.client.post(
            reverse("chat_set_active_company"),
            {"company_id": str(second_company.pk)},
        )
        self.assertEqual(selected.status_code, 200)
        response = self.client.post(
            reverse("chat_api"),
            {"message": "Globex question"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        conversation = Conversation.objects.get(pk=response.json()["conversation_id"])
        self.assertEqual(conversation.company, second_company)

    def test_chat_api_continues_existing_conversation(self):
        first_response = self.client.post(
            reverse("chat_api"),
            {"message": "Hello"},
            content_type="application/json",
        )
        conversation_id = first_response.json()["conversation_id"]

        second_response = self.client.post(
            reverse("chat_api"),
            {"message": "Follow up", "conversation_id": conversation_id},
            content_type="application/json",
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["conversation_id"], conversation_id)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 4)

    def test_chat_api_reuses_the_question_saved_with_an_uploaded_file(self):
        conversation = Conversation.objects.create(user=self.user, title="Education data")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="education.csv",
            file="documents/education.csv",
            file_type="csv",
            status=Document.STATUS_READY,
        )
        question = "Explain this file and create charts"
        attachment_message = Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=question,
        )
        attachment_message.documents.add(document)

        response = self.client.post(
            reverse("chat_api"),
            {
                "message": question,
                "conversation_id": str(conversation.pk),
                "user_message_id": str(attachment_message.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(conversation.messages.count(), 2)
        self.assertEqual(
            list(conversation.messages.values_list("content", flat=True)),
            [question, "Test response grounded in the retrieved passages."],
        )
        self.assertEqual(self.provider.last_prompt.count(f"User: {question}"), 1)

    def test_chat_api_builds_age_chart_from_attached_csv_without_ai_provider(self):
        conversation = Conversation.objects.create(user=self.user, title="People")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="people.csv",
            file=SimpleUploadedFile(
                "people.csv",
                (
                    b"# Sample file metadata\n"
                    b"ID,Age,Country\n"
                    b"1,18,A\n"
                    b"2,18,B\n"
                    b"3,22,A\n"
                ),
                content_type="text/csv",
            ),
            file_type="csv",
            status=Document.STATUS_READY,
            chunk_count=1,
        )
        conversation.documents.add(document)

        response = self.client.post(
            reverse("chat_api"),
            {
                "message": "Create a chart for ages",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(chart["title"], "Distribution of Age")
        self.assertEqual(
            chart["data"],
            [
                {"label": "18", "values": [2.0]},
                {"label": "22", "values": [1.0]},
            ],
        )
        self.assertEqual(self.provider.last_prompt, "")

    def test_chat_api_rejects_questions_while_attached_file_is_processing(self):
        conversation = Conversation.objects.create(user=self.user, title="Processing file")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="report.csv",
            file="documents/report.csv",
            file_type="csv",
            status=Document.STATUS_PROCESSING,
            processing_stage="embedding",
            processing_progress=50,
        )
        attachment = Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content="Attached file: report.csv",
        )
        attachment.documents.add(document)

        response = self.client.post(
            reverse("chat_api"),
            {
                "message": "Summarize this file",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("still processing", response.json()["error"])
        self.assertEqual(conversation.messages.count(), 1)

    def test_conversation_list_is_scoped_to_signed_in_user(self):
        owned = Conversation.objects.create(user=self.user, title="My documents")
        other_user = get_user_model().objects.create_user(username="bob")
        Conversation.objects.create(user=other_user, title="Private conversation")

        response = self.client.get(reverse("conversation_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["conversations"]],
            [str(owned.pk)],
        )

    def test_conversation_detail_returns_messages_and_citations(self):
        conversation = Conversation.objects.create(user=self.user, title="Policy")
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content="See the policy.",
            citations=[{"reference_id": "chunk-uuid", "page": 2}],
        )

        response = self.client.get(
            reverse("conversation_detail", kwargs={"conversation_id": conversation.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["messages"][0]["citations"][0]["reference_id"],
            "chunk-uuid",
        )
        self.assertIsNone(response.json()["messages"][0]["chart_data"])

    def test_chat_api_returns_and_persists_structured_chart_data(self):
        chart = {
            "type": "bar",
            "title": "Revenue by month",
            "x_axis": "Month",
            "y_axis": "Revenue",
            "series": ["Revenue"],
            "data": [
                {"label": "January", "values": [120.0]},
                {"label": "February", "values": [150.0]},
            ],
        }
        self.provider.chart = chart

        response = self.client.post(
            reverse("chat_api"),
            {"message": "Create a bar chart"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chart_data"], chart)
        conversation_id = response.json()["conversation_id"]
        assistant_message = Conversation.objects.get(pk=conversation_id).messages.get(
            role=Message.ROLE_ASSISTANT
        )
        self.assertEqual(assistant_message.chart_data, chart)
        history = self.client.get(
            reverse(
                "conversation_detail",
                kwargs={"conversation_id": conversation_id},
            )
        )
        self.assertEqual(
            history.json()["messages"][1]["chart_data"],
            chart,
        )

    def test_chat_api_rejects_invalid_chart_metrics_from_provider(self):
        self.provider.chart = {
            "type": "pie",
            "title": "Invalid",
            "x_axis": "Category",
            "y_axis": "Value",
            "series": ["Value"],
            "data": [{"label": "A", "values": [-2]}],
        }

        response = self.client.post(
            reverse("chat_api"),
            {"message": "Create a pie chart"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(Conversation.objects.exists())

    def test_chat_page_loads(self):
        response = self.client.get(reverse("chat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="root"')
        self.assertContains(response, "chat-config")
        self.assertContains(response, "chat/chat.js")

    def test_chat_page_offers_login_on_the_same_screen(self):
        response = Client().get(reverse("chat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"authenticated": false')
        self.assertContains(response, "chat/chat.js")

    def test_session_login_authenticates_regular_app_users(self):
        client = Client()
        page = client.get(reverse("chat"))
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("chat_session_login"),
            {"username": "alice", "password": "secret123"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(page.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "alice")
        self.assertIn("_auth_user_id", client.session)

    def test_session_login_accepts_email_address(self):
        client = Client()
        client.get(reverse("chat"))
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("chat_session_login"),
            {"username": "alice@example.com", "password": "secret123"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "alice")
        self.assertIn("_auth_user_id", client.session)

    def test_home_opens_the_chat_workspace(self):
        response = self.client.get("/")
        self.assertRedirects(response, reverse("chat"))

    def test_chat_api_rejects_invalid_json(self):
        response = self.client.post(
            reverse("chat_api"),
            "{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_form_can_post_with_csrf_protection(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
        client.force_login(self.user)
        page = client.get(reverse("chat"))
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("chat_api"),
            {"message": "Hello"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(page.status_code, 200)
        self.assertEqual(response.status_code, 200)

    def test_chat_api_requires_login(self):
        response = Client().post(
            reverse("chat_api"),
            {"message": "Hello"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_chat_api_does_not_allow_another_users_conversation(self):
        other_user = get_user_model().objects.create_user(username="bob")
        conversation = Conversation.objects.create(user=other_user)

        response = self.client.post(
            reverse("chat_api"),
            {
                "message": "Hello",
                "conversation_id": str(conversation.id),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_chat_answers_with_persisted_document_references(self):
        document = Document.objects.create(
            uploaded_by=self.user,
            title="retention.pdf",
            file="documents/retention.pdf",
            status=Document.STATUS_READY,
            chunk_count=1,
        )
        chunk = DocumentChunk.objects.create(
            document=document,
            chunk_index=0,
            page_number=3,
            content="Records must be retained for seven years.",
            source_location="Page 3",
        )
        provider = TestAIProvider()
        conversation = Conversation.objects.create(user=self.user, title="Retention")
        conversation.documents.add(document)
        vector_store = TestVectorStore(chunk)

        assistant_message = ChatService(
            provider=provider,
            vector_store=vector_store,
        ).process_message(
            self.user,
            "How long are records kept?",
            conversation=conversation,
        )

        self.assertIn(str(chunk.pk), provider.last_prompt)
        self.assertIn("location: Page 3", provider.last_prompt)
        self.assertEqual(
            vector_store.last_filter["$and"][1],
            {"document_id": {"$in": [str(document.pk)]}},
        )
        self.assertEqual(
            assistant_message.citations,
            [
                {
                    "reference_id": str(chunk.pk),
                    "document_id": str(document.pk),
                    "filename": "retention.pdf",
                    "page": 3,
                    "source_location": "Page 3",
                    "excerpt": "Records must be retained for seven years.",
                }
            ],
        )
        self.assertEqual(
            Message.objects.get(pk=assistant_message.pk).citations[0]["reference_id"],
            str(chunk.pk),
        )

    @patch(
        "chat.views.ChatService.process_message",
        side_effect=ChatProviderError("provider unavailable"),
    )
    def test_chat_api_reports_provider_failure(self, _process_message):
        response = self.client.post(
            reverse("chat_api"),
            {"message": "Hello"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 502)
        self.assertIn("AI provider", response.json()["error"])

    def test_chat_requires_message_content(self):
        response = self.client.post(
            reverse("chat_api"),
            {"message": "   "},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Message is required", response.json()["error"])


class TestVectorStore:
    last_filter = None

    def __init__(self, chunk):
        self.chunk = chunk

    def similarity_search(self, query_embedding, collection, k=5, filter=None):
        self.last_filter = filter
        return [{"id": str(self.chunk.pk)}]


class ChatAdminRouteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password",
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)

    def test_message_admin_route_loads(self):
        response = self.client.get(reverse("admin:chat_message_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_keeps_admin_navigation(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workspace")


class SessionLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="login-user",
            email="login-user@example.com",
            password="correct-password",
            is_staff=True,
        )

    def test_session_login_accepts_username(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {"username": "login-user", "password": "correct-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "login-user")

    def test_session_login_accepts_email(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {"username": "LOGIN-USER@example.com", "password": "correct-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "login-user")

    def test_shared_login_accepts_username_and_grants_admin_access(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {
                "username": "login-user",
                "password": "correct-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_shared_login_accepts_email_and_grants_admin_access(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {
                "username": "LOGIN-USER@example.com",
                "password": "correct-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_chat_and_admin_use_the_same_authenticated_user(self):
        chat_response = self.client.post(
            reverse("chat_session_login"),
            {"username": "login-user", "password": "correct-password"},
        )
        self.assertEqual(chat_response.status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:index")).status_code,
            200,
        )

    def test_admin_login_redirects_to_the_shared_chat_sign_in_screen(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/chat/?next=%2Fadmin%2F&reauth=1",
        )

    def test_chat_login_returns_the_admin_redirect_for_valid_local_next(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {
                "username": "login-user",
                "password": "correct-password",
                "next": "/admin/",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/admin/")

    def test_chat_login_rejects_external_redirect_urls(self):
        response = self.client.post(
            reverse("chat_session_login"),
            {
                "username": "login-user",
                "password": "correct-password",
                "next": "https://example.com/admin/",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("redirect_url", response.json())


class CompanyChatAdminTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.other_company = Company.objects.create(name="Globex", slug="globex")
        self.company_admin = get_user_model().objects.create_user(
            username="acme-admin",
            email="acme-admin@example.com",
            password="company-admin-password",
        )
        CompanyMembership.objects.create(
            user=self.company_admin,
            company=self.company,
            role=CompanyMembership.Role.ADMIN,
        )
        self.member = get_user_model().objects.create_user(
            username="company-member",
            email="company-member@example.com",
            password="member-password",
        )
        self.company_conversation = Conversation.objects.create(
            user=self.member,
            company=self.company,
            title="Acme support session",
        )
        self.other_conversation = Conversation.objects.create(
            user=self.member,
            company=self.other_company,
            title="Globex private session",
        )

    def test_company_admin_sees_only_their_company_sessions_in_split_view(self):
        client = Client()
        client.force_login(self.company_admin)

        response = client.get(reverse("admin:chat_conversation_sessions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme support session")
        self.assertNotContains(response, "Globex private session")

        visible_detail = client.get(
            reverse(
                "admin:chat_conversation_session_detail",
                kwargs={"conversation_id": self.company_conversation.pk},
            )
        )
        hidden_detail = client.get(
            reverse(
                "admin:chat_conversation_session_detail",
                kwargs={"conversation_id": self.other_conversation.pk},
            )
        )
        self.assertEqual(visible_detail.status_code, 200)
        self.assertEqual(hidden_detail.status_code, 404)

    def test_only_superusers_can_load_chunk_embedding_vectors(self):
        document = Document.objects.create(
            uploaded_by=self.member,
            company=self.company,
            conversation=self.company_conversation,
            title="report.txt",
            file="documents/report.txt",
            file_type="txt",
            status=Document.STATUS_READY,
        )
        chunk = DocumentChunk.objects.create(
            document=document,
            chunk_index=0,
            page_number=1,
            content="A grounded passage.",
        )
        Message.objects.create(
            conversation=self.company_conversation,
            role=Message.ROLE_ASSISTANT,
            content="Here is the answer.",
        )
        detail_url = reverse(
            "admin:chat_conversation_session_detail",
            kwargs={"conversation_id": self.company_conversation.pk},
        )
        embedding_url = reverse(
            "admin:chat_conversation_chunk_embedding",
            kwargs={"chunk_id": chunk.pk},
        )

        company_client = Client()
        company_client.force_login(self.company_admin)
        detail = company_client.get(detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["messages"][0]["content"], "Here is the answer.")
        self.assertEqual(detail.json()["chunks"][0]["content"], "A grounded passage.")
        forbidden = company_client.get(embedding_url)
        self.assertEqual(forbidden.status_code, 403)

        system_admin = get_user_model().objects.create_superuser(
            username="system-admin",
            email="system-admin@example.com",
            password="system-admin-password",
        )
        system_client = Client()
        system_client.force_login(system_admin)
        with patch(
            "chat.admin.ChromaVectorStore.get_embeddings",
            return_value={str(chunk.pk): [0.25, 0.75]},
        ):
            response = system_client.get(embedding_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["embedding"], [0.25, 0.75])
