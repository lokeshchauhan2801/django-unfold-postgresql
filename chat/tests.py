from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from chat.models import Conversation, Message
from chat.services import ChatProviderError, ChatService
from company.models import Company, CompanyMembership
from docs.models import Document, DocumentChunk


class _EmptyVectorStore:
    """Vector store stub that returns no matches (deterministic API tests)."""

    def similarity_search(self, query_embedding, collection, k=5, filter=None):
        return []


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
        # Keep document retrieval deterministic in API tests: return no vector
        # matches so the LLM path runs without a live Chroma backend. Tests that
        # exercise retrieval use ChatService(vector_store=...) directly instead.
        self.vector_store_patcher = patch(
            "chat.services.ChromaVectorStore",
            return_value=_EmptyVectorStore(),
        )
        self.vector_store_patcher.start()
        self.addCleanup(self.vector_store_patcher.stop)

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
        # The LLM is always consulted first; the deterministic CSV chart is a
        # fallback used because the stub provider returned no chart.
        self.assertNotEqual(self.provider.last_prompt, "")

    def test_chat_api_auto_selects_pie_chart_without_a_named_column(self):
        conversation = Conversation.objects.create(user=self.user, title="Sales")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="sales.csv",
            file=SimpleUploadedFile(
                "sales.csv",
                (
                    b"# Sample sales export\n"
                    b"Date,Product,Category,Channel,Units\n"
                    b"2024-01-01,Phone,Mobile,Online,10\n"
                    b"2024-01-02,Laptop,Computers,Retail,5\n"
                    b"2024-01-03,Case,Accessories,Online,8\n"
                    b"2024-01-04,Tablet,Mobile,Partner,3\n"
                    b"2024-01-05,Monitor,Computers,Retail,2\n"
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
                "message": "create a pie chart from this csv",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        self.assertEqual(chart["type"], "pie")
        self.assertEqual(len(chart["series"]), 1)
        # A categorical column (not the all-unique Date column) must be chosen,
        # and every slice must carry a positive count.
        self.assertGreaterEqual(len(chart["data"]), 2)
        self.assertTrue(all(point["values"][0] > 0 for point in chart["data"]))
        self.assertTrue(all(point["label"] for point in chart["data"]))
        # The LLM is consulted first; the deterministic pie chart is the
        # fallback used when the provider returns no chart of its own.
        self.assertNotEqual(self.provider.last_prompt, "")

    def test_chat_api_prefers_llm_chart_over_local_csv_fallback(self):
        # When the LLM returns its own chart (e.g. grounded in the request's
        # subject), it must be used instead of the generic local distribution.
        self.provider.chart = {
            "type": "pie",
            "title": "Accessories by channel",
            "x_axis": "Channel",
            "y_axis": "Units",
            "series": ["Units"],
            "data": [
                {"label": "Online", "values": [8.0]},
                {"label": "Retail", "values": [4.0]},
            ],
        }
        conversation = Conversation.objects.create(user=self.user, title="Sales")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="sales.csv",
            file=SimpleUploadedFile(
                "sales.csv",
                (
                    b"Date,Product,Category,Channel,Units\n"
                    b"2024-01-01,Phone,Mobile,Online,10\n"
                    b"2024-01-03,Case,Accessories,Online,8\n"
                    b"2024-01-04,Strap,Accessories,Retail,4\n"
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
                "message": "create chart related to accessories",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        self.assertEqual(chart["title"], "Accessories by channel")
        self.assertEqual(
            chart["data"],
            [
                {"label": "Online", "values": [8.0]},
                {"label": "Retail", "values": [4.0]},
            ],
        )
        self.assertNotEqual(self.provider.last_prompt, "")

    def test_chat_api_uses_file_attached_earlier_in_the_session(self):
        # Requirement: a media file stays referenced for the whole session, so
        # a later message (without re-attaching) still resolves it.
        conversation = Conversation.objects.create(user=self.user, title="Sales")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="sales.csv",
            file=SimpleUploadedFile(
                "sales.csv",
                (
                    b"Category,Channel\n"
                    b"Mobile,Online\n"
                    b"Accessories,Retail\n"
                    b"Accessories,Online\n"
                ),
                content_type="text/csv",
            ),
            file_type="csv",
            status=Document.STATUS_READY,
            chunk_count=1,
        )
        conversation.documents.add(document)
        # An earlier, unrelated exchange in the same session.
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content="hello",
            model_name="user",
        )

        # A later chart request that does NOT re-attach the file.
        response = self.client.post(
            reverse("chat_api"),
            {
                "message": "now show a chart",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        # The session's CSV was still resolved and charted via the fallback.
        self.assertIsNotNone(chart)
        self.assertGreaterEqual(len(chart["data"]), 1)

    def test_chat_api_charts_an_arbitrary_csv_shape_without_hardcoding(self):
        # A completely different CSV (semicolon-delimited, unrelated columns)
        # must still produce a chart from whatever columns it actually has.
        conversation = Conversation.objects.create(user=self.user, title="Weather")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="weather.csv",
            file=SimpleUploadedFile(
                "weather.csv",
                (
                    b"City;Condition;TempC\n"
                    b"Oslo;Snow;-3\n"
                    b"Cairo;Sunny;31\n"
                    b"Lima;Cloudy;19\n"
                    b"Delhi;Sunny;34\n"
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
                "message": "visualize this as a chart",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        self.assertIsNotNone(chart)
        # Title/axis come from the file's own headers, not hardcoded names.
        self.assertTrue(chart["x_axis"] in {"City", "Condition", "TempC"})
        self.assertGreaterEqual(len(chart["data"]), 1)

    def test_chat_api_falls_back_to_local_chart_when_provider_fails(self):
        # Reproduces the reported bug: a chart worked, then a follow-up chart
        # request 502'd because the LLM call failed. With a CSV in the session
        # the deterministic fallback must still answer instead of hard-failing.
        def boom(prompt, schema):
            self.provider.last_prompt = prompt
            raise RuntimeError("provider unavailable")

        self.provider.generate_structured = boom

        conversation = Conversation.objects.create(user=self.user, title="Sales")
        document = Document.objects.create(
            uploaded_by=self.user,
            conversation=conversation,
            title="sales.csv",
            file=SimpleUploadedFile(
                "sales.csv",
                (
                    b"Category,Channel\n"
                    b"Mobile,Online\n"
                    b"Computers,Retail\n"
                    b"Computers,Online\n"
                    b"Accessories,Online\n"
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
                "message": "bar chart computers",
                "conversation_id": str(conversation.pk),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        chart = response.json()["chart_data"]
        self.assertIsNotNone(chart)
        self.assertGreaterEqual(len(chart["data"]), 1)

    def test_chat_api_still_errors_when_provider_fails_and_no_fallback(self):
        # A non-chart request with no usable fallback must still surface 502.
        def boom(prompt, schema):
            raise RuntimeError("provider unavailable")

        self.provider.generate_structured = boom

        response = self.client.post(
            reverse("chat_api"),
            {"message": "summarize the policy"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("AI provider", response.json()["error"])

    def test_prompt_includes_whole_chat_context_for_long_conversations(self):
        # The LLM must keep a reference to the entire chat: an early message
        # (beyond the recent verbatim window) should still appear via the
        # earlier-conversation digest, alongside recent turns.
        conversation = Conversation.objects.create(user=self.user, title="Long chat")
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content="EARLY_MARKER remember my favourite colour is teal",
            model_name="user",
        )
        for i in range(40):
            Message.objects.create(
                conversation=conversation,
                role=Message.ROLE_ASSISTANT if i % 2 else Message.ROLE_USER,
                content=f"filler message number {i}",
            )
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content="RECENT_MARKER what did I say earlier",
            model_name="user",
        )

        self.client.post(
            reverse("chat_api"),
            {"message": "remind me", "conversation_id": str(conversation.pk)},
            content_type="application/json",
        )

        prompt = self.provider.last_prompt
        self.assertIn("earlier conversation digest", prompt)
        self.assertIn("EARLY_MARKER", prompt)   # old turn preserved via digest
        self.assertIn("RECENT_MARKER", prompt)  # recent turn verbatim

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

    def test_new_chat_view_loads_for_superuser(self):
        response = self.client.get(reverse("admin:chat_conversation_new"))
        self.assertEqual(response.status_code, 200)
        # The admin page hosts the chat as an iframe in its right content panel
        # so the admin left menu and layout stay intact.
        self.assertContains(response, "<iframe")
        self.assertContains(response, reverse("chat_embedded"))

    def test_new_chat_view_loads_for_company_admin_without_staff(self):
        from company.models import Company, CompanyMembership

        company_admin = get_user_model().objects.create_user(
            username="company-admin",
            email="company-admin@example.com",
            password="Company-admin-password-123",
        )
        company = Company.objects.create(name="Acme", slug="acme")
        CompanyMembership.objects.create(
            user=company_admin,
            company=company,
            role=CompanyMembership.Role.ADMIN,
        )
        client = Client(HTTP_HOST="localhost")
        client.force_login(company_admin)

        response = client.get(reverse("admin:chat_conversation_new"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<iframe")
        self.assertContains(response, reverse("chat_embedded"))

    def test_new_chat_view_denies_anonymous(self):
        response = Client(HTTP_HOST="localhost").get(
            reverse("admin:chat_conversation_new")
        )
        # Admin redirects unauthenticated users to the login flow.
        self.assertEqual(response.status_code, 302)

    def test_new_chat_view_denies_plain_member(self):
        from company.models import Company, CompanyMembership

        member = get_user_model().objects.create_user(
            username="plain-member",
            email="plain-member@example.com",
            password="Plain-member-password-123",
        )
        company = Company.objects.create(name="Globex", slug="globex")
        CompanyMembership.objects.create(
            user=member,
            company=company,
            role=CompanyMembership.Role.MEMBER,
        )
        client = Client(HTTP_HOST="localhost")
        client.force_login(member)

        response = client.get(reverse("admin:chat_conversation_new"))

        # Non-admin members are not allowed into the admin portal.
        self.assertEqual(response.status_code, 302)

    def test_embedded_chat_preselects_conversation_from_query_param(self):
        from chat.models import Conversation

        conversation = Conversation.objects.create(
            user=self.user, title="History item", company=None
        )
        response = self.client.get(
            reverse("chat_embedded") + f"?conversation={conversation.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'"initialConversationId": "{conversation.pk}"')

    def test_embedded_chat_ignores_foreign_conversation_param(self):
        from chat.models import Conversation

        other = get_user_model().objects.create_user(username="eve")
        conversation = Conversation.objects.create(
            user=other, title="Not yours", company=None
        )
        response = self.client.get(
            reverse("chat_embedded") + f"?conversation={conversation.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"initialConversationId": ""')

    def test_admin_sidebar_shows_chat_history_titles(self):
        from chat.models import Conversation

        conversation = Conversation.objects.create(
            user=self.user, title="My analytics chat", company=None
        )
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My analytics chat")
        self.assertContains(
            response,
            reverse("admin:chat_conversation_new") + f"?conversation={conversation.pk}",
        )

    def test_embedded_chat_page_mounts_react_and_allows_sameorigin_framing(self):
        response = self.client.get(reverse("chat_embedded"))
        self.assertEqual(response.status_code, 200)
        # The embedded page mounts the React chat and carries its config.
        self.assertContains(response, 'id="root"')
        self.assertContains(response, 'id="chat-config"')
        self.assertContains(response, '"embedded": true')
        # Must be framable same-origin so the admin iframe can load it.
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_public_chat_page_still_denies_framing(self):
        # The public chat page keeps clickjacking protection (default DENY).
        response = self.client.get(reverse("chat"))
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_admin_dashboard_keeps_admin_navigation(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        # The admin left navigation renders with the Dashboard group and the
        # integrated chat entries (New chat + the session browser).
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "New chat")
        self.assertContains(response, reverse("admin:chat_conversation_new"))


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
