import json
import logging
from pathlib import Path
from uuid import UUID

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.chat.models import Conversation, Message
from apps.documents.models import Document
from apps.chat.services import (
    ChatProviderError,
    ChatRetrievalError,
    ChatService,
)

logger = logging.getLogger(__name__)


def chat_page(request):
    conversation_placeholder = "00000000-0000-0000-0000-000000000000"
    built_bundle = Path(settings.BASE_DIR) / "static" / "chat" / "chat.js"
    asset_version = built_bundle.stat().st_mtime_ns
    return render(
        request,
        "chatbot/chat.html",
        {
            "chat_asset_version": asset_version,
            "chat_config": {
                "authenticated": request.user.is_authenticated,
                "username": request.user.get_username() if request.user.is_authenticated else "",
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
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "Username or password is incorrect."}, status=400)

    login(request, user)
    return JsonResponse({"username": user.get_username()})


@require_POST
def session_logout(request):
    logout(request)
    return JsonResponse({"success": True})


@require_GET
def conversation_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view conversations."}, status=401)

    conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")
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

    conversation = Conversation.objects.filter(
        pk=conversation_id,
        user=request.user,
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
