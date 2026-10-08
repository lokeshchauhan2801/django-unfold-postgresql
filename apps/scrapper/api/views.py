from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.basics.mixins import CompanyFilterMixin
from apps.scrapper.models import Document, DocumentChunk, QueueMessage
from apps.scrapper.services import create_document_from_file, create_document_from_url

from .serializers import (
    DocumentChunkSerializer,
    DocumentCreateSerializer,
    DocumentSerializer,
    QueueMessageSerializer,
)


class DocumentViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    """
    CRUD + custom actions for scrapper Documents.
    Endpoint: api/v1/scrapper/documents/
    """

    queryset = Document.objects.select_related("company", "created_by").order_by("-created_at")
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [SearchFilter]
    search_fields = ["title"]

    def get_serializer_class(self):
        if self.action in ("create",):
            return DocumentCreateSerializer
        return DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        company_id = data.get("company").pk if data.get("company") else None

        if data.get("file"):
            doc = create_document_from_file(
                uploaded_file=data["file"],
                company_id=company_id,
                created_by=request.user,
                title=data.get("title"),
            )
        else:
            doc = create_document_from_url(
                url=data["source_url"],
                company_id=company_id,
                created_by=request.user,
                title=data.get("title"),
            )

        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="process")
    def process_now(self, request, pk=None):
        """Re-trigger processing for a document."""
        doc = self.get_object()
        from apps.scrapper.tasks import process_scrapper_document

        process_scrapper_document.delay(str(doc.id))
        return Response({"detail": "Processing triggered."})

    @action(detail=True, methods=["get"], url_path="chunks")
    def chunks(self, request, pk=None):
        """List chunks for a document."""
        doc = self.get_object()
        qs = doc.chunks.all()
        serializer = DocumentChunkSerializer(qs, many=True)
        return Response(serializer.data)


class DocumentChunkViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for DocumentChunks.
    Endpoint: api/v1/scrapper/document-chunks/
    """

    queryset = DocumentChunk.objects.select_related("document").order_by("document", "chunk_index")
    serializer_class = DocumentChunkSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ["document__title", "content"]


class QueueMessageViewSet(CompanyFilterMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for QueueMessages.
    Endpoint: api/v1/scrapper/queue-messages/
    """

    queryset = QueueMessage.objects.select_related("document", "company").order_by("-created_at")
    serializer_class = QueueMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
