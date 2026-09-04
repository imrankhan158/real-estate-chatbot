"""
RAG retrieval – embeds a query and returns the top-k matching properties from ChromaDB.
"""

import logging

from ingest import get_collection, get_model

logger = logging.getLogger(__name__)


def retrieve(query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
    """
    Embed the query and return the top-k most relevant property documents.
    Each item contains: id, document, metadata, distance, relevance_score.
    """
    model = get_model()
    collection = get_collection()

    embedding = model.encode([query], show_progress_bar=False).tolist()[0]
    n_results = min(k, max(collection.count(), 1))

    try:
        raw = collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=filters or None,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        logger.exception("ChromaDB query failed")
        return []

    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]
    ids = raw.get("ids", [[]])[0]

    return [
        {
            "id": ids[i],
            "document": docs[i],
            "metadata": metas[i],
            "distance": distances[i],
            "relevance_score": round(1 - distances[i], 3),
        }
        for i in range(len(docs))
    ]


def build_context(results: list[dict]) -> str:
    """Format retrieved documents into a prompt context block."""
    if not results:
        return "No relevant properties found in the database."

    sections = []
    for i, r in enumerate(results, 1):
        url = r.get("metadata", {}).get("url", "")
        score = r.get("relevance_score", 0)
        sections.append(
            f"### Property {i} (relevance: {score:.2f})\n"
            f"{r['document']}\n"
            f"URL: {url}"
        )

    return "\n\n".join(sections)
