"""
Ingest scraped property data into ChromaDB.
Loads darglobal.json and wasalt.json, builds text chunks, embeds, and upserts.
"""

import json
import logging
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)

# Module-level singletons – initialised lazily on first use
_model: SentenceTransformer | None = None
_collection: chromadb.Collection | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        logger.info("Connecting to ChromaDB at %s:%s", settings.chroma_host, settings.chroma_port)
        client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        _collection = client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


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
    """Extract flat metadata for ChromaDB (no nested dicts, no None values)."""
    loc = prop.get("location", {})
    return {
        "source": prop.get("source", "unknown"),
        "title": prop.get("title", "")[:200],
        "property_type": prop.get("property_type", ""),
        "price": float(prop["price"]) if prop.get("price") else -1.0,
        "currency": prop.get("currency", ""),
        "city": loc.get("city", ""),
        "country": loc.get("country", ""),
        "bedrooms": int(prop["bedrooms"]) if prop.get("bedrooms") is not None else -1,
        "bathrooms": int(prop["bathrooms"]) if prop.get("bathrooms") is not None else -1,
        "area_sqm": float(prop["area_sqm"]) if prop.get("area_sqm") is not None else -1.0,
        "url": prop.get("url", ""),
    }


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning("Data file not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Public API ─────────────────────────────────────────────────────────────────

def ingest_all() -> dict:
    """Load property JSON files and upsert into ChromaDB. Idempotent."""
    collection = get_collection()

    if collection.count() > 0:
        count = collection.count()
        logger.info("ChromaDB already has %d documents – skipping re-ingestion", count)
        return {"status": "skipped", "existing": count}

    all_properties: list[dict] = []
    for filename in ("darglobal.json", "wasalt.json"):
        props = _load_json(settings.data_dir / filename)
        all_properties.extend(props)
        logger.info("Loaded %d properties from %s", len(props), filename)

    if not all_properties:
        logger.error("No property data found to ingest")
        return {"status": "error", "message": "No data files found"}

    ids = [str(p.get("id", f"prop_{i}")) for i, p in enumerate(all_properties)]
    documents = [_build_text_chunk(p) for p in all_properties]
    metadatas = [_build_metadata(p) for p in all_properties]

    model = get_model()
    batch_size = 50
    total = 0

    for i in range(0, len(documents), batch_size):
        batch_slice = slice(i, i + batch_size)
        embeddings = model.encode(documents[batch_slice], show_progress_bar=False).tolist()
        collection.upsert(
            ids=ids[batch_slice],
            documents=documents[batch_slice],
            embeddings=embeddings,
            metadatas=metadatas[batch_slice],
        )
        total += len(embeddings)
        logger.info("Ingested %d / %d documents", total, len(documents))

    logger.info("Ingestion complete: %d documents", total)
    return {"status": "ok", "ingested": total}


def get_stats() -> dict:
    """Return property counts per source."""
    collection = get_collection()
    total = collection.count()
    try:
        dg = collection.get(where={"source": "darglobal"})
        ws = collection.get(where={"source": "wasalt"})
        return {"total": total, "darglobal": len(dg["ids"]), "wasalt": len(ws["ids"])}
    except Exception:
        return {"total": total, "darglobal": 0, "wasalt": 0}
