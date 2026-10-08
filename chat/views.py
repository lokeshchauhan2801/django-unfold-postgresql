import json
import logging
from pathlib import Path
from uuid import UUID

from django.contrib import admin
from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from company.access import (
    active_company_for_request,
    company_options_for_request,
    company_selection_required,
)
from company.models import CompanyMembership
from chat.models import Conversation, Message
from docs.models import Document
from chat.services import (
    ChatProviderError,
    ChatRetrievalError,
    ChatService,
)

logger = logging.getLogger(__name__)


def chat_page(request):
    conversation_placeholder = "00000000-0000-0000-0000-000000000000"
    built_bundle = Path(settings.BASE_DIR) / "static" / "chat" / "chat.js"
    asset_version = built_bundle.stat().st_mtime_ns
    post_login_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        post_login_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        post_login_url = ""
    force_login = request.GET.get("reauth") == "1"
    companies = company_options_for_request(request)
    active_company = (
        active_company_for_request(request) if request.user.is_authenticated else None
    )
    return render(
        request,
        "chatbot/chat.html",
        {
            "chat_asset_version": asset_version,
            "chat_config": {
                "authenticated": request.user.is_authenticated and not force_login,
                "username": request.user.username if request.user.is_authenticated else "",
                "companies": [
                    {"id": str(company["id"]), "name": company["name"]}
                    for company in companies
                ],
                "activeCompanyId": str(active_company.pk) if active_company else "",
                "companySelectionUrl": reverse("chat_set_active_company"),
                "postLoginUrl": post_login_url,
                "loginUrl": reverse("chat_session_login"),
                "logoutUrl": reverse("chat_session_logout"),
                "chatUrl": reverse("chat_api"),
                "conversationsUrl": reverse("conversation_list"),
                "conversationUrl": reverse(
                    "conversation_detail",
                    kwargs={"conversation_id": conversation_placeholder},
                ),
                "conversationPlaceholder": conversation_placeholder,
                "uploadUrl": reverse("document_upload"),
                "documentsUrl": reverse("document_list"),
                "documentReprocessUrl": reverse(
                    "document_reprocess",
                    kwargs={"document_id": "00000000-0000-0000-0000-000000000000"},
                ),
            }
        },
    )


@require_POST
def session_login(request):
    identifier = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    user = authenticate(request, username=identifier, password=password)
    if user is None:
        return JsonResponse({"error": "Username or password is incorrect."}, status=400)

    login(request, user)
    response = {"username": user.username}
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        response["redirect_url"] = next_url
    return JsonResponse(response)


def admin_login_redirect(request):
    if request.user.is_authenticated and admin.site.has_permission(request):
        return redirect("admin:index")
    return redirect(f"{reverse('chat')}?next=%2Fadmin%2F&reauth=1")


@require_POST
def set_active_company(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in before selecting a company."}, status=401)

    company_id = request.POST.get("company_id", "")
    try:
        company_id = UUID(str(company_id))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Choose a valid company."}, status=400)
    membership = CompanyMembership.objects.filter(
        user=request.user,
        company_id=company_id,
        company__is_active=True,
        status=CompanyMembership.Status.ACTIVE,
    ).select_related("company").first()
    if membership is None:
        return JsonResponse({"error": "You are not an active member of that company."}, status=403)

    request.session["active_company_id"] = str(membership.company_id)
    return JsonResponse(
        {
            "company": {
                "id": str(membership.company_id),
                "name": membership.company.name,
            }
        }
    )


def _company_scope_error(request):
    if company_selection_required(request):
        return JsonResponse(
            {"error": "Select a company before accessing company chat data."},
            status=409,
        )
    return None


@require_POST
def session_logout(request):
    logout(request)
    return JsonResponse({"success": True})


@require_GET
def conversation_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view conversations."}, status=401)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)
    conversations = Conversation.objects.filter(
        user=request.user,
        company=company,
    ).order_by("-updated_at")
    return JsonResponse(
        {
            "conversations": [
                {
                    "id": str(conversation.pk),
                    "title": conversation.title,
                    "updated_at": conversation.updated_at.isoformat(),
                    "document_count": conversation.documents.count(),
                }
                for conversation in conversations
            ]
        }
    )


@require_GET
def conversation_detail(request, conversation_id: UUID):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view conversations."}, status=401)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)
    conversation = Conversation.objects.filter(
        pk=conversation_id,
        user=request.user,
        company=company,
    ).first()
    if conversation is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)

    return JsonResponse(
        {
            "id": str(conversation.pk),
            "title": conversation.title,
            "messages": [
                {
                    "id": str(message.pk),
                    "role": message.role,
                    "content": message.content,
                    "citations": message.citations,
                    "chart_data": message.chart_data,
                    "documents": [
                        {
                            "id": str(document.pk),
                            "reference_id": str(document.pk),
                            "title": document.title,
                            "file_type": document.file_type,
                            "content_type": document.content_type,
                            "file_size": document.file_size,
                            "status": document.status,
                            "processing_stage": document.processing_stage,
                            "processing_progress": document.processing_progress,
                            "can_retry": document.status == Document.STATUS_FAILED
                            or (
                                document.status == Document.STATUS_QUEUED
                                and not document.processing_task_id
                            ),
                            "chunk_count": document.chunk_count,
                            "processing_error": document.processing_error,
                            "created_at": document.created_at.isoformat(),
                            "file_url": reverse(
                                "document_file",
                                kwargs={"file_path": document.file.name},
                            ),
                        }
                        for document in message.documents.all()
                    ],
                }
                for message in conversation.messages.all()
            ],
        }
    )


@require_POST
def chat_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in before starting a chat."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"error": "Request body must be a JSON object."}, status=400)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"error": "Message is required."}, status=400)

    conversation = None
    conversation_id = data.get("conversation_id")
    if conversation_id:
        try:
            conversation_uuid = UUID(str(conversation_id))
        except (ValueError, TypeError):
            return JsonResponse({"error": "Conversation not found."}, status=404)

        conversation = Conversation.objects.filter(
            pk=conversation_uuid,
            user=request.user,
            company=company,
        ).first()
        if conversation is None:
            return JsonResponse({"error": "Conversation not found."}, status=404)

    existing_message = None
    existing_message_id = data.get("user_message_id")
    if existing_message_id is not None:
        if conversation is None:
            return JsonResponse(
                {"error": "An existing message requires a conversation."},
                status=400,
            )
        try:
            existing_message_uuid = UUID(str(existing_message_id))
        except (ValueError, TypeError):
            return JsonResponse({"error": "Message not found."}, status=404)
        existing_message = Message.objects.filter(
            pk=existing_message_uuid,
            conversation=conversation,
            role=Message.ROLE_USER,
            content=message.strip(),
            documents__conversation=conversation,
        ).first()
        if existing_message is None:
            return JsonResponse({"error": "Message not found."}, status=404)

    if conversation and conversation.documents.filter(
        status__in=[Document.STATUS_QUEUED, Document.STATUS_PROCESSING],
    ).exists():
        return JsonResponse(
            {
                "error": (
                    "A file in this conversation is still processing. "
                    "Wait until it is ready before asking about its contents."
                )
            },
            status=409,
        )

    try:
        assistant_message = ChatService().process_message(
            request.user,
            message.strip(),
            conversation,
            user_message=existing_message,
            company=company,
        )
    except ChatRetrievalError:
        logger.exception("Document retrieval failed for user %s", request.user.pk)
        return JsonResponse(
            {"error": "Could not search your PDF index. Check the vector database."},
            status=502,
        )
    except ChatProviderError:
        logger.exception("Chat generation failed for user %s", request.user.pk)
        return JsonResponse(
            {
                "error": (
                    "The configured AI provider could not generate a response. "
                    "Check AI_PROVIDER, AI_API_KEY, and AI_BASE_URL."
                )
            },
            status=502,
        )

    return JsonResponse(
        {
            "response": assistant_message.content,
            "conversation_id": str(assistant_message.conversation_id),
            "citations": assistant_message.citations,
            "chart_data": assistant_message.chart_data,
        }
    )
