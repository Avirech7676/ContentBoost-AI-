# ContentBoost AI — Product Optimization Engine v2.0

An AI-powered e-commerce product description optimizer using Google Gemini,
competitor analysis, SEO scoring, streaming generation, and version memory.

---

## Features

- **3 AI-generated versions** per product: SEO-optimized, Marketing-focused, Technical
- **Competitor content analysis** — keyword extraction, feature identification, style patterns
- **Competitor URL scraper** — paste a URL and auto-extract competitor text
- **SEO scoring** — readability, keyword density (corrected), title length, Flesch score
- **Memento memory system** — SQLite-backed version history with iterative improvement tracking
- **Real SSE streaming** — genuine server-side progress events (not fake timers)
- **Compare view** — pick any two saved versions via dropdown, view both SEO + Marketing
- **Tone selector** — persuasive, formal, casual, technical, luxury (with full AI tone definitions)
- **Refinement with instruction** — guide the AI refiner ("make it shorter", "add urgency")
- **Export** — download optimized descriptions as `.txt`
- **Rate limiting** — per-IP request cap (configurable)
- **REST API** — `/analyze`, `/generate`, `/generate/stream`, `/refine`, `/scrape`, `/history`, `/export`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| LLM | Google Gemini API (`gemini-1.5-flash`) |
| Memory | Async SQLite via `aiosqlite` |
| SEO Analysis | Custom Python scoring (textstat + fixed keyword density) |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Security | DOMPurify (XSS), input max_length, rate limiting (slowapi) |
| Resilience | Tenacity retry + exponential backoff, LLM timeout |

---

## Project Structure

```
contentboost-ai/
├── backend/
│   ├── main.py              # FastAPI app, all routes, rate limiting
│   ├── llm_client.py        # Gemini API wrapper (async, retry, cache, streaming)
│   ├── database.py          # NEW: async SQLite persistence layer
│   ├── memory.py            # Thin async facade over database.py
│   ├── seo_analyzer.py      # SEO scoring engine (fixed keyword density)
│   ├── competitor.py        # Competitor analysis + URL scraping
│   ├── constants.py         # NEW: shared STOP_WORDS, tone definitions, few-shot examples
│   └── models.py            # Pydantic models (max_length, timezone-aware timestamps)
├── frontend/
│   ├── templates/
│   │   └── index.html       # SPA (DOMPurify CDN, refinement input, URL scraper)
│   └── static/
│       ├── css/style.css    # Styles (spinner, refine row, compare dropdowns)
│       └── js/
│           ├── app.js       # Core logic (real SSE progress, Gemini error messages)
│           ├── api.js       # API client (generateStream, scrape methods)
│           └── ui.js        # Rendering (DOMPurify sanitisation, compare dropdowns)
├── data/
│   └── contentboost.db      # Auto-created SQLite DB (gitignored)
├── .env.example             # Environment variable template
├── .gitignore               # Ignores .env and DB files
└── requirements.txt
```

---

## Setup & Installation

### 1. Clone / download the project

```bash
cd contentboost-ai
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Edit `.env` and add your **Gemini API key**:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Get your free key at: **https://aistudio.google.com/app/apikey**

> ⚠️ **Never commit `.env` to version control.** It is already listed in `.gitignore`.

### 5. Run the server

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open the app

Visit: [http://localhost:8000](http://localhost:8000)

The SQLite database is created automatically at `data/contentboost.db` on first run.

---

## API Reference

### `POST /analyze`
Analyze product and extract competitor insights (cached 5 min).

### `POST /generate`
Generate 3 optimised descriptions. SEO metrics computed locally (not by LLM).

### `POST /generate/stream`
Same as `/generate` but streams real server-side SSE progress events.

### `POST /scrape`
```json
{ "url": "https://competitor.com/product-page" }
```
Returns cleaned competitor page text (up to 5000 chars). Use `content` as `competitor_content` in `/generate`.

### `POST /refine`
```json
{
  "version_id": "uuid",
  "version_type": "seo_version",
  "instruction": "make it shorter and add more urgency"
}
```

### `GET /history` · `GET /history/{product_name}`
Version history, newest first.

### `DELETE /history/{version_id}`
Delete a version.

### `GET /export/{version_id}`
Download as `.txt`.

### `GET /health`
```json
{ "status": "ok", "version": "2.0.0", "db": "data/contentboost.db" }
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API key | **Yes** |
| `HOST` | Server host (default: `0.0.0.0`) | No |
| `PORT` | Server port (default: `8000`) | No |
| `DB_FILE` | SQLite DB path (default: `data/contentboost.db`) | No |
| `MAX_HISTORY_PER_PRODUCT` | Max versions per product (default: `50`) | No |
| `LLM_TIMEOUT` | Gemini call timeout in seconds (default: `30`) | No |
| `RATE_LIMIT` | Max requests per minute per IP (default: `20`) | No |

---

## What Changed in v2.0

| Area | Fix |
|---|---|
| 🔐 Security | Hardcoded API key removed; `.gitignore` added; `max_length` on all inputs |
| ⚡ Performance | LLM calls are non-blocking (async via `run_in_executor`); tenacity retry; analyze cache |
| 🗄️ Storage | JSON flat-file replaced with async SQLite (multi-worker safe, indexed) |
| 📡 Streaming | Real SSE endpoint — progress reflects actual server processing, not fake timers |
| 🔎 SEO | Keyword density formula fixed (per-keyword average, not inflated sum) |
| 🛡️ XSS | DOMPurify sanitises all LLM output before `innerHTML` insertion |
| 🤖 Prompts | Tone definitions added; few-shot example included; fake SEO metrics removed from prompt |
| 🔗 Scraping | `POST /scrape` accepts competitor URL and extracts clean text via httpx + BeautifulSoup |
| 🎛️ Compare | Dropdown selectors for any 2 history versions; shows both SEO and Marketing versions |
| ✏️ Refine | Instruction text field per result card — guide the AI refiner |
| ⏱️ Timestamps | Timezone-aware UTC datetimes throughout; frontend parses correctly |
| 🚦 Rate Limiting | Per-IP cap via slowapi; scrape endpoint has stricter 10/min limit |
