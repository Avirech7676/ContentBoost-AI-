"""
models.py — Pydantic request/response models for ContentBoost AI.

Changes vs original:
- max_length guards on all free-text fields (prevents prompt injection / token abuse)
- timezone-aware timestamps (datetime.now(timezone.utc))
- ScrapeRequest model for competitor URL scraping
- RefineRequest now exposes `instruction` max_length
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Request Models ─────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    existing_description: Optional[str] = Field(None, max_length=5000)
    competitor_content: Optional[str] = Field(None, max_length=5000)


class GenerateRequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    existing_description: Optional[str] = Field(None, max_length=5000)
    competitor_content: Optional[str] = Field(None, max_length=5000)
    target_audience: Optional[str] = Field(None, max_length=300)
    tone: Literal["persuasive", "formal", "casual", "technical", "luxury"] = "persuasive"


class RefineRequest(BaseModel):
    version_id: str
    version_type: Literal["seo_version", "marketing_version", "technical_version"]
    instruction: Optional[str] = Field(None, max_length=500)


class ScrapeRequest(BaseModel):
    """Scrape a competitor product page URL and return cleaned text."""
    url: str = Field(..., max_length=2048)


# ── Sub-models ─────────────────────────────────────────────────────────────────

class DescriptionVersion(BaseModel):
    title: str
    description: str


class SEOMetrics(BaseModel):
    readability_score: float = 0.0
    keyword_density: float = 0.0
    title_length: int = 0
    description_length: int = 0
    flesch_score: float = 0.0
    overall_score: float = 0.0


class Suggestion(BaseModel):
    type: Literal["tip", "warn", "error"] = "tip"
    text: str


# ── Response Models ────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    keywords: List[str] = []
    competitor_insights: List[str] = []
    writing_patterns: List[str] = []
    common_features: List[str] = []


class GenerateResponse(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version_number: int = 1
    product_name: str
    tone: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    seo_version: DescriptionVersion
    marketing_version: DescriptionVersion
    technical_version: DescriptionVersion
    keywords: List[str] = []
    competitor_insights: List[str] = []
    seo_metrics: SEOMetrics = Field(default_factory=SEOMetrics)
    suggestions: List[Suggestion] = []


class RefineResponse(BaseModel):
    version_id: str
    version_type: str
    refined_title: str
    refined_description: str


class HistoryEntry(BaseModel):
    version_id: str
    version_number: int
    product_name: str
    tone: str
    timestamp: datetime
    seo_metrics: SEOMetrics
    keywords: List[str] = []
    seo_version: DescriptionVersion
    marketing_version: DescriptionVersion
    technical_version: DescriptionVersion
    suggestions: List[Suggestion] = []
    competitor_insights: List[str] = []


class HistoryResponse(BaseModel):
    total: int
    entries: List[HistoryEntry]


class ScrapeResponse(BaseModel):
    url: str
    content: str
    word_count: int


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ── Auth Models ────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=3, max_length=100)

class Token(BaseModel):
    access_token: str
    token_type: str


# ── Gemini Response Schemas ────────────────────────────────────────────────────
# We define these strictly so they can be passed to Gemini's response_schema.

class SuggestionSchema(BaseModel):
    type: str = Field(description="Must be 'tip', 'warn', or 'error'")
    text: str = Field(description="The actionable improvement suggestion")

class DescriptionVersionSchema(BaseModel):
    title: str = Field(description="The generated title for this version")
    description: str = Field(description="The generated description for this version")

class GenerateResponseSchema(BaseModel):
    keywords: List[str] = Field(description="List of extracted keywords")
    competitor_insights: List[str] = Field(description="List of specific competitor insights")
    seo_version: DescriptionVersionSchema
    marketing_version: DescriptionVersionSchema
    technical_version: DescriptionVersionSchema
    suggestions: List[SuggestionSchema]

