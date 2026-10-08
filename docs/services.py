from __future__ import annotations

import csv
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import TextIOWrapper
from pathlib import Path

from django.db import transaction
from docx import Document as WordDocument
from openpyxl import load_workbook
from pypdf import PdfReader

from ai.providers import get_ai_provider
from docs.models import Document, DocumentChunk
from infrastructure.vectorstore.chroma_backend import ChromaVectorStore

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
TABLE_CHUNK_SIZE = 9_000
EMBEDDING_BATCH_SIZE = 96
EMBEDDING_WORKERS = 4
VECTOR_BATCH_SIZE = 100
MAX_DOCUMENT_CHUNKS = 10_000
SUPPORTED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
}


class DocumentValidationError(Exception):
    """Raised when an uploaded document cannot be converted into searchable text."""


class DocumentIndexError(Exception):
    """Raised when a document cannot be embedded and written to vector storage."""


def split_page_text(text: str, page_number: int) -> list[tuple[int, str]]:
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary
        content = normalized[start:end].strip()
        if content:
            chunks.append((page_number, content))
        if end >= len(normalized):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _labelled_chunks(text: str, page_number: int, label: str) -> list[tuple[int, str, str]]:
    return [
        (page, f"{label} · section {index}", content)
        for index, (page, content) in enumerate(
            split_page_text(text, page_number),
            start=1,
        )
    ]


def _extract_pdf(document: Document) -> list[tuple[int, str, str]]:
    try:
        with document.file.open("rb") as pdf_file:
            reader = PdfReader(pdf_file)
            chunks = []
            for page_number, page in enumerate(reader.pages, start=1):
                chunks.extend(
                    (page, f"Page {page}", content)
                    for page, content in split_page_text(
                        page.extract_text() or "",
                        page_number,
                    )
                )
    except Exception as exc:
        raise DocumentValidationError(
            "This PDF could not be read. Check that it is a valid, unencrypted PDF."
        ) from exc

    if not chunks:
        raise DocumentValidationError(
            "No selectable text was found in this PDF. Scanned PDFs need OCR before upload."
        )
    return chunks


def _decode_text(document: Document) -> str:
    try:
        with document.file.open("rb") as source:
            return source.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentValidationError(
            "Text files must use UTF-8 encoding."
        ) from exc


def _table_chunks(headers, rows, location_prefix: str) -> list[tuple[int, str, str]]:
    column_context = "Columns: " + " | ".join(headers)
    if len(column_context) > TABLE_CHUNK_SIZE:
        raise DocumentValidationError(
            "This table has too many or too-long column names to index safely."
        )

    output = []
    lines = []
    start_row = None
    end_row = None
    content_size = len(column_context) + len("\nRows:\n")

    def flush():
        nonlocal lines, start_row, end_row, content_size
        if not lines or start_row is None or end_row is None:
            return
        output.append(
            (
                1,
                f"{location_prefix} rows {start_row}-{end_row}",
                f"{column_context}\nRows:\n" + "\n".join(lines),
            )
        )
        lines = []
        start_row = None
        end_row = None
        content_size = len(column_context) + len("\nRows:\n")

    for row_number, row in rows:
        values = [
            str(value).strip() if value is not None and str(value).strip() else ""
            for value in row[: len(headers)]
        ]
        if len(row) > len(headers):
            values.extend(
                f"Extra column {index}: {str(value).strip()}"
                for index, value in enumerate(row[len(headers) :], start=len(headers) + 1)
            )
        if not any(values):
            continue

        row_line = f"{row_number}: " + " | ".join(values)
        row_size = len(row_line) + 1
        if len(column_context) + len("\nRows:\n") + row_size > TABLE_CHUNK_SIZE:
            flush()
            oversized_text = f"{column_context}\n{row_line}"
            fragments = split_page_text(oversized_text, page_number=1)
            output.extend(
                (
                    1,
                    f"{location_prefix} row {row_number}, part {part}",
                    fragment,
                )
                for part, (_page, fragment) in enumerate(fragments, start=1)
            )
            continue

        if lines and content_size + row_size > TABLE_CHUNK_SIZE:
            flush()
        if start_row is None:
            start_row = row_number
        end_row = row_number
        lines.append(row_line)
        content_size += row_size

    flush()
    return output


def _extract_docx(document: Document) -> list[tuple[int, str, str]]:
    try:
        with document.file.open("rb") as source:
            word_document = WordDocument(source)
            sections = [
                paragraph.text.strip()
                for paragraph in word_document.paragraphs
                if paragraph.text.strip()
            ]
            for table_number, table in enumerate(word_document.tables, start=1):
                for row_number, row in enumerate(table.rows, start=1):
                    cells = [
                        re.sub(r"\s+", " ", cell.text).strip()
                        for cell in row.cells
                    ]
                    if any(cells):
                        sections.append(
                            f"Table {table_number}, row {row_number}: "
                            + " | ".join(cells)
                        )
    except Exception as exc:
        raise DocumentValidationError(
            "This DOCX file could not be read. Check that it is a valid Word document."
        ) from exc

    if not sections:
        raise DocumentValidationError("No readable text was found in this DOCX file.")
    return _labelled_chunks("\n".join(sections), 1, "DOCX")


def _extract_csv(document: Document) -> list[tuple[int, str, str]]:
    try:
        with document.file.open("rb") as source:
            text_source = TextIOWrapper(source, encoding="utf-8-sig", newline="")
            sample = text_source.read(8192)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            text_source.seek(0)
            reader = csv.reader(text_source, dialect)
            header_row_number = 0
            headers = None
            for row_number, row in enumerate(reader, start=1):
                if not row or not any(cell.strip() for cell in row):
                    continue
                if len(row) == 1 and row[0].lstrip().startswith("#"):
                    continue
                headers = row
                header_row_number = row_number
                break
            if headers is None:
                raise DocumentValidationError(
                    "The CSV file must contain a header and at least one data row."
                )
            normalized_headers = [
                cell.strip() or f"Column {index}"
                for index, cell in enumerate(headers, 1)
            ]
            chunks = _table_chunks(
                normalized_headers,
                enumerate(reader, start=header_row_number + 1),
                "CSV",
            )
    except UnicodeDecodeError as exc:
        raise DocumentValidationError("Text files must use UTF-8 encoding.") from exc
    except csv.Error as exc:
        raise DocumentValidationError("This CSV file could not be parsed.") from exc

    if not chunks:
        raise DocumentValidationError("The CSV file must contain a header and at least one data row.")
    return chunks


def _extract_xlsx(document: Document) -> list[tuple[int, str, str]]:
    try:
        with document.file.open("rb") as source:
            workbook = load_workbook(source, read_only=True, data_only=True)
            chunks = []
            try:
                for sheet in workbook.worksheets:
                    rows = sheet.iter_rows(values_only=True)
                    headers = next(rows, None)
                    if headers is None:
                        continue
                    labels = [
                        str(value).strip() if value is not None else f"Column {index}"
                        for index, value in enumerate(headers, 1)
                    ]
                    chunks.extend(
                        _table_chunks(
                            labels,
                            enumerate(rows, start=2),
                            f"Sheet {sheet.title}",
                        )
                    )
            finally:
                workbook.close()
    except Exception as exc:
        raise DocumentValidationError(
            "This XLSX file could not be read. Check that it is a valid Excel workbook."
        ) from exc

    if not chunks:
        raise DocumentValidationError("No readable worksheet data was found in this XLSX file.")
    return chunks


def _extract_json(document: Document) -> list[tuple[int, str, str]]:
    text = _decode_text(document)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DocumentValidationError("This JSON file contains invalid JSON.") from exc
    return _labelled_chunks(
        json.dumps(data, ensure_ascii=False, indent=2),
        1,
        "JSON",
    )


def extract_document_chunks(document: Document) -> list[tuple[int, str, str]]:
    file_type = Path(document.title).suffix.lower()
    if file_type == ".pdf":
        chunks = _extract_pdf(document)
    elif file_type == ".docx":
        chunks = _extract_docx(document)
    elif file_type in {".txt", ".md"}:
        text = _decode_text(document)
        chunks = _labelled_chunks(text, 1, file_type[1:].upper())
        if not chunks:
            raise DocumentValidationError("This file does not contain searchable text.")
    elif file_type == ".csv":
        chunks = _extract_csv(document)
    elif file_type == ".xlsx":
        chunks = _extract_xlsx(document)
    elif file_type == ".json":
        chunks = _extract_json(document)
    else:
        raise DocumentValidationError(
            "Supported files are PDF, DOCX, TXT, MD, CSV, XLSX, and JSON."
        )

    if len(chunks) > MAX_DOCUMENT_CHUNKS:
        raise DocumentValidationError(
            f"This file is too large to index. Limit it to {MAX_DOCUMENT_CHUNKS} text chunks."
        )
    return chunks


def extract_pdf_chunks(document: Document) -> list[tuple[int, str]]:
    """Retain the legacy PDF extraction helper used by existing integrations."""
    return [(page, content) for page, _location, content in _extract_pdf(document)]


def _set_processing_progress(document: Document, stage: str, progress: int):
    document.processing_stage = stage
    document.processing_progress = progress
    document.save(
        update_fields=["processing_stage", "processing_progress", "updated_at"]
    )


def process_document(document: Document, backend: str = "celery") -> Document:
    document.status = Document.STATUS_PROCESSING
    document.processing_backend = backend
    document.processing_stage = "extracting"
    document.processing_progress = 5
    document.processing_error = ""
    document.save(
        update_fields=[
            "status",
            "processing_backend",
            "processing_stage",
            "processing_progress",
            "processing_error",
            "updated_at",
        ]
    )

    vector_store = None
    vector_ids: list[str] = []
    try:
        extracted_chunks = extract_document_chunks(document)
        _set_processing_progress(document, "embedding", 10)
        provider = get_ai_provider()
        embedding_batches = [
            (
                offset,
                [
                    text
                    for _, _, text in extracted_chunks[
                        offset : offset + EMBEDDING_BATCH_SIZE
                    ]
                ],
            )
            for offset in range(0, len(extracted_chunks), EMBEDDING_BATCH_SIZE)
        ]
        batch_results: dict[int, list[list[float]]] = {}
        completed_batches = 0
        with ThreadPoolExecutor(max_workers=EMBEDDING_WORKERS) as executor:
            futures = {
                executor.submit(provider.embed_documents, texts): offset
                for offset, texts in embedding_batches
            }
            for future in as_completed(futures):
                offset = futures[future]
                batch_embeddings = future.result()
                expected_count = min(
                    EMBEDDING_BATCH_SIZE,
                    len(extracted_chunks) - offset,
                )
                if len(batch_embeddings) != expected_count:
                    raise DocumentIndexError(
                        "The embedding service returned an incomplete result."
                    )
                batch_results[offset] = batch_embeddings
                completed_batches += 1
                progress = 10 + int(75 * completed_batches / len(embedding_batches))
                _set_processing_progress(document, "embedding", progress)
        embeddings = [
            embedding
            for offset in sorted(batch_results)
            for embedding in batch_results[offset]
        ]

        if len(embeddings) != len(extracted_chunks):
            raise DocumentIndexError(
                "The embedding service returned an incomplete result."
            )

        chunk_rows = [
            DocumentChunk(
                document=document,
                chunk_index=index,
                page_number=page_number,
                source_location=source_location,
                content=text,
            )
            for index, (page_number, source_location, text) in enumerate(
                extracted_chunks
            )
        ]

        # Purge any chunks (and their vectors) left over from a previous failed
        # attempt.  Doing this inside a transaction means a crash between the
        # delete and the insert cannot leave the document in an inconsistent
        # state — the outer exception handler will mark it failed again.
        stale_chunk_ids = list(
            DocumentChunk.objects.filter(document=document).values_list("id", flat=True)
        )
        if stale_chunk_ids:
            try:
                stale_vector_store = ChromaVectorStore()
                stale_vector_store.delete_documents(
                    [str(pk) for pk in stale_chunk_ids],
                    collection="pdf_chunks",
                )
            except Exception:
                logger.exception(
                    "Could not remove stale vectors for document %s before re-index",
                    document.pk,
                )
            DocumentChunk.objects.filter(document=document).delete()

        with transaction.atomic():
            DocumentChunk.objects.bulk_create(chunk_rows)

        vector_store = ChromaVectorStore()
        _set_processing_progress(document, "indexing", 85)
        for offset in range(0, len(chunk_rows), VECTOR_BATCH_SIZE):
            rows = chunk_rows[offset : offset + VECTOR_BATCH_SIZE]
            vectors = embeddings[offset : offset + VECTOR_BATCH_SIZE]
            vector_ids.extend(
                vector_store.add_documents(
                    [
                        {
                            "id": str(chunk.pk),
                            "text": chunk.content,
                            "embedding": embedding,
                            "metadata": {
                                "user_id": str(document.uploaded_by_id),
                                "company_id": str(document.company_id)
                                if document.company_id
                                else "",
                                "document_id": str(document.pk),
                                "chunk_id": str(chunk.pk),
                                "page_number": chunk.page_number,
                                "source_location": chunk.source_location,
                                "file_type": document.file_type,
                            },
                        }
                        for chunk, embedding in zip(rows, vectors, strict=True)
                    ],
                    collection="pdf_chunks",
                )
            )
            progress = 85 + int(
                14 * min(offset + len(rows), len(chunk_rows)) / len(chunk_rows)
            )
            _set_processing_progress(document, "indexing", progress)

        document.status = Document.STATUS_READY
        document.processing_stage = "ready"
        document.processing_progress = 100
        document.chunk_count = len(chunk_rows)
        document.processing_error = ""
        document.save(
            update_fields=[
                "status",
                "processing_stage",
                "processing_progress",
                "chunk_count",
                "processing_error",
                "updated_at",
            ]
        )
        return document
    except (DocumentValidationError, DocumentIndexError) as exc:
        if vector_store and vector_ids:
            try:
                vector_store.delete_documents(vector_ids, collection="pdf_chunks")
            except Exception:
                logger.exception(
                    "Could not remove partial vectors for document %s",
                    document.pk,
                )
        DocumentChunk.objects.filter(document=document).delete()
        document.status = Document.STATUS_FAILED
        document.processing_stage = "failed"
        document.processing_progress = 0
        document.chunk_count = 0
        document.processing_error = str(exc)
        document.save(
            update_fields=[
                "status",
                "processing_stage",
                "processing_progress",
                "chunk_count",
                "processing_error",
                "updated_at",
            ]
        )
        raise
    except Exception as exc:
        if vector_store and vector_ids:
            try:
                vector_store.delete_documents(vector_ids, collection="pdf_chunks")
            except Exception:
                logger.exception(
                    "Could not remove partial vectors for document %s",
                    document.pk,
                )
        DocumentChunk.objects.filter(document=document).delete()
        document.status = Document.STATUS_FAILED
        document.processing_stage = "failed"
        document.processing_progress = 0
        document.chunk_count = 0
        document.processing_error = (
            "Document indexing failed. Check the embedding provider and vector database configuration."
        )
        document.save(
            update_fields=[
                "status",
                "processing_stage",
                "processing_progress",
                "chunk_count",
                "processing_error",
                "updated_at",
            ]
        )
        raise DocumentIndexError(document.processing_error) from exc


def process_pdf_document(document: Document) -> Document:
    """Backward-compatible alias for code that still calls the PDF processor."""
    return process_document(document)
