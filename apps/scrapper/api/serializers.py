from rest_framework import serializers

from apps.scrapper.models import Document, DocumentChunk, QueueMessage


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = ("id", "chunk_index", "page_number", "source_location", "content", "created_at")
        read_only_fields = ("id", "created_at")


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "document_type",
            "status",
            "chunk_count",
            "file",
            "source_url",
            "file_size",
            "content_type",
            "company",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "chunk_count",
            "file_size",
            "content_type",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Used for POST — accepts either file or source_url."""

    class Meta:
        model = Document
        fields = ("title", "document_type", "file", "source_url", "company")

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("source_url"):
            raise serializers.ValidationError("Provide either a file or a source URL.")
        return attrs


class QueueMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueueMessage
        fields = (
            "id",
            "document",
            "task_id",
            "status",
            "progress",
            "stage",
            "error",
            "company",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "task_id", "created_at", "created_by")
