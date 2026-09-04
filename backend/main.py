"""
FastAPI application – Real Estate AI Chatbot
Routes: GET /health, GET /api/stats, POST /api/chat, GET /api/properties
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import chat
import guard
import ingest
import rag
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up – ingesting property data into ChromaDB...")
    try:
        result = ingest.ingest_all()
        logger.info("Ingest result: %s", result)
    except Exception:
        logger.exception("Ingest failed – continuing without pre-loaded data")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Real Estate AI Chatbot API",
    description="AI-powered chatbot over DarGlobal and Wasalt property listings",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError("role must be 'user' or 'assistant'")
        return v


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    model: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    try:
        count = ingest.get_collection().count()
        return {"status": "ok", "indexed": count}
    except Exception as exc:
        return {"status": "degraded", "error": str(exc), "indexed": 0}


@app.get("/api/stats", tags=["system"])
async def stats():
    return ingest.get_stats()


@app.post("/api/chat", tags=["chat"])
@limiter.limit("15/minute")
async def chat_endpoint(request: Request, body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not guard.is_allowed(body.message):
        async def rejection():
            yield chat._sse({"token": guard.REJECTION_MESSAGE})
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            rejection(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    results = rag.retrieve(body.message, k=5)
    context = rag.build_context(results)
    history = [{"role": m.role, "content": m.content} for m in body.history]

    return StreamingResponse(
        chat.stream_chat(body.message, history, context, body.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/properties", tags=["properties"])
async def list_properties(
    page: int = 1,
    limit: int = 20,
    source: Optional[str] = None,
    city: Optional[str] = None,
    property_type: Optional[str] = None,
    query: Optional[str] = None,
):
    """Browse properties with optional semantic search."""
    limit = min(limit, 100)

    if query:
        filters = {k: v for k, v in {"source": source}.items() if v}
        results = rag.retrieve(query, k=limit, filters=filters or None)
        return {"items": [r["metadata"] for r in results], "total": len(results), "page": 1}

    collection = ingest.get_collection()
    where = {k: v for k, v in {
        "source": source, "city": city, "property_type": property_type,
    }.items() if v}

    try:
        result = collection.get(
            where=where or None,
            limit=limit,
            offset=(page - 1) * limit,
            include=["metadatas"],
        )
        return {
            "items": result.get("metadatas", []),
            "total": collection.count(),
            "page": page,
            "limit": limit,
        }
    except Exception:
        logger.exception("Properties listing failed")
        return {"items": [], "total": 0, "page": page, "limit": limit}
