"""
main.py — FastAPI application entry point for ContentBoost AI.

Improvements vs original:
- lifespan() replaces deprecated @app.on_event("startup")
- All memory/LLM calls are properly awaited (async-safe)
- Rate limiting via slowapi
- /generate/stream — real SSE endpoint with server-side progress events
- /scrape — competitor URL scraping endpoint
- Version number derived from DB max (survives restarts)
- Structured error handling throughout
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend import database, llm_client, seo_analyzer, auth
from backend import competitor as comp_module
from backend import memory
from backend.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DescriptionVersion,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    HistoryEntry,
    HistoryResponse,
    RefineRequest,
    RefineResponse,
    ScrapeRequest,
    ScrapeResponse,
    SEOMetrics,
    Suggestion,
    UserCreate,
    Token,
)
import aiosqlite
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
import time

logger.add("logs/api.log", rotation="10 MB", retention="7 days", level="INFO")

# ── Rate limiter ───────────────────────────────────────────────────────────────

_RATE_LIMIT = os.getenv("RATE_LIMIT", "20")
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{_RATE_LIMIT}/minute"])


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB and NLP models on startup."""
    await database.init_db()
    
    # Pre-download NLTK data
    import nltk
    try:
        nltk.download("punkt", quiet=True)
    except Exception as e:
        logger.warning(f"Failed to download NLTK data: {e}")
        
    logger.info("Server started — database ready")
    yield
    logger.info("Server shutting down")


# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ContentBoost AI",
    description="AI-powered e-commerce product description optimizer",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    return response

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend" / "templates"))


# ── Frontend ───────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_seo_metrics(llm_data: dict, seo_title: str, seo_desc: str, keywords: list) -> tuple[SEOMetrics, list[Suggestion]]:
    """Compute real SEO metrics locally; merge with LLM suggestions."""
    recalc = seo_analyzer.analyze(seo_title, seo_desc, keywords)

    metrics = SEOMetrics(
        readability_score=recalc.get("readability_score", 0),
        keyword_density=recalc.get("keyword_density", 0),
        title_length=recalc.get("title_length", 0),
        description_length=recalc.get("description_length", 0),
        flesch_score=recalc.get("flesch_score", 0),
        overall_score=recalc.get("overall_score", 0),
    )

    all_suggestions = []
    for s in llm_data.get("suggestions", []):
        all_suggestions.append(Suggestion(type=s.get("type", "tip"), text=s.get("text", "")))
    for s in recalc.get("suggestions", []):
        all_suggestions.append(Suggestion(type=s.get("type", "tip"), text=s.get("text", "")))

    return metrics, all_suggestions[:6]


# ── Auth Routes ────────────────────────────────────────────────────────────────

@app.post("/register", response_model=Token, tags=["Auth"])
async def register(user: UserCreate):
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute("SELECT id FROM users WHERE username = ?", (user.username,)) as cur:
                if await cur.fetchone():
                    raise HTTPException(status_code=400, detail="Username already registered")
            
            user_id = str(uuid.uuid4())
            hashed_pw = auth.get_password_hash(user.password)
            await db.execute("INSERT INTO users (id, username, hashed_password) VALUES (?, ?, ?)", 
                             (user_id, user.username, hashed_pw))
            await db.commit()
            
        access_token = auth.create_access_token(data={"sub": user_id})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, hashed_password FROM users WHERE username = ?", (form_data.username,)) as cur:
            user = await cur.fetchone()
            
    if not user or not auth.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = auth.create_access_token(data={"sub": user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}


# ── API Routes ─────────────────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
@limiter.limit(f"{_RATE_LIMIT}/minute")
async def analyze(req: AnalyzeRequest, request: Request, user_id: str = Depends(auth.get_current_user_id)):
    """
    Analyze product and competitor content.
    Short-circuits if no meaningful input is provided.
    Results cached for 5 minutes.
    """
    has_input = req.existing_description or req.competitor_content
    if not has_input:
        # Return empty analysis without burning an LLM call
        return AnalyzeResponse()

    try:
        local = comp_module.analyze_competitor(req.competitor_content or "")
        llm_result = await llm_client.analyze_content(
            product_name=req.product_name,
            category=req.category,
            existing_description=req.existing_description,
            competitor_content=req.competitor_content,
        )
        keywords = comp_module.merge_keywords(
            llm_result.get("keywords", []),
            local.get("keywords", []),
            max_total=10,
        )
        return AnalyzeResponse(
            keywords=keywords,
            competitor_insights=llm_result.get("competitor_insights", local.get("insights", [])),
            writing_patterns=llm_result.get("writing_patterns", local.get("writing_patterns", [])),
            common_features=llm_result.get("common_features", local.get("features", [])),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@app.post("/generate", response_model=GenerateResponse, tags=["Generation"])
@limiter.limit(f"{_RATE_LIMIT}/minute")
async def generate(req: GenerateRequest, request: Request, user_id: str = Depends(auth.get_current_user_id)):
    """
    Generate three optimised product descriptions (SEO, Marketing, Technical)
    plus SEO metrics and improvement suggestions.
    """
    try:
        # Use DB max version number (survives server restarts)
        version_number = await memory.get_version_count(user_id, req.product_name) + 1

        llm_data = await llm_client.generate_descriptions(
            product_name=req.product_name,
            category=req.category,
            existing_description=req.existing_description,
            competitor_content=req.competitor_content,
            target_audience=req.target_audience,
            tone=req.tone,
        )

        seo_title = llm_data.get("seo_version", {}).get("title", "")
        seo_desc = llm_data.get("seo_version", {}).get("description", "")
        keywords = llm_data.get("keywords", [])

        metrics, suggestions = _build_seo_metrics(llm_data, seo_title, seo_desc, keywords)

        response = GenerateResponse(
            version_id=str(uuid.uuid4()),
            version_number=version_number,
            product_name=req.product_name,
            tone=req.tone,
            timestamp=datetime.now(timezone.utc),
            seo_version=DescriptionVersion(**llm_data.get("seo_version", {"title": "", "description": ""})),
            marketing_version=DescriptionVersion(**llm_data.get("marketing_version", {"title": "", "description": ""})),
            technical_version=DescriptionVersion(**llm_data.get("technical_version", {"title": "", "description": ""})),
            keywords=keywords,
            competitor_insights=llm_data.get("competitor_insights", []),
            seo_metrics=metrics,
            suggestions=suggestions,
        )

        await memory.save_version(user_id, response)
        return response

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@app.post("/generate/stream", tags=["Generation"])
@limiter.limit(f"{_RATE_LIMIT}/minute")
async def generate_stream(req: GenerateRequest, request: Request, user_id: str = Depends(auth.get_current_user_id)):
    """
    SSE endpoint — streams real server-side progress events then the final result.
    Frontend connects with EventSource or fetch+ReadableStream.
    """
    async def event_gen():
        try:
            async for event_name, data in llm_client.generate_descriptions_stream(
                product_name=req.product_name,
                category=req.category,
                existing_description=req.existing_description,
                competitor_content=req.competitor_content,
                target_audience=req.target_audience,
                tone=req.tone,
            ):
                if event_name == "result":
                    # Build full response and save
                    llm_data = data
                    version_number = await memory.get_version_count(user_id, req.product_name) + 1
                    seo_title = llm_data.get("seo_version", {}).get("title", "")
                    seo_desc = llm_data.get("seo_version", {}).get("description", "")
                    keywords = llm_data.get("keywords", [])
                    metrics, suggestions = _build_seo_metrics(llm_data, seo_title, seo_desc, keywords)

                    response = GenerateResponse(
                        version_id=str(uuid.uuid4()),
                        version_number=version_number,
                        product_name=req.product_name,
                        tone=req.tone,
                        timestamp=datetime.now(timezone.utc),
                        seo_version=DescriptionVersion(**llm_data.get("seo_version", {"title": "", "description": ""})),
                        marketing_version=DescriptionVersion(**llm_data.get("marketing_version", {"title": "", "description": ""})),
                        technical_version=DescriptionVersion(**llm_data.get("technical_version", {"title": "", "description": ""})),
                        keywords=keywords,
                        competitor_insights=llm_data.get("competitor_insights", []),
                        seo_metrics=metrics,
                        suggestions=suggestions,
                    )
                    await memory.save_version(user_id, response)

                    payload = json.dumps({"event": "done", "data": response.model_dump(mode="json")})
                    yield f"data: {payload}\n\n"
                else:
                    payload = json.dumps({"event": event_name, **data})
                    yield f"data: {payload}\n\n"

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            err = json.dumps({"event": "error", "message": f"AI Generation failed: {str(e)}"})
            yield f"data: {err}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/scrape", response_model=ScrapeResponse, tags=["Analysis"])
@limiter.limit("10/minute")
async def scrape(req: ScrapeRequest, request: Request):
    """
    Scrape a competitor product page URL and return cleaned text.
    Use the returned `content` as competitor_content in /generate.
    """
    try:
        content = await comp_module.scrape_competitor_url(req.url)
        return ScrapeResponse(
            url=req.url,
            content=content,
            word_count=len(content.split()),
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Scrape failed: {e}")


@app.post("/refine", response_model=RefineResponse, tags=["Generation"])
@limiter.limit(f"{_RATE_LIMIT}/minute")
async def refine(req: RefineRequest, request: Request, user_id: str = Depends(auth.get_current_user_id)):
    """Refine a specific version of a saved product description using AI."""
    entry = await memory.get_version(user_id, req.version_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Version '{req.version_id}' not found")

    ver_map = {
        "seo_version": entry.seo_version,
        "marketing_version": entry.marketing_version,
        "technical_version": entry.technical_version,
    }
    ver_data = ver_map.get(req.version_type)
    if not ver_data:
        raise HTTPException(status_code=400, detail=f"Invalid version_type '{req.version_type}'")

    try:
        result = await llm_client.refine_description(
            version_type=req.version_type,
            current_title=ver_data.title,
            current_description=ver_data.description,
            instruction=req.instruction,
        )
        new_title = result.get("title", ver_data.title)
        new_desc = result.get("description", ver_data.description)

        await memory.update_version_content(
            user_id=user_id,
            version_id=req.version_id,
            version_type=req.version_type,
            new_title=new_title,
            new_description=new_desc,
        )

        return RefineResponse(
            version_id=req.version_id,
            version_type=req.version_type,
            refined_title=new_title,
            refined_description=new_desc,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {e}")


@app.get("/history", response_model=HistoryResponse, tags=["History"])
async def get_all_history(limit: int = Query(default=50, le=200), user_id: str = Depends(auth.get_current_user_id)):
    """Get all stored product description versions, newest first."""
    entries = await memory.get_all_history(user_id, limit=limit)
    return HistoryResponse(total=len(entries), entries=entries)


@app.get("/history/{product_name}", response_model=HistoryResponse, tags=["History"])
async def get_product_history(product_name: str, user_id: str = Depends(auth.get_current_user_id)):
    """Get all versions for a specific product, newest first."""
    entries = await memory.get_product_history(user_id, product_name)
    return HistoryResponse(total=len(entries), entries=entries)


@app.delete("/history/{version_id}", tags=["History"])
async def delete_version(version_id: str, user_id: str = Depends(auth.get_current_user_id)):
    """Delete a specific version from history."""
    success = await memory.delete_version(user_id, version_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found")
    return {"deleted": True, "version_id": version_id}


@app.get("/export/{version_id}", response_class=PlainTextResponse, tags=["Export"])
async def export_version(version_id: str, user_id: str = Depends(auth.get_current_user_id)):
    """Export a version as plain text."""
    entry = await memory.get_version(user_id, version_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found")

    ts_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "=" * 60,
        "ContentBoost AI — Product Description Export",
        "=" * 60,
        f"Product:   {entry.product_name}",
        f"Version:   {entry.version_number}",
        f"Tone:      {entry.tone}",
        f"Generated: {ts_str}",
        f"SEO Score: {entry.seo_metrics.overall_score}/100",
        "",
        "─" * 60,
        "SEO OPTIMISED VERSION",
        "─" * 60,
        f"Title: {entry.seo_version.title}",
        "",
        entry.seo_version.description,
        "",
        "─" * 60,
        "MARKETING VERSION",
        "─" * 60,
        f"Title: {entry.marketing_version.title}",
        "",
        entry.marketing_version.description,
        "",
        "─" * 60,
        "TECHNICAL VERSION",
        "─" * 60,
        f"Title: {entry.technical_version.title}",
        "",
        entry.technical_version.description,
        "",
        "─" * 60,
        "KEYWORDS",
        "─" * 60,
        ", ".join(entry.keywords),
        "",
        "─" * 60,
        "SEO METRICS",
        "─" * 60,
        f"Readability Score: {entry.seo_metrics.readability_score}",
        f"Keyword Density:   {entry.seo_metrics.keyword_density}%",
        f"Title Length:      {entry.seo_metrics.title_length} chars",
        f"Description Words: {entry.seo_metrics.description_length}",
        f"Flesch Score:      {entry.seo_metrics.flesch_score}",
        f"Overall SEO Score: {entry.seo_metrics.overall_score}/100",
        "=" * 60,
    ]
    content = "\n".join(lines)
    filename = f"contentboost-{entry.product_name.replace(' ', '-').lower()}-v{entry.version_number}.txt"
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0", "db": str(database.DB_PATH)}
