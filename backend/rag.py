"""
RAG retrieval – embeds a query and returns the top-k matching properties from Pinecone.
"""

import logging

from ingest import get_index, get_model
from config import settings

logger = logging.getLogger(__name__)


def retrieve(query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
    """
    Embed the query and return the top-k most relevant property documents.
    Each item contains: id, document, metadata, score.
    """
    model = get_model()
    index = get_index()

    embedding = model.encode([query], show_progress_bar=False).tolist()[0]

    try:
        response = index.query(
            vector=embedding,
            top_k=k,
            filter=filters,
            include_metadata=True,
        )
    except Exception:
        logger.exception("Pinecone query failed")
        return []

    results = []
    for match in response.get("matches", []):
        metadata = match.get("metadata", {})
        results.append({
            "id": match.get("id", ""),
            # text chunk is stored in metadata to avoid a second fetch
            "document": metadata.pop("text", ""),
            "metadata": metadata,
            "relevance_score": round(float(match.get("score", 0)), 3),
        })

    return results


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
