"""
Ingest scraped property data into Pinecone (serverless, cloud vector DB).
Loads darglobal.json and wasalt.json, embeds with sentence-transformers, upserts to Pinecone.
"""

import json
import logging
from pathlib import Path

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)

# Lazy singletons
_model: SentenceTransformer | None = None
_index = None  # pinecone.Index


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def get_index():
    """Return the Pinecone index, creating it if necessary."""
    global _index
    if _index is not None:
        return _index

    pc = Pinecone(api_key=settings.pinecone_api_key)

    # Create index if it doesn't exist
    existing = [idx.name for idx in pc.list_indexes()]
    if settings.pinecone_index_name not in existing:
        logger.info("Creating Pinecone index: %s", settings.pinecone_index_name)
        pc.create_index(
            name=settings.pinecone_index_name,
            dimension=settings.embedding_dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    logger.info("Connecting to Pinecone index: %s", settings.pinecone_index_name)
    _index = pc.Index(settings.pinecone_index_name)
    return _index


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_text_chunk(prop: dict) -> str:
    """Build a human-readable text representation of a property for embedding."""
    source = prop.get("source", "unknown").upper()
    title = prop.get("title", "Property")

    loc = prop.get("location", {})
    location_str = ", ".join(filter(None, [
        loc.get("district", ""), loc.get("city", ""), loc.get("country", ""),
    ]))

    price = prop.get("price")
    currency = prop.get("currency", "")
    price_str = f"{currency} {price:,.0f}" if price else "Price on request"

    ptype = prop.get("property_type", "").replace("_", " ").title()

    specs: list[str] = []
    if (beds := prop.get("bedrooms")) is not None:
        specs.append(f"{beds} bed{'s' if beds != 1 else ''}")
    if (baths := prop.get("bathrooms")) is not None:
        specs.append(f"{baths} bath{'s' if baths != 1 else ''}")
    if (area := prop.get("area_sqm")) is not None:
        specs.append(f"{area:.0f} sqm")

    lines = [
        f"[{source}] {title}",
        f"Location: {location_str}",
        f"Price: {price_str} | Type: {ptype}" + (f" | {' | '.join(specs)}" if specs else ""),
    ]

    amenities = prop.get("amenities", [])
    if amenities:
        lines.append(f"Amenities: {', '.join(amenities[:8])}")

    description = prop.get("description", "")[:500]
    if description:
        lines.append(f"Description: {description}")

    return "\n".join(lines)


def _build_metadata(prop: dict) -> dict:
    """
    Flat metadata dict for Pinecone.
    Pinecone only supports str, int, float, bool and lists of those — no nested dicts or None.
    """
    loc = prop.get("location", {})
    return {
        "source": prop.get("source", "unknown"),
        "title": prop.get("title", "")[:200],
        "property_type": prop.get("property_type", ""),
        "price": float(prop["price"]) if prop.get("price") else -1.0,
        "currency": prop.get("currency", ""),
        "city": loc.get("city", "") or "",
        "country": loc.get("country", "") or "",
        "bedrooms": int(prop["bedrooms"]) if prop.get("bedrooms") is not None else -1,
        "bathrooms": int(prop["bathrooms"]) if prop.get("bathrooms") is not None else -1,
        "area_sqm": float(prop["area_sqm"]) if prop.get("area_sqm") is not None else -1.0,
        "url": prop.get("url", ""),
        # Store the full text chunk so we can return it in query results
        "text": _build_text_chunk(prop),
    }


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning("Data file not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Public API ─────────────────────────────────────────────────────────────────

def ingest_all() -> dict:
    """Load property JSON files and upsert into Pinecone. Idempotent."""
    index = get_index()

    # Check if already populated
    stats = index.describe_index_stats()
    existing = stats.get("total_vector_count", 0)
    if existing > 0:
        logger.info("Pinecone already has %d vectors – skipping re-ingestion", existing)
        return {"status": "skipped", "existing": existing}

    all_properties: list[dict] = []
    for filename in ("darglobal.json", "wasalt.json"):
        props = _load_json(settings.data_dir / filename)
        all_properties.extend(props)
        logger.info("Loaded %d properties from %s", len(props), filename)

    if not all_properties:
        logger.error("No property data found to ingest")
        return {"status": "error", "message": "No data files found"}

    model = get_model()
    batch_size = 50
    total = 0

    for i in range(0, len(all_properties), batch_size):
        batch = all_properties[i:i + batch_size]
        texts = [_build_text_chunk(p) for p in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        vectors = [
            {
                "id": str(p.get("id", f"prop_{i + j}")),
                "values": embeddings[j],
                "metadata": _build_metadata(p),
            }
            for j, p in enumerate(batch)
        ]

        index.upsert(vectors=vectors)
        total += len(vectors)
        logger.info("Upserted %d / %d vectors", total, len(all_properties))

    logger.info("Ingestion complete: %d vectors in Pinecone", total)
    return {"status": "ok", "ingested": total}


def get_stats() -> dict:
    """Return property counts per source."""
    index = get_index()
    total = index.describe_index_stats().get("total_vector_count", 0)
    try:
        dg = index.query(
            vector=[0.0] * settings.embedding_dimension,
            top_k=1000,
            filter={"source": {"$eq": "darglobal"}},
            include_metadata=False,
        )
        ws = index.query(
            vector=[0.0] * settings.embedding_dimension,
            top_k=1000,
            filter={"source": {"$eq": "wasalt"}},
            include_metadata=False,
        )
        return {
            "total": total,
            "darglobal": len(dg.get("matches", [])),
            "wasalt": len(ws.get("matches", [])),
        }
    except Exception:
        return {"total": total, "darglobal": 0, "wasalt": 0}
