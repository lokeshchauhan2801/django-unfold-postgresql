import logging
import mimetypes
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from company.access import active_company_for_request, company_selection_required
from chat.models import Conversation, Message
from docs.models import Document, DocumentChunk
from docs.services import SUPPORTED_FILE_TYPES
from docs.tasks import dispatch_document_processing

logger = logging.getLogger(__name__)


def _document_payload(document):
    return {
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


def _queue_document_processing(document):
    try:
        task_id, backend = dispatch_document_processing(str(document.pk))
    except Exception:
        logger.exception("Could not queue document processing for %s", document.pk)
        document.status = Document.STATUS_FAILED
        document.processing_stage = "failed"
        document.processing_progress = 0
        document.processing_error = (
            "Background processing is unavailable. Start Redis and a Celery worker, "
            "then retry this file."
        )
        document.save(
            update_fields=[
                "status",
                "processing_stage",
                "processing_progress",
                "processing_error",
                "updated_at",
            ]
        )
        return False

    document.processing_task_id = task_id
    document.processing_backend = backend
    document.save(
        update_fields=["processing_task_id", "processing_backend", "updated_at"]
    )
    return True


def _message_payload(message):
    return {
        "id": str(message.pk),
        "role": message.role,
        "content": message.content,
        "citations": message.citations,
        "chart_data": message.chart_data,
        "documents": [
            _document_payload(document)
            for document in message.documents.all()
        ],
    }


@require_POST
def upload_document(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in before uploading documents."}, status=401)
    if company_selection_required(request):
        return JsonResponse(
            {"error": "Select a company before uploading a document."},
            status=409,
        )
    company = active_company_for_request(request)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse(
            {
                "error": (
                    "Choose a supported file: PDF, DOCX, TXT, MD, CSV, XLSX, or JSON."
                )
            },
            status=400,
        )

    file_type = Path(uploaded_file.name).suffix.lower()
    content_type = SUPPORTED_FILE_TYPES.get(file_type)
    if content_type is None:
        return JsonResponse(
            {
                "error": (
                    "Supported files are PDF, DOCX, TXT, MD, CSV, XLSX, and JSON."
                )
            },
            status=400,
        )

    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if uploaded_file.size > max_size:
        return JsonResponse(
            {
                "error": (
                    f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
                )
            },
            status=413,
        )

    signature = uploaded_file.read(5)
    if file_type == ".pdf" and signature != b"%PDF-":
        return JsonResponse({"error": "The uploaded file is not a valid PDF."}, status=400)
    if file_type in {".docx", ".xlsx"} and not signature.startswith(b"PK"):
        return JsonResponse(
            {"error": "The uploaded file is not a valid Office document."},
            status=400,
        )
    uploaded_file.seek(0)

    conversation_id = request.POST.get("conversation_id")
    conversation = None
    if conversation_id:
        try:
            conversation_uuid = UUID(conversation_id)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Conversation not found."}, status=404)
        conversation = Conversation.objects.filter(
            pk=conversation_uuid,
            user=request.user,
            company=company,
        ).first()
        if conversation is None:
            return JsonResponse({"error": "Conversation not found."}, status=404)
    else:
        title = request.POST.get("message", "").strip() or uploaded_file.name
        conversation = Conversation.objects.create(
            user=request.user,
            title=title[:200],
            company=company,
        )

    document = Document.objects.create(
        uploaded_by=request.user,
        company=company,
        conversation=conversation,
        title=uploaded_file.name,
        file=uploaded_file,
        file_type=file_type[1:],
        content_type=content_type,
        file_size=uploaded_file.size,
        status=Document.STATUS_QUEUED,
        processing_stage="queued",
        processing_backend="celery",
    )
    message = Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content=(
            request.POST.get("message", "").strip()
            or f"Attached file: {document.title}"
        ),
        model_name="user",
    )
    message.documents.add(document)
    conversation.save(update_fields=["updated_at"])
    queued = _queue_document_processing(document)
    document.refresh_from_db()

    payload = {
        "document": _document_payload(document),
        "conversation_id": str(conversation.pk),
        "message": _message_payload(message),
    }
    if not queued:
        payload["error"] = document.processing_error
        return JsonResponse(payload, status=503)
    return JsonResponse(payload, status=202)


@require_POST
def reprocess_document(request, document_id: UUID):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in before retrying document processing."}, status=401)

    document = get_object_or_404(
        Document,
        pk=document_id,
        uploaded_by=request.user,
    )
    retryable = document.status == Document.STATUS_FAILED or (
        document.status == Document.STATUS_QUEUED
        and not document.processing_task_id
    )
    if not retryable:
        return JsonResponse(
            {"error": "Only failed or unqueued documents can be reprocessed."},
            status=409,
        )

    # Remove any stale chunks left over from the previous failed attempt so the
    # worker can run bulk_create cleanly without hitting the unique constraint.
    DocumentChunk.objects.filter(document=document).delete()

    document.status = Document.STATUS_QUEUED
    document.processing_stage = "queued"
    document.processing_progress = 0
    document.processing_error = ""
    document.processing_task_id = ""
    document.save(
        update_fields=[
            "status",
            "processing_stage",
            "processing_progress",
            "processing_error",
            "processing_task_id",
            "updated_at",
        ]
    )
    if not _queue_document_processing(document):
        document.refresh_from_db()
        return JsonResponse(
            {
                "error": document.processing_error,
                "document": _document_payload(document),
            },
            status=503,
        )
    document.refresh_from_db()
    return JsonResponse({"document": _document_payload(document)}, status=202)


@require_GET
def document_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to view your documents."}, status=401)

    if company_selection_required(request):
        return JsonResponse(
            {"error": "Select a company before viewing documents."},
            status=409,
        )
    company = active_company_for_request(request)
    documents = (
        Document.objects.filter(company=company)
        if company
        else Document.objects.filter(uploaded_by=request.user, company__isnull=True)
    )
    return JsonResponse(
        {"documents": [_document_payload(document) for document in documents]}
    )


@require_GET
def document_file(request, file_path):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to access this document."}, status=401)

    if company_selection_required(request):
        return JsonResponse(
            {"error": "Select a company before accessing company files."},
            status=409,
        )
    company = active_company_for_request(request)
    document_query = Document.objects.filter(file=file_path)
    if company:
        document_query = document_query.filter(company=company)
    else:
        document_query = document_query.filter(
            uploaded_by=request.user,
            company__isnull=True,
        )
    document = get_object_or_404(document_query)
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=Path(document.title).name,
        content_type=mimetypes.guess_type(document.title)[0]
        or "application/octet-stream",
    )
