"""ChromaDB vector store implementation."""
from __future__ import annotations

from pathlib import Path

from .interfaces import VectorStore


class ChromaVectorStore(VectorStore):
    """ChromaDB-backed vector store."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        persistent_path: str | Path | None = None,
    ):
        from django.conf import settings

        self._host = host if host is not None else getattr(settings, "CHROMA_HOST", "")
        self._port = port or getattr(settings, "CHROMA_PORT", 8000)
        self._persistent_path = Path(
            persistent_path
            or getattr(settings, "CHROMA_PATH", settings.BASE_DIR / "chroma_data")
        )
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            from chromadb.config import Settings

            telemetry_settings = {
                "anonymized_telemetry": False,
                "chroma_product_telemetry_impl": (
                    "infrastructure.vectorstore.telemetry.DisabledProductTelemetry"
                ),
                "chroma_telemetry_impl": (
                    "infrastructure.vectorstore.telemetry.DisabledProductTelemetry"
                ),
            }
            if self._host:
                self._client = chromadb.HttpClient(
                    host=self._host,
                    port=self._port,
                    settings=Settings(**telemetry_settings),
                )
            else:
                self._persistent_path.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self._persistent_path),
                    settings=Settings(**telemetry_settings),
                )
        return self._client

    def add_documents(self, documents: list[dict], collection: str) -> list[str]:
        col = self.client.get_or_create_collection(
            collection,
            metadata={"hnsw:space": "cosine"},
        )
        ids = [str(doc["id"]) for doc in documents]
        embeddings = [doc["embedding"] for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]
        texts = [doc.get("text", "") for doc in documents]
        col.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)
        return ids

    def similarity_search(
        self,
        query_embedding: list[float],
        collection: str,
        k: int = 5,
        filter: dict | None = None,
    ) -> list[dict]:
        col = self.client.get_collection(collection)
        if col.count() == 0:
            return []
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(k, col.count()),
            where=filter,
        )
        out = []
        for i, doc_id in enumerate(results['ids'][0]):
            out.append(
                {
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )
        return out

    def get_embeddings(self, ids: list[str], collection: str) -> dict[str, list[float]]:
        if not ids:
            return {}
        col = self.client.get_collection(collection)
        result = col.get(ids=ids, include=["embeddings"])
        return {
            vector_id: [float(value) for value in embedding]
            for vector_id, embedding in zip(
                result["ids"],
                result["embeddings"],
                strict=True,
            )
            if embedding is not None
        }

    def delete_collection(self, collection: str) -> None:
        self.client.delete_collection(collection)

    def delete_documents(self, ids: list[str], collection: str) -> None:
        col = self.client.get_or_create_collection(collection)
        col.delete(ids=ids)
