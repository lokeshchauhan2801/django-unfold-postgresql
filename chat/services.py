from __future__ import annotations

import csv
import logging
import math
import re
from collections import Counter
from io import TextIOWrapper
from pathlib import Path
from typing import Literal

from django.db import transaction
from pydantic import BaseModel, Field, model_validator

from ai.providers import get_ai_provider
from chat.models import Conversation, Message
from docs.models import Document, DocumentChunk
from infrastructure.vectorstore.chroma_backend import ChromaVectorStore

logger = logging.getLogger(__name__)


class ChatProviderError(Exception):
    """Raised when the configured AI provider cannot generate a response."""


class ChatRetrievalError(Exception):
    """Raised when document references cannot be retrieved from vector storage."""


class ChartPoint(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    values: list[float] = Field(min_length=1, max_length=6)


class ChartData(BaseModel):
    type: Literal["pie", "bar", "line"]
    title: str = Field(min_length=1, max_length=200)
    x_axis: str = Field(min_length=1, max_length=100)
    y_axis: str = Field(min_length=1, max_length=100)
    series: list[str] = Field(min_length=1, max_length=6)
    data: list[ChartPoint] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_series_data(self):
        if self.type == "pie" and len(self.series) != 1:
            raise ValueError("Pie charts must have exactly one data series.")
        if len(set(self.series)) != len(self.series):
            raise ValueError("Chart series names must be unique.")
        for point in self.data:
            if len(point.values) != len(self.series):
                raise ValueError("Each chart point must have one value per series.")
            if any(not math.isfinite(value) for value in point.values):
                raise ValueError("Chart values must be finite numbers.")
            if self.type == "pie" and any(value < 0 for value in point.values):
                raise ValueError("Pie chart values cannot be negative.")
        if self.type == "pie" and not any(
            point.values[0] > 0 for point in self.data
        ):
            raise ValueError("Pie charts must contain a positive value.")
        return self


class ChatCompletion(BaseModel):
    response: str = Field(min_length=1)
    chart: ChartData | None = None


class ChatService:
    def __init__(self, provider=None, vector_store=None):
        try:
            self.provider = provider or get_ai_provider()
        except Exception as exc:
            raise ChatProviderError(
                "The configured AI provider is unavailable."
            ) from exc
        self.vector_store = vector_store or ChromaVectorStore()

    def create_conversation(self, user, title="New conversation", company=None):
        return Conversation.objects.create(user=user, title=title, company=company)

    def add_message(
        self,
        conversation,
        role,
        content,
        model_name=None,
        citations=None,
        chart_data=None,
    ):
        return Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            model_name=model_name or getattr(self.provider, "model", "gpt-4o-mini"),
            citations=citations or [],
            chart_data=chart_data,
        )

    def _find_relevant_chunks(self, user, question, conversation=None, company=None):
        attached_document_ids = (
            list(conversation.documents.values_list("pk", flat=True))
            if conversation
            else []
        )
        documents = Document.objects.filter(
            status=Document.STATUS_READY,
            chunk_count__gt=0,
        )
        if company:
            documents = documents.filter(company=company)
        else:
            documents = documents.filter(uploaded_by=user, company__isnull=True)
        if attached_document_ids:
            documents = documents.filter(pk__in=attached_document_ids)
        document_ids = [str(document_id) for document_id in documents.values_list("pk", flat=True)]
        if not document_ids:
            return []

        try:
            query_embedding = self.provider.embed_query(question)
            vector_filter = (
                {"document_id": {"$in": document_ids}}
                if company
                else {
                    "$and": [
                        {"user_id": str(user.pk)},
                        {"document_id": {"$in": document_ids}},
                    ]
                }
            )
            matches = self.vector_store.similarity_search(
                query_embedding,
                collection="pdf_chunks",
                k=20 if re.search(r"\b(chart|graph|plot|visuali[sz]e)\b", question, re.I) else 5,
                filter=vector_filter,
            )
        except Exception as exc:
            raise ChatRetrievalError(
                "Could not search the uploaded document index."
            ) from exc

        ranked_ids = [match["id"] for match in matches]
        chunk_documents = Document.objects.filter(pk__in=document_ids)
        if not company:
            chunk_documents = chunk_documents.filter(uploaded_by=user)
        chunks = {
            str(chunk.pk): chunk
            for chunk in DocumentChunk.objects.filter(
                pk__in=ranked_ids,
                document__in=chunk_documents,
                document__status=Document.STATUS_READY,
            ).select_related("document")
        }
        return [chunks[chunk_id] for chunk_id in ranked_ids if chunk_id in chunks]

    def _build_prompt(self, history, question, chunks):
        context_sections = []
        citations = []
        for chunk in chunks:
            reference_id = str(chunk.pk)
            filename = Path(chunk.document.file.name).name
            context_sections.append(
                f"[Source reference: {reference_id}; file: {filename}; "
                f"location: {chunk.source_location or f'page {chunk.page_number}'}]\n"
                f"{chunk.content}"
            )
            citations.append(
                {
                    "reference_id": reference_id,
                    "document_id": str(chunk.document_id),
                    "filename": filename,
                    "page": chunk.page_number,
                    "source_location": chunk.source_location,
                    "excerpt": chunk.content[:300],
                }
            )

        history_text = "\n".join(
            f"{message.role.title()}: {message.content}" for message in history
        )
        document_context = (
            "\n\n".join(context_sections)
            if context_sections
            else "No relevant passages were retrieved from uploaded files for this question."
        )

        prompt = (
            "You are a helpful assistant in a private document chat workspace. "
            "Answer using the retrieved passages from the user's uploaded files when relevant. "
            "Cite factual claims from those passages with their exact reference "
            "in square brackets, for example [<reference UUID>]. Never invent "
            "a source, page, or reference. For explicit chart/graph requests, "
            "return a chart only when the retrieved file context supports the "
            "values; copy metric values from that context and never make up "
            "numbers. Otherwise set chart to null and explain what data is missing. "
            "For pie charts use one series and non-negative values. For bar/line "
            "charts use one or more named series. The chart must use this schema: "
            "{type: pie|bar|line, title, x_axis, y_axis, series: [names], "
            "data: [{label, values: [one number per series in series order]}]}. "
            "Limit chart data "
            "to 100 points and 6 series. Return a response object containing "
            "response (answer text) and chart (chart object or null).\n\n"
            f"Retrieved passages:\n{document_context}\n\n"
            f"Conversation so far:\n{history_text or '(new conversation)'}\n\n"
            f"User: {question}\nAssistant:"
        )
        return prompt, citations

    def _build_csv_distribution_chart(self, conversation, question):
        if not re.search(
            r"\b(chart|graph|plot|visuali[sz]e|distribution)\b",
            question,
            re.I,
        ):
            return None

        documents = conversation.documents.filter(
            uploaded_by=conversation.user,
            status=Document.STATUS_READY,
            file_type="csv",
        )
        for document in documents:
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
                    headers = None
                    for row in reader:
                        if not row or not any(cell.strip() for cell in row):
                            continue
                        if len(row) == 1 and row[0].lstrip().startswith("#"):
                            continue
                        headers = [cell.strip() for cell in row]
                        break
                    if not headers:
                        continue

                    selected_index = next(
                        (
                            index
                            for index, header in enumerate(headers)
                            if header
                            and re.search(
                                rf"\b{re.escape(header)}s?\b",
                                question,
                                re.I,
                            )
                        ),
                        None,
                    )
                    if selected_index is None:
                        continue

                    counts = Counter()
                    for row in reader:
                        if selected_index >= len(row):
                            continue
                        value = row[selected_index].strip()
                        if not value:
                            continue
                        try:
                            numeric_value = float(value)
                        except ValueError:
                            continue
                        if math.isfinite(numeric_value):
                            counts[numeric_value] += 1
            except (OSError, UnicodeDecodeError, csv.Error):
                logger.exception(
                    "Could not read CSV %s to generate a local chart",
                    document.pk,
                )
                continue

            if not counts:
                continue

            chart_type = (
                "pie"
                if re.search(r"\bpie\b", question, re.I)
                else "line"
                if re.search(r"\bline\b", question, re.I)
                else "bar"
            )
            chart = ChartData(
                type=chart_type,
                title=f"Distribution of {headers[selected_index]}",
                x_axis=headers[selected_index],
                y_axis="Number of records",
                series=["Records"],
                data=[
                    ChartPoint(
                        label=str(int(value)) if value.is_integer() else format(value, "g"),
                        values=[count],
                    )
                    for value, count in sorted(counts.items())[:100]
                ],
            )
            return (
                f"Here is the {chart_type} chart of {headers[selected_index]} "
                f"from {document.title}, based on {sum(counts.values()):,} records.",
                chart,
            )
        return None

    def process_message(
        self,
        user,
        message_text,
        conversation=None,
        user_message=None,
        company=None,
    ):
        if not user or not user.is_authenticated:
            raise ValueError("A signed-in user is required to chat.")

        if conversation and (
            conversation.user_id != user.pk
            or conversation.company_id != getattr(company, "pk", None)
        ):
            raise ValueError("Conversation does not belong to the signed-in user.")

        history_query = (
            conversation.messages.exclude(role=Message.ROLE_SYSTEM)
            if conversation
            else Message.objects.none()
        )
        if user_message:
            history_query = history_query.exclude(pk=user_message.pk)
        history = list(history_query.order_by("-created_at")[:10])
        history.reverse()
        try:
            local_chart = (
                self._build_csv_distribution_chart(conversation, message_text)
                if conversation
                else None
            )
            if local_chart:
                response_text, chart = local_chart
                citations = []
                completion = ChatCompletion(response=response_text, chart=chart)
            else:
                chunks = self._find_relevant_chunks(
                    user,
                    message_text,
                    conversation,
                    company,
                )
                prompt, citations = self._build_prompt(history, message_text, chunks)
                completion = self.provider.generate_structured(prompt, ChatCompletion)
                completion = ChatCompletion.model_validate(completion)
        except (ChatRetrievalError, ChatProviderError):
            raise
        except Exception as exc:
            raise ChatProviderError(
                "The AI provider failed to generate a response."
            ) from exc

        if not completion.response.strip():
            raise ChatProviderError("The AI provider returned an empty response.")

        with transaction.atomic():
            convo = conversation or self.create_conversation(
                user=user,
                title=message_text[:200],
                company=company,
            )
            if user_message:
                if user_message.conversation_id != convo.pk:
                    raise ValueError("User message does not belong to this conversation.")
            else:
                self.add_message(
                    convo,
                    Message.ROLE_USER,
                    message_text,
                    model_name="user",
                )
            assistant_message = self.add_message(
                convo,
                Message.ROLE_ASSISTANT,
                completion.response.strip(),
                citations=citations,
                chart_data=(
                    completion.chart.model_dump(mode="json")
                    if completion.chart
                    else None
                ),
            )
            if convo.title == "New conversation":
                convo.title = message_text[:200]
                convo.save(update_fields=["title", "updated_at"])
            else:
                convo.save(update_fields=["updated_at"])
        return assistant_message
