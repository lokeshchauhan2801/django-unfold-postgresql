import logging

from django.contrib import admin
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import path
from unfold.admin import ModelAdmin

from basics.admin import AuditAdminMixin, CompanyScopedAdminMixin
from docs.models import Document, DocumentChunk
from infrastructure.vectorstore.chroma_backend import ChromaVectorStore

from .models import Conversation, Message, MessageVersion

logger = logging.getLogger(__name__)


@admin.register(Conversation)
class ConversationAdmin(CompanyScopedAdminMixin, AuditAdminMixin, ModelAdmin):
    list_display = ("title", "user", "company", "created_at", "updated_at")
    list_filter = ("company", "created_at")
    search_fields = ("title", "user__email")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
    date_hierarchy = "created_at"

    def get_urls(self):
        custom_urls = [
            path(
                "sessions/",
                self.admin_site.admin_view(self.session_browser_view),
                name="chat_conversation_sessions",
            ),
            path(
                "sessions/<uuid:conversation_id>/",
                self.admin_site.admin_view(self.session_detail_view),
                name="chat_conversation_session_detail",
            ),
            path(
                "chunks/<uuid:chunk_id>/embedding/",
                self.admin_site.admin_view(self.chunk_embedding_view),
                name="chat_conversation_chunk_embedding",
            ),
        ]
        return custom_urls + super().get_urls()

    def session_browser_view(self, request):
        return render(
            request,
            "admin/chat/conversation/session_browser.html",
            {
                **self.admin_site.each_context(request),
                "title": "Company chat sessions",
                "opts": self.model._meta,
                "conversations": self.get_queryset(request).select_related(
                    "user", "company"
                ),
                "can_view_embeddings": request.user.is_superuser,
            },
        )

    def session_detail_view(self, request, conversation_id):
        conversation = self.get_queryset(request).filter(pk=conversation_id).first()
        if conversation is None:
            raise Http404("Chat session not found.")

        documents = Document.objects.filter(
            Q(conversation=conversation)
            | Q(messages__conversation=conversation)
        ).distinct()
        chunks = DocumentChunk.objects.filter(document__in=documents).select_related(
            "document"
        )
        return JsonResponse(
            {
                "title": conversation.title,
                "company": conversation.company.name if conversation.company else "",
                "user": str(conversation.user) if conversation.user else "",
                "messages": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "documents": [
                            {"id": str(document.pk), "title": document.title}
                            for document in message.documents.all()
                        ],
                    }
                    for message in conversation.messages.prefetch_related(
                        "documents"
                    ).all()
                ],
                "chunks": [
                    {
                        "id": str(chunk.pk),
                        "document": chunk.document.title,
                        "index": chunk.chunk_index,
                        "location": chunk.source_location or f"page {chunk.page_number}",
                        "content": chunk.content,
                    }
                    for chunk in chunks
                ],
                "can_view_embeddings": request.user.is_superuser,
            }
        )

    def chunk_embedding_view(self, request, chunk_id):
        if not request.user.is_superuser:
            return JsonResponse(
                {"error": "Only system administrators can view embedding vectors."},
                status=403,
            )

        visible_conversations = self.get_queryset(request).values("pk")
        chunk = DocumentChunk.objects.filter(
            pk=chunk_id,
        ).filter(
            Q(document__conversation__in=visible_conversations)
            | Q(document__messages__conversation__in=visible_conversations)
        ).first()
        if chunk is None:
            raise Http404("Chunk not found.")

        try:
            embeddings = ChromaVectorStore().get_embeddings(
                [str(chunk.pk)],
                collection="pdf_chunks",
            )
        except Exception:
            logger.exception("Could not load embedding for document chunk %s", chunk.pk)
            return JsonResponse(
                {"error": "Could not load the embedding from the vector database."},
                status=503,
            )
        return JsonResponse({"embedding": embeddings.get(str(chunk.pk))})


@admin.register(Message)
class MessageAdmin(CompanyScopedAdminMixin, ModelAdmin):
    list_display = ("conversation", "role", "content_preview", "has_chart", "model_name", "created_at")
    list_filter = ("role", "model_name", "created_at")
    search_fields = ("content", "conversation__title")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("conversation", "parent")

    def content_preview(self, obj):
        return obj.content[:60]

    content_preview.short_description = "Content"

    @admin.display(boolean=True, description="Chart")
    def has_chart(self, obj):
        return bool(obj.chart_data)


@admin.register(MessageVersion)
class MessageVersionAdmin(CompanyScopedAdminMixin, ModelAdmin):
    list_display = ("message", "version", "created_at")
    list_filter = ("version",)
    readonly_fields = ("id", "created_at")
