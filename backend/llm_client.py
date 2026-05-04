"""
llm_client.py — Groq API wrapper for ContentBoost AI.

Switched from Google Gemini to Groq (Llama 3.3 70B) for:
- Reliable free-tier quota (14,400 req/day)
- Fast inference
- No billing setup required
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Any, AsyncIterator, Dict

from groq import AsyncGroq
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.constants import FEW_SHOT_SEO_EXAMPLE, TONE_DEFINITIONS
from backend.models import GenerateResponseSchema

# ── Config ─────────────────────────────────────────────────────────────────────

LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "30"))
_MODEL_NAME = "llama-3.3-70b-versatile"
_client: AsyncGroq | None = None

# Simple in-memory TTL cache: {hash -> (result, expires_at)}
_cache: Dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 300  # 5 minutes


# ── Client singleton ───────────────────────────────────────────────────────────

def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key or api_key == "your_groq_api_key_here":
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file (see .env.example). "
                "Get a free key at https://console.groq.com/keys"
            )
        _client = AsyncGroq(api_key=api_key)
    return _client


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Dict[str, Any]:
    """Strip markdown fences and parse JSON robustly."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response. Raw: {raw[:200]}")
    return json.loads(clean[start:end])


def _cache_key(*args: Any) -> str:
    payload = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cache(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    _cache.pop(key, None)
    return None


def _set_cache(key: str, value: Any) -> None:
    _cache[key] = (value, time.time() + _CACHE_TTL)


# ── Retry decorator ────────────────────────────────────────────────────────────

_retry = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)


# ── Async wrapper ──────────────────────────────────────────────────────────────

async def _call_llm_json(prompt: str, response_schema: Any = None) -> Dict[str, Any]:
    """
    Async call to Groq API, enforcing JSON output.
    """
    @_retry
    async def _async_call() -> Dict[str, Any]:
        client = get_client()
        response = await client.chat.completions.create(
            model=_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant. Always respond with valid JSON only. No markdown fences, no extra text outside the JSON object.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.7,
            response_format={"type": "json_object"},
            timeout=LLM_TIMEOUT,
        )
        raw = response.choices[0].message.content
        return _parse_json(raw)

    return await _async_call()


# ── Public Functions ───────────────────────────────────────────────────────────

async def analyze_content(
    product_name: str,
    category: str | None,
    existing_description: str | None,
    competitor_content: str | None,
) -> Dict[str, Any]:
    """
    Analyze product and competitor content.
    Results are cached for 5 minutes to avoid duplicate LLM calls.
    """
    cache_key = _cache_key("analyze", product_name, category, existing_description, competitor_content)
    cached = _get_cache(cache_key)
    if cached:
        return cached

    prompt = f"""You are an expert e-commerce content analyst.

Analyze the following product information and competitor content.

Product: "{product_name}"
Category: {category or "General"}
Existing description: {existing_description or "(none)"}
Competitor content: {competitor_content or "(none)"}

Return ONLY valid JSON — no markdown, no preamble, no trailing text:
{{
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6", "keyword7", "keyword8"],
  "competitor_insights": ["specific insight about competitor strategy 1", "insight 2", "insight 3"],
  "writing_patterns": ["pattern 1", "pattern 2", "pattern 3"],
  "common_features": ["feature 1", "feature 2", "feature 3", "feature 4"]
}}"""

    result = await _call_llm_json(prompt)
    _set_cache(cache_key, result)
    return result


async def generate_descriptions(
    product_name: str,
    category: str | None,
    existing_description: str | None,
    competitor_content: str | None,
    target_audience: str | None,
    tone: str,
) -> Dict[str, Any]:
    """
    Generate 3 optimised product descriptions + suggestions.
    SEO metrics are NOT requested from the LLM (computed locally by seo_analyzer).
    """
    tone_instruction = TONE_DEFINITIONS.get(tone, "")

    prompt = f"""You are ContentBoost AI, an expert e-commerce product description optimizer.

{tone_instruction}

{FEW_SHOT_SEO_EXAMPLE}

Product: "{product_name}"
Category: {category or "General"}
Target audience: {target_audience or "General consumers"}
Existing description: {existing_description or "(none provided)"}
Competitor reference: {competitor_content or "(none provided)"}

Generate exactly this JSON structure — no markdown fences, no extra text outside the JSON:
{{
  "keywords": ["keyword1","keyword2","keyword3","keyword4","keyword5","keyword6","keyword7","keyword8"],
  "competitor_insights": ["specific insight 1","insight 2","insight 3"],
  "seo_version": {{
    "title": "SEO optimised title under 70 chars, front-load primary keyword",
    "description": "150-200 word SEO description. Natural keyword placement (1.5-2.5%). Benefit-first structure. Active voice. Clear call-to-action at the end. Cover core features, key benefits, and use case."
  }},
  "marketing_version": {{
    "title": "Emotionally compelling headline that creates desire",
    "description": "150-200 word marketing description. Lifestyle transformation, emotional benefits, sensory language, social proof cues, aspirational outcomes. Apply the tone defined above throughout."
  }},
  "technical_version": {{
    "title": "Technical product title with key spec or differentiator",
    "description": "150-200 word technical description. Lead with specifications, materials, performance metrics, compatibility, certifications, and precise technical language."
  }},
  "suggestions": [
    {{"type": "tip", "text": "Actionable improvement suggestion 1"}},
    {{"type": "tip", "text": "Actionable improvement suggestion 2"}},
    {{"type": "warn", "text": "Something to watch out for"}}
  ]
}}"""

    return await _call_llm_json(prompt)


async def refine_description(
    version_type: str,
    current_title: str,
    current_description: str,
    instruction: str | None = None,
) -> Dict[str, str]:
    """
    Refine a specific product description version.
    Returns improved title and description.
    """
    focus_map = {
        "seo_version": "SEO optimization: improve keyword placement, clarity, and search ranking potential",
        "marketing_version": "marketing impact: increase emotional appeal, desire, and conversion potential",
        "technical_version": "technical precision: enhance spec coverage, accuracy, and professional tone",
    }
    focus = focus_map.get(version_type, "overall quality")
    extra = f"\n\nSpecific instruction from user: {instruction}" if instruction else ""

    prompt = f"""You are an expert e-commerce copywriter. Refine the following product description with focus on {focus}.{extra}

Current title: "{current_title}"
Current description:
"{current_description}"

Return ONLY valid JSON — no markdown:
{{
  "title": "improved title here",
  "description": "improved description here, same approximate length as original"
}}"""

    return await _call_llm_json(prompt)


# ── Streaming generator ────────────────────────────────────────────────────────

async def generate_descriptions_stream(
    product_name: str,
    category: str | None,
    existing_description: str | None,
    competitor_content: str | None,
    target_audience: str | None,
    tone: str,
) -> AsyncIterator[tuple[str, Any]]:
    """
    Async generator that yields (event_name, data) tuples for SSE streaming.
    Yields actual token chunks as they arrive from Groq.
    """
    yield ("status", {"step": 1, "message": "Analysing product & competitor content…"})

    tone_instruction = TONE_DEFINITIONS.get(tone, "")
    prompt = f"""You are ContentBoost AI, an expert e-commerce product description optimizer.

{tone_instruction}

{FEW_SHOT_SEO_EXAMPLE}

Product: "{product_name}"
Category: {category or "General"}
Target audience: {target_audience or "General consumers"}
Existing description: {existing_description or "(none provided)"}
Competitor reference: {competitor_content or "(none provided)"}

Generate exactly this JSON structure — no markdown fences, no extra text outside the JSON:
{{
  "keywords": ["keyword1","keyword2","keyword3","keyword4","keyword5","keyword6","keyword7","keyword8"],
  "competitor_insights": ["specific insight 1","insight 2","insight 3"],
  "seo_version": {{
    "title": "SEO optimised title under 70 chars, front-load primary keyword",
    "description": "150-200 word SEO description. Natural keyword placement (1.5-2.5%). Benefit-first structure. Active voice. Clear call-to-action at the end. Cover core features, key benefits, and use case."
  }},
  "marketing_version": {{
    "title": "Emotionally compelling headline that creates desire",
    "description": "150-200 word marketing description. Lifestyle transformation, emotional benefits, sensory language, social proof cues, aspirational outcomes. Apply the tone defined above throughout."
  }},
  "technical_version": {{
    "title": "Technical product title with key spec or differentiator",
    "description": "150-200 word technical description. Lead with specifications, materials, performance metrics, compatibility, certifications, and precise technical language."
  }},
  "suggestions": [
    {{"type": "tip", "text": "Actionable improvement suggestion 1"}},
    {{"type": "tip", "text": "Actionable improvement suggestion 2"}},
    {{"type": "warn", "text": "Something to watch out for"}}
  ]
}}"""

    client = get_client()

    yield ("status", {"step": 2, "message": "Generating optimized content..."})

    stream = await client.chat.completions.create(
        model=_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful AI assistant. Always respond with valid JSON only. No markdown fences, no extra text outside the JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.7,
        stream=True,
        timeout=LLM_TIMEOUT,
    )

    full_text = ""
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_text += delta
            yield ("chunk", {"text": delta})

    yield ("status", {"step": 3, "message": "Saving to history…"})

    llm_data = _parse_json(full_text)
    yield ("result", llm_data)
