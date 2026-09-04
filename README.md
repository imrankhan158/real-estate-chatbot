# Real Estate AI Chatbot – DarGlobal & Wasalt

An AI-powered property search chatbot that scrapes listings from **DarGlobal** (international luxury real estate) and **Wasalt** (Saudi Arabia's leading property marketplace), then lets users query them in natural language.

> **Live URL: https://darglobal.up.railway.app/

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      Docker Compose                      │
│                                                          │
│  ┌──────────────┐   ┌──────────────────┐  ┌──────────┐   │
│  │  Scraper     │──▶│ Backend (FastAPI)│◀─│ Frontend│    │
│  │  (Python)    │   │  + RAG pipeline  │  │ Next.js  │   │
│  └──────────────┘   └────────┬─────────┘  └──────────┘   │
└────────────────────────────  │  ─────────────────────────┘
                               │ HTTPS
               ┌───────────────┴──────────────┐
               │                              │
   ┌───────────▼──────────┐      ┌────────────▼────────┐
   │  Pinecone (cloud)    │      │  OpenRouter API     │
   │  Serverless Vector DB│      │  (free LLM models)  │
   └──────────────────────┘      └─────────────────────┘
```

**Tech Stack**

| Layer | Technology |
|-------|-----------|
| Scraper | Python + httpx + BeautifulSoup4 + Playwright |
| Backend | FastAPI + Python 3.12 |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local, free) |
| Vector DB | **Pinecone** (serverless, cloud) |
| LLM | OpenRouter – free tier (Gemma 4, Nemotron, MiniMax) |
| Frontend | Next.js **16** + React 19 + Tailwind CSS |
| Container | Docker Compose v2 |
| Deployment | Railway |

---

## Quick Start (Local)

### Prerequisites
- Docker & Docker Compose v2
- [OpenRouter](https://openrouter.ai) API key (free, no credit card)
- [Pinecone](https://pinecone.io) API key (free Starter plan)

### 1. Clone & configure
```bash
git clone <repo-url>
cd real-estate-chatbot
cp .env.example .env
```

Edit `.env` and set your keys:
```env
OPENROUTER_API_KEY=sk-or-...
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=real-estate
```

### 2. Run
```bash
docker compose up --build
```

This will:
1. Run the scraper (DarGlobal + Wasalt) – writes JSON to `./data/`
2. Start the backend (FastAPI) – embeds properties and upserts to Pinecone on startup
3. Start the frontend (Next.js) – available at **http://localhost:3000**

First build takes ~5–10 minutes (downloads ML model, installs deps).
Subsequent starts are fast — Pinecone skips re-ingestion if vectors already exist.

---

## Re-running the Scraper

To force a fresh scrape and re-ingest:

```bash
# 1. Delete cached data files
rm -f data/darglobal.json data/wasalt.json

# 2. Re-run the scraper
docker compose run --rm scraper

# 3. Restart the backend to re-ingest into Pinecone
docker compose up -d --no-deps backend
```

> The scraper respects `SCRAPE_MAX_PAGES` (default: 5). Increase it in `.env` for more listings.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | ✅ | – | OpenRouter API key for LLM |
| `PINECONE_API_KEY` | ✅ | – | Pinecone API key |
| `PINECONE_INDEX_NAME` | ❌ | `real-estate` | Pinecone index name |
| `SCRAPE_MAX_PAGES` | ❌ | `5` | Max listing pages per scraper |
| `NEXT_PUBLIC_API_URL` | ❌ | `http://localhost:8080` | Backend URL for the frontend |
| `APP_URL` | ❌ | `http://localhost:3000` | Your app URL (OpenRouter attribution) |
| `APP_TITLE` | ❌ | `Real Estate AI Chatbot` | App title (OpenRouter attribution) |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + indexed vector count |
| `GET` | `/api/stats` | Property counts per source |
| `POST` | `/api/chat` | Chat (SSE streaming) |
| `GET` | `/api/properties` | Browse/search properties |

### Chat request example
```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me villas in Dubai under $5M"}' \
  --no-buffer
```

---

## Deployment (Railway)

1. Push repo to GitHub
2. Create a new Railway project → **Deploy from GitHub repo**
3. Railway auto-detects `docker-compose.yml`
4. Set environment variables in Railway dashboard:
   - `OPENROUTER_API_KEY`
   - `PINECONE_API_KEY`
   - `PINECONE_INDEX_NAME`
   - `APP_URL` ← set to your Railway public URL
5. Deploy → Railway provides a public HTTPS URL

**Startup order:**
```
scraper (completed) → backend (healthy) → frontend
```

---

## Data Sources

- **DarGlobal** (`darglobal.co.uk`) – International luxury developer with properties in UAE, UK, Saudi Arabia, Oman, Qatar, and Spain. Brands include Aston Martin, Lamborghini, Dolce & Gabbana, and Trump.
- **Wasalt** (`wasalt.com`) – Saudi Arabia's leading property portal with residential, commercial, and land listings across Riyadh, Jeddah, Dammam, and more.

*If live scraping is blocked, the system automatically falls back to a curated sample dataset representing real property types from each source.*

---

## Security

- API keys stored in `.env` only — never in image layers or source code
- Topic guard (`guard.py`) blocks all non-real-estate questions before they reach the LLM
- CORS restricted to configured `ALLOWED_ORIGINS` in production
- Rate limiting on `/api/chat`: 15 requests/minute per IP
- Chat history never persisted server-side — lives in browser session only
- Scrapers respect `robots.txt` with 1–2 req/s rate limiting
