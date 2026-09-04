# Real Estate AI Chatbot – DarGlobal & Wasalt

An AI-powered property search chatbot that scrapes listings from **DarGlobal** (international luxury real estate) and **Wasalt** (Saudi Arabia's leading property marketplace), then lets users query them in natural language.

> **Live URL:** *(add after deployment)*

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Compose                        │
│                                                             │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────┐  │
│  │  Scraper     │──▶│  Backend (FastAPI)│◀──│ Frontend   │  │
│  │  (Python)    │   │  + RAG pipeline   │   │ (Next.js)  │  │
│  └──────────────┘   └────────┬─────────┘   └────────────┘  │
│                              │                              │
│                    ┌─────────▼─────────┐                   │
│                    │  ChromaDB (vector) │                   │
│                    └───────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  OpenRouter API    │
                    │  (free LLM models) │
                    └───────────────────┘
```

**Tech Stack**
| Layer | Technology |
|-------|-----------|
| Scraper | Python + httpx + BeautifulSoup4 + Playwright |
| Backend | FastAPI + Python 3.12 |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local, free) |
| Vector DB | ChromaDB (persistent) |
| LLM | OpenRouter (free tier: Llama 3.1 8B, Mistral 7B) |
| Frontend | Next.js 14 + Tailwind CSS |
| Container | Docker Compose v2 |
| Deployment | Railway |

---

## Quick Start (Local)

### Prerequisites
- Docker & Docker Compose v2
- An [OpenRouter](https://openrouter.ai) API key (free, no credit card)

### 1. Clone & configure
```bash
git clone <repo-url>
cd real-estate-chatbot
cp .env.example .env
```

Edit `.env` and set your key:
```
OPENROUTER_API_KEY=sk-or-...
```

### 2. Run
```bash
docker compose up --build
```

This will:
1. Start ChromaDB
2. Run the scraper (DarGlobal + Wasalt) – writes to shared volume
3. Start the backend (FastAPI) – ingests data into ChromaDB on startup
4. Start the frontend (Next.js) – available at **http://localhost:3000**

First build takes ~5–10 minutes (downloads ML model, installs deps).  
Subsequent starts are fast (data is cached in Docker volumes).

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | ✅ | – | Your OpenRouter API key |
| `SCRAPE_MAX_PAGES` | ❌ | `5` | Max pages per scraper (reduce for faster dev) |
| `NEXT_PUBLIC_API_URL` | ❌ | `http://localhost:8080` | Backend URL for the frontend |
| `CHROMA_HOST` | ❌ | `vectordb` | ChromaDB hostname |
| `CHROMA_PORT` | ❌ | `8000` | ChromaDB port |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + indexed count |
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

1. Push to GitHub
2. Create a new Railway project → **Deploy from GitHub repo**
3. Railway auto-detects `docker-compose.yml`
4. Set environment variable: `OPENROUTER_API_KEY=sk-or-...`
5. Deploy → Railway provides a public HTTPS URL

---

## Data Sources

- **DarGlobal** (`darglobal.co.uk`) – International luxury real estate developer with properties in UAE, UK, Saudi Arabia, Oman, Qatar, and Spain. Brand collaborations include Aston Martin, Lamborghini, Dolce & Gabbana, and Trump.
- **Wasalt** (`wasalt.com`) – Saudi Arabia's leading property portal with thousands of residential, commercial, and land listings across Riyadh, Jeddah, Dammam, and other cities.

*Note: The scraper collects only publicly available listing data. If live scraping is blocked, the system falls back to a curated sample dataset representing real property types from each source.*

---

## Security

- API key stored in `.env`, never committed
- CORS restricted to frontend origin in production
- Rate limiting on `/api/chat`: 15 requests/minute per IP
- No user data is persisted; chat history lives in browser session only
- Scrapers respect `robots.txt` and use conservative rate limits (1–2 req/s)
