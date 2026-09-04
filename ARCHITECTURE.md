# Real Estate AI Chatbot – Architecture & End-to-End Flow

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Project Structure](#project-structure)
4. [Service Descriptions](#service-descriptions)
5. [End-to-End Data Flow](#end-to-end-data-flow)
   - [Phase 1 – Startup & Data Ingestion](#phase-1--startup--data-ingestion)
   - [Phase 2 – User Sends a Message](#phase-2--user-sends-a-message)
   - [Phase 3 – Guard Check](#phase-3--guard-check)
   - [Phase 4 – Retrieval (RAG)](#phase-4--retrieval-rag)
   - [Phase 5 – LLM Generation](#phase-5--llm-generation)
   - [Phase 6 – Streaming Response](#phase-6--streaming-response)
6. [Component Reference](#component-reference)
7. [API Reference](#api-reference)
8. [Configuration Reference](#configuration-reference)
9. [Security Design](#security-design)
10. [Deployment](#deployment)

---

## Overview

This application is an AI-powered real estate chatbot that aggregates property listings
from two sources — **DarGlobal** (international luxury properties) and **Wasalt**
(Saudi Arabia's leading property marketplace) — and lets users query them in natural
language.

It uses a **Retrieval-Augmented Generation (RAG)** architecture: property data is
embedded into a vector database at startup, and every user query retrieves the most
relevant listings before passing them to a free LLM via OpenRouter. The LLM answers
strictly from the retrieved data, not from its training knowledge.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Docker Compose                                │
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────────┐    ┌───────────────┐  │
│  │  Scraper        │───▶│  Backend (FastAPI)    │◀───│  Frontend     │  │
│  │  Python         │    │                      │    │  Next.js 14   │  │
│  │                 │    │  ┌────────────────┐  │    │  Tailwind CSS │  │
│  │  - darglobal.py │    │  │ guard.py       │  │    └───────────────┘  │
│  │  - wasalt.py    │    │  │ rag.py         │  │           │           │
│  └────────┬────────┘    │  │ chat.py        │  │    http://localhost   │
│           │             │  │ ingest.py      │  │           :3000       │
│           │ JSON files  │  └───────┬────────┘  │                       │
│           ▼             └──────────┼───────────┘                       │
│     ┌───────────┐                  │                                    │
│     │  ./data/  │        ┌─────────▼──────────┐                        │
│     │  volume   │        │  ChromaDB          │                        │
│     └───────────┘        │  (vector store)    │                        │
│                          └────────────────────┘                        │
└──────────────────────────────────────┬─────────────────────────────────┘
                                       │ HTTPS
                              ┌────────▼────────┐
                              │  OpenRouter API  │
                              │  (free LLM tier) │
                              └─────────────────┘
```

**Ports exposed to host:**

| Port | Service | Purpose |
|------|---------|---------|
| 3000 | Frontend | Chat UI |
| 8080 | Backend | REST API |
| 8001 | ChromaDB | Vector DB (dev inspection) |

---

## Project Structure

```
real-estate-chatbot/
│
├── docker-compose.yml          # Orchestrates all four services
├── .env                        # Secrets & config (never committed)
├── .env.example                # Template for .env
├── .gitignore
├── README.md
├── ARCHITECTURE.md             # This document
│
├── scraper/                    # One-shot data collection service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # Entry point – runs both scrapers
│   ├── darglobal.py            # DarGlobal scraper + sample fallback
│   └── wasalt.py               # Wasalt scraper + sample fallback
│
├── backend/                    # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # App setup, routes, middleware
│   ├── config.py               # All settings from environment variables
│   ├── guard.py                # Topic guard – blocks off-topic questions
│   ├── ingest.py               # Loads JSON → embeds → upserts to ChromaDB
│   ├── rag.py                  # Query embedding + ChromaDB retrieval
│   └── chat.py                 # OpenRouter streaming integration
│
├── frontend/                   # Next.js chat UI
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      # Root HTML shell + metadata
│       │   ├── page.tsx        # Entry point → renders ChatWindow
│       │   └── globals.css     # Tailwind + custom styles
│       ├── components/
│       │   ├── ChatWindow.tsx  # Main stateful chat component
│       │   ├── MessageBubble.tsx   # Renders a single message
│       │   └── SuggestedPrompts.tsx  # Clickable starter questions
│       └── lib/
│           ├── api.ts          # All fetch calls (stats, chat)
│           └── sse.ts          # SSE stream parser utility
│
└── data/                       # Shared bind-mount volume (git-ignored)
    ├── darglobal.json          # Scraped DarGlobal listings
    └── wasalt.json             # Scraped Wasalt listings
```

---

## Service Descriptions

### 1. Scraper (`scraper/`)

A short-lived Python process that runs **once at startup** and then exits.

- Attempts live scraping of DarGlobal (static HTML via `httpx` + `BeautifulSoup4`)
  and Wasalt (internal REST API, with Playwright headless fallback).
- If live scraping yields fewer than 10 results per source, falls back to a curated
  sample dataset that accurately represents real listing types from each platform.
- Writes `data/darglobal.json` and `data/wasalt.json` to a shared bind-mount volume.
- Skips scraping if the output files already exist (cache-first strategy).

### 2. Backend (`backend/`)

A **FastAPI** application that forms the core of the system.

Responsibilities:
- On startup: reads the JSON files and ingests all properties into ChromaDB
  (embedding each listing with `sentence-transformers/all-MiniLM-L6-v2`).
- On each chat request: validates the topic, retrieves relevant listings,
  builds a prompt, and streams the LLM response back to the client.

### 3. ChromaDB (`vectordb`)

A persistent vector database used to store property embeddings.

- Runs as a standalone container using the official `chromadb/chroma` image.
- Embeddings persist across container restarts via a named Docker volume (`chroma_data`).
- The backend queries it on every chat request via cosine similarity search.

### 4. Frontend (`frontend/`)

A **Next.js 14** single-page app served as a standalone Node.js process.

- Renders the chat UI with streaming token display.
- Calls `GET /api/stats` on load to show property counts in the header.
- Sends `POST /api/chat` for each user message and reads the SSE response stream.
- All API communication is centralised in `src/lib/api.ts`.

---

## End-to-End Data Flow

### Phase 1 – Startup & Data Ingestion

```
Docker Compose starts services in dependency order:

  vectordb (healthy)
       │
       ▼
  scraper (runs once, exits)
       │  writes ./data/darglobal.json
       │  writes ./data/wasalt.json
       ▼
  backend (starts FastAPI)
       │
       │  lifespan event fires → ingest.ingest_all()
       │
       ├─ reads darglobal.json  (12+ properties)
       ├─ reads wasalt.json     (15+ properties)
       │
       │  for each property:
       │    text_chunk = _build_text_chunk(property)
       │      → "[DARGLOBAL] Aston Martin Residences – Duplex Penthouse
       │          Location: Downtown Dubai, UAE
       │          Price: USD 15,000,000 | Type: Apartment | 4 beds | 5 baths | 850 sqm
       │          Amenities: Private Pool, Concierge, Gym, Spa
       │          Description: Ultra-luxury penthouse..."
       │
       │    embedding = SentenceTransformer.encode(text_chunk)
       │      → float[384]  (all-MiniLM-L6-v2 output dimension)
       │
       │    ChromaDB.upsert(id, document, embedding, metadata)
       │
       └─ 27 documents indexed → FastAPI ready
               │
               ▼
         frontend (starts Next.js)
               │
               ▼
         http://localhost:3000  (ready for users)
```

---

### Phase 2 – User Sends a Message

```
Browser (http://localhost:3000)
  │
  │  User types: "Show me luxury villas in Dubai"
  │  Presses Enter or clicks Send button
  │
  │  ChatWindow.sendMessage()
  │    - appends user bubble to messages state
  │    - appends empty bot bubble (isStreaming: true)
  │    - calls lib/api.ts → streamChat()
  │
  └─ POST /api/chat  HTTP/1.1
       Content-Type: application/json
       Body: {
         "message": "Show me luxury villas in Dubai",
         "history": [...]   ← last N conversation turns
       }
```

---

### Phase 3 – Guard Check

```
Backend: main.py → chat_endpoint()
  │
  ├─ Validate: message is not empty
  │
  └─ guard.is_allowed("Show me luxury villas in Dubai")
       │
       ├─ Step 1: _BLOCKED_RE.search(text)
       │    Checks against regex blocklist:
       │    coding patterns, travel, weather, general knowledge, etc.
       │    → No match → not blocked
       │
       ├─ Step 2: word count ≤ 6?
       │    "Show me luxury villas in Dubai" = 6 words
       │    → Borderline, proceeds to allowlist check
       │
       └─ Step 3: _SIGNAL_RE.search(text)
            Checks for real-estate signals:
            "villa" ✓ → matches allowlist
            → ALLOWED ✓

  If BLOCKED:
    → returns SSE stream with rejection message instantly
    → no LLM call made, no ChromaDB query
```

---

### Phase 4 – Retrieval (RAG)

```
Backend: rag.retrieve("Show me luxury villas in Dubai", k=5)
  │
  ├─ model.encode(["Show me luxury villas in Dubai"])
  │    → query_embedding: float[384]
  │
  └─ ChromaDB.query(
         query_embeddings=[query_embedding],
         n_results=5,
         include=["documents", "metadatas", "distances"]
     )
       │
       │  Cosine similarity search across 27 property embeddings
       │
       └─ Returns top 5 closest documents, e.g.:
            1. Lamborghini Residences – Sky Villa (relevance: 0.91)
            2. Trump Estates – 4BR Golf Villa    (relevance: 0.88)
            3. DarGlobal Oman – Waterfront Villa  (relevance: 0.84)
            4. Sea-View Villa – Al Shati, Jeddah  (relevance: 0.79)
            5. Luxury Compound Villa – Al Yasmin  (relevance: 0.76)

  rag.build_context(results)
    → Formatted string:
        ### Property 1 (relevance: 0.91)
        [DARGLOBAL] Lamborghini Residences – Sky Villa
        Location: Business Bay, Dubai, UAE
        Price: USD 8,500,000 | Type: Villa | 5 beds | 6 baths | 700 sqm
        Amenities: Sky Pool, Private Gym, Home Cinema, Smart Home, 24/7 Security
        Description: Sky Villa in the Lamborghini-branded tower...
        URL: https://darglobal.co.uk/properties/lamborghini-residences

        ### Property 2 (relevance: 0.88)
        ...
```

---

### Phase 5 – LLM Generation

```
Backend: chat.stream_chat(message, history, context)
  │
  ├─ _build_messages(message, history, context)
  │    →  [
  │         { role: "system",  content: SYSTEM_PROMPT },
  │         { role: "user",    content: "..." },   ← history turns (last 6)
  │         { role: "assistant", content: "..." },
  │         { role: "user",    content:
  │             "Available properties:\n{context}\n\nQuestion: Show me luxury villas in Dubai"
  │         }
  │       ]
  │
  └─ Try models in order:
       1. google/gemma-4-31b-it:free
          POST https://openrouter.ai/api/v1/chat/completions
          { model, messages, stream: true, max_tokens: 1024, temperature: 0.3 }
          │
          ├─ 429 Rate Limited → try next model
          ├─ 404 Not Found    → try next model
          └─ 200 OK           → begin streaming ✓

       Model streams tokens back:
         "Here", " are", " some", " luxury", " villas", ...
```

---

### Phase 6 – Streaming Response

```
Backend → Frontend: SSE (Server-Sent Events) stream

  data: {"token": "Here"}
  data: {"token": " are"}
  data: {"token": " some"}
  data: {"token": " luxury"}
  data: {"token": " villas"}
  ...
  data: [DONE]

Frontend: lib/sse.ts → parseSSEStream()
  │
  │  onToken(token):
  │    setMessages(prev =>
  │      prev.map(msg =>
  │        msg.id === botId
  │          ? { ...msg, content: msg.content + token }
  │          : msg
  │      )
  │    )
  │    → React re-renders MessageBubble with growing content
  │    → User sees text appearing word by word
  │
  └─ onDone():
       setMessages → isStreaming: false
       setIsLoading(false)
       Typing cursor disappears
```

---

## Component Reference

### `config.py` – Settings

Single source of truth for all configuration. Every module imports `settings` —
nothing reads `os.environ` directly.

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `""` | Required for LLM calls |
| `chroma_host` | `CHROMA_HOST` | `vectordb` | ChromaDB hostname |
| `chroma_port` | `CHROMA_PORT` | `8000` | ChromaDB port |
| `data_dir` | `DATA_DIR` | `/app/data` | Path to JSON data files |
| `allowed_origins` | `ALLOWED_ORIGINS` | `*` | CORS origins |
| `app_url` | `APP_URL` | `http://localhost:3000` | OpenRouter attribution |
| `app_title` | `APP_TITLE` | `Real Estate AI Chatbot` | OpenRouter attribution |
| `embedding_model` | – | `all-MiniLM-L6-v2` | Sentence transformer model |
| `llm_models` | – | (list) | Ordered fallback model list |

---

### `guard.py` – Topic Guard

Prevents off-topic questions from reaching the LLM.

```
Input message
     │
     ▼
_BLOCKED_RE.search()    ← regex blocklist (coding, travel, general knowledge)
     │
     ├─ match → REJECT immediately (no LLM call)
     │
     ▼
word count ≤ 6?          ← short follow-ups allowed ("tell me more", "how much?")
     │
     ├─ yes → ALLOW
     │
     ▼
_SIGNAL_RE.search()     ← must contain a real-estate keyword
     │
     ├─ match → ALLOW
     └─ no match → REJECT
```

---

### `ingest.py` – Data Ingestion

| Function | Description |
|----------|-------------|
| `get_model()` | Lazy-loads `all-MiniLM-L6-v2` sentence transformer (singleton) |
| `get_collection()` | Lazy-connects to ChromaDB and returns the collection (singleton) |
| `ingest_all()` | Loads JSON → builds text chunks → embeds → upserts; idempotent |
| `get_stats()` | Returns `{total, darglobal, wasalt}` counts |

**Text chunk format** (what gets embedded and stored):
```
[SOURCE] Property Title
Location: District, City, Country
Price: CURRENCY AMOUNT | Type: TYPE | N beds | N baths | N sqm
Amenities: Pool, Gym, ...
Description: First 500 chars of description
```

---

### `rag.py` – Retrieval

| Function | Description |
|----------|-------------|
| `retrieve(query, k, filters)` | Embeds query, queries ChromaDB, returns top-k results |
| `build_context(results)` | Formats results into a prompt context string |

---

### `chat.py` – LLM Integration

| Function | Description |
|----------|-------------|
| `stream_chat(message, history, context, model_override)` | Async generator yielding SSE strings |
| `_build_messages(user_message, history, context)` | Assembles OpenAI-format message array |
| `_sse(payload)` | Formats a dict as an SSE data line |

**Model fallback order:**
1. `google/gemma-4-31b-it:free`
2. `nvidia/nemotron-3-ultra-550b-a55b:free`
3. `minimax/minimax-m3:free`
4. `nvidia/nemotron-3.5-lightning:free`
5. `thinkingmachines/inkling:free`
6. `nvidia/nemotron-3-super-120b-a12b:free`

---

### `lib/api.ts` – Frontend API Client

| Export | Description |
|--------|-------------|
| `fetchStats()` | `GET /api/stats` → `{total, darglobal, wasalt}` |
| `streamChat(message, history, signal)` | `POST /api/chat` → `ReadableStreamDefaultReader` |

---

### `lib/sse.ts` – SSE Parser

```typescript
parseSSEStream(reader, { onToken, onError, onDone })
```

Reads a `ReadableStream`, splits on newlines, parses `data:` lines,
and dispatches to the appropriate callback. Pure utility — no React dependency.

---

## API Reference

### `GET /health`
Returns the backend liveness status and number of indexed properties.
```json
{ "status": "ok", "indexed": 27 }
```

### `GET /api/stats`
Returns property counts per data source.
```json
{ "total": 27, "darglobal": 12, "wasalt": 15 }
```

### `POST /api/chat`
Streams a chat response as Server-Sent Events.

**Request:**
```json
{
  "message": "Show me villas in Dubai under $5M",
  "history": [
    { "role": "user",      "content": "previous question" },
    { "role": "assistant", "content": "previous answer"   }
  ]
}
```

**Response stream:**
```
data: {"token": "Here"}
data: {"token": " are"}
data: {"token": " two"}
...
data: [DONE]
```

**Error token:**
```
data: {"error": "All models failed. Please try again."}
data: [DONE]
```

**Rate limit:** 15 requests / minute / IP

### `GET /api/properties`
Browse or search properties.

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default: 1) |
| `limit` | int | Results per page (max: 100) |
| `source` | string | Filter by `darglobal` or `wasalt` |
| `city` | string | Filter by city name |
| `property_type` | string | `apartment`, `villa`, `land`, `commercial` |
| `query` | string | Semantic search query (uses embeddings) |

---

## Configuration Reference

Copy `.env.example` to `.env` and fill in:

```bash
# Required
OPENROUTER_API_KEY=sk-or-...

# Optional – defaults work for local development
SCRAPE_MAX_PAGES=5
CHROMA_HOST=vectordb
CHROMA_PORT=8000
NEXT_PUBLIC_API_URL=http://localhost:8080
APP_URL=http://localhost:3000
APP_TITLE=Real Estate AI Chatbot
```

---

## Security Design

| Concern | Mitigation |
|---------|-----------|
| API key exposure | Stored in `.env` only; never in image layers or source code |
| Prompt injection | Topic guard blocks off-topic input before reaching the LLM |
| LLM hallucination | System prompt instructs model to answer only from provided context |
| Abuse / scraping | Rate limiting: 15 req/min/IP on `/api/chat` via `slowapi` |
| CORS | Restricted to configured `ALLOWED_ORIGINS` |
| Chat history | Never persisted server-side; lives in browser session only |
| Scraper ethics | Respects `robots.txt`; 1–2 req/s rate limiting; public data only |

---

## Deployment

### Local (Docker Compose)

```bash
cp .env.example .env
# Edit .env – set OPENROUTER_API_KEY
docker compose up --build
# Open http://localhost:3000
```

### Production (Railway)

1. Push repo to GitHub
2. Create Railway project → Deploy from GitHub
3. Set `OPENROUTER_API_KEY` and `APP_URL` in Railway environment variables
4. Railway auto-detects `docker-compose.yml` and assigns a public HTTPS URL
5. Update `NEXT_PUBLIC_API_URL` to point to the deployed backend URL

**Startup order is enforced by Docker Compose health checks:**
```
vectordb (healthy) → scraper (completed) → backend (healthy) → frontend
```
