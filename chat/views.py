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
from django.views.decorators.clickjacking import xframe_options_sameorigin

from company.access import (
    active_companies_for_user,
    active_company_for_request,
    company_metadata,
    company_options_for_request,
    company_permissions,
    company_selection_required,
    effective_role_label,
    is_company_admin,
    scoped_conversations,
    scoped_documents,
    scoped_members,
)
from chat.models import Conversation, Message
from docs.models import Document
from chat.services import (
    ChatProviderError,
    ChatRetrievalError,
    ChatService,
)

logger = logging.getLogger(__name__)


def build_chat_config(
    request,
    *,
    force_login=False,
    post_login_url="",
    embedded=False,
    initial_conversation_id="",
):
    """Build the React chat bootstrap config.

    Shared by the public chat page and the in-admin "New chat" workspace so
    both reuse the same company-scoped API endpoints and session logic. The
    chat data a user can reach is always restricted to their active company
    (superusers included, via the active-company selection), which keeps a
    company admin confined to their own company's conversations.

    When ``embedded`` is true the React app hides its own sidebar and fills its
    host container instead of the whole viewport, so it renders as the right
    panel inside the admin shell (the admin's left menu stays visible).

    ``initial_conversation_id`` preselects a conversation to open on load (used
    by the admin chat-history sidebar links).
    """

    conversation_placeholder = "00000000-0000-0000-0000-000000000000"
    companies = company_options_for_request(request)
    active_company = (
        active_company_for_request(request) if request.user.is_authenticated else None
    )

    def _logo_url(logo):
        if not logo:
            return ""
        try:
            from django.core.files.storage import default_storage

            return default_storage.url(str(logo))
        except Exception:
            return ""

    company_list = [
        {
            "id": str(company["id"]),
            "name": company["name"],
            "slug": company.get("slug", ""),
            "logo_url": _logo_url(company.get("logo")),
        }
        for company in companies
    ]

    return {
        "embedded": embedded,
        "initialConversationId": str(initial_conversation_id or ""),
        "authenticated": request.user.is_authenticated and not force_login,
        "username": request.user.username if request.user.is_authenticated else "",
        "companies": company_list,
        "activeCompanyId": str(active_company.pk) if active_company else "",
        "activeCompany": company_metadata(active_company),
        "role": (
            effective_role_label(request.user, active_company)
            if request.user.is_authenticated
            else "member"
        ),
        "permissions": (
            company_permissions(request.user, active_company)
            if request.user.is_authenticated
            else {}
        ),
        "companySelectionUrl": reverse("chat_set_active_company"),
        "companyMetaUrl": reverse("chat_company_meta"),
        "membersUrl": reverse("company_members"),
        "dashboardUrl": reverse("company_dashboard"),
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
        "libraryUploadUrl": reverse("document_library_upload"),
        "documentsUrl": reverse("document_list"),
        "documentReprocessUrl": reverse(
            "document_reprocess",
            kwargs={"document_id": "00000000-0000-0000-0000-000000000000"},
        ),
        "documentProcessUrl": reverse(
            "document_process",
            kwargs={"document_id": "00000000-0000-0000-0000-000000000000"},
        ),
    }


def chat_asset_version():
    built_bundle = Path(settings.BASE_DIR) / "static" / "chat" / "chat.js"
    return built_bundle.stat().st_mtime_ns


def chat_page(request):
    post_login_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        post_login_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        post_login_url = ""
    force_login = request.GET.get("reauth") == "1"
    return render(
        request,
        "chatbot/chat.html",
        {
            "chat_asset_version": chat_asset_version(),
            "chat_config": build_chat_config(
                request,
                force_login=force_login,
                post_login_url=post_login_url,
            ),
        },
    )


@xframe_options_sameorigin
def embedded_chat_page(request):
    """Standalone chat page rendered for same-origin framing in the admin.

    The admin "New chat" view embeds this page in an iframe so the chat UI
    fills the admin's right content panel while the admin's own left menu and
    layout stay untouched. Rendering inside an iframe fully isolates the chat
    bundle's global CSS (Tailwind preflight) from the admin shell.

    A ``conversation`` query param preselects a conversation to open (used by
    the admin chat-history sidebar). It is validated against the signed-in
    user's company-scoped conversations before being passed to the client.
    """

    initial_conversation_id = ""
    requested = request.GET.get("conversation", "")
    if requested and request.user.is_authenticated:
        try:
            requested_uuid = UUID(str(requested))
        except (TypeError, ValueError):
            requested_uuid = None
        if requested_uuid is not None:
            company = active_company_for_request(request)
            if Conversation.objects.filter(
                pk=requested_uuid,
                user=request.user,
                company=company,
            ).exists():
                initial_conversation_id = str(requested_uuid)

    return render(
        request,
        "chatbot/chat.html",
        {
            "chat_asset_version": chat_asset_version(),
            "chat_config": build_chat_config(
                request,
                embedded=True,
                initial_conversation_id=initial_conversation_id,
            ),
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

    # Validate against the set of companies the user may open. Superusers may
    # open any active company (even without a membership); everyone else is
    # restricted to companies where they hold an active membership. This is the
    # single tenant-isolation gate for company switching.
    company = active_companies_for_user(request.user).filter(pk=company_id).first()
    if company is None:
        return JsonResponse(
            {"error": "You are not an active member of that company."}, status=403
        )

    request.session["active_company_id"] = str(company.pk)
    return JsonResponse(
        {
            "company": company_metadata(company),
            "role": effective_role_label(request.user, company),
            "permissions": company_permissions(request.user, company),
        }
    )


@require_GET
def company_meta(request):
    """Return the active company's name/logo, the signed-in user's role, and
    permission flags. The frontend calls this after switching companies and on
    load so the header/sidebar reflect the current tenant.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view company details."}, status=401)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)
    return JsonResponse(
        {
            "company": company_metadata(company),
            "role": effective_role_label(request.user, company),
            "permissions": company_permissions(request.user, company),
        }
    )


@require_GET
def company_members(request):
    """List the active company's members — company admins/owners and system
    admins only. Enforced on the backend via ``scoped_members``.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view members."}, status=401)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)
    if company is None or not is_company_admin(request.user, company):
        return JsonResponse(
            {"error": "Only company administrators can view the member list."},
            status=403,
        )

    members = scoped_members(request.user, company)
    return JsonResponse(
        {
            "members": [
                {
                    "id": str(membership.pk),
                    "username": membership.user.username,
                    "email": membership.user.email,
                    "role": membership.role,
                    "status": membership.status,
                    "joined_at": membership.joined_at.isoformat(),
                }
                for membership in members
            ]
        }
    )


@require_GET
def company_dashboard(request):
    """Return aggregate counts for the active company's dashboard.

    Scoped exactly like the list endpoints: admins see company-wide totals,
    regular members see only their own conversations/documents.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view the dashboard."}, status=401)

    scope_error = _company_scope_error(request)
    if scope_error:
        return scope_error
    company = active_company_for_request(request)
    if company is None:
        return JsonResponse(
            {"error": "Select a company before viewing the dashboard."},
            status=409,
        )

    conversations = scoped_conversations(request.user, company)
    documents = scoped_documents(request.user, company)
    admin = is_company_admin(request.user, company)

    stats = {
        "conversation_count": conversations.count(),
        "document_count": documents.count(),
        "ready_document_count": documents.filter(status=Document.STATUS_READY).count(),
        "processing_document_count": documents.filter(
            status__in=[Document.STATUS_QUEUED, Document.STATUS_PROCESSING]
        ).count(),
        "message_count": Message.objects.filter(
            conversation__in=conversations
        ).count(),
    }
    if admin:
        stats["member_count"] = scoped_members(request.user, company).count()

    recent_conversations = [
        {
            "id": str(conversation.pk),
            "title": conversation.title,
            "owner": conversation.user.username if conversation.user else "",
            "updated_at": conversation.updated_at.isoformat(),
        }
        for conversation in conversations.select_related("user").order_by(
            "-updated_at"
        )[:5]
    ]

    return JsonResponse(
        {
            "company": company_metadata(company),
            "role": effective_role_label(request.user, company),
            "permissions": company_permissions(request.user, company),
            "stats": stats,
            "recent_conversations": recent_conversations,
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
    conversations = (
        scoped_conversations(request.user, company)
        .select_related("user")
        .order_by("-updated_at")
    )
    return JsonResponse(
        {
            "conversations": [
                {
                    "id": str(conversation.pk),
                    "title": conversation.title,
                    "owner": conversation.user.username if conversation.user else "",
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
    conversation = (
        scoped_conversations(request.user, company)
        .filter(pk=conversation_id)
        .first()
    )
    if conversation is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)

    return JsonResponse(
        {
            "id": str(conversation.pk),
            "title": conversation.title,
            "owner": conversation.user.username if conversation.user else "",
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
