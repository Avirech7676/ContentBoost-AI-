"""
competitor.py — Competitor content analysis for ContentBoost AI.

Changes vs original:
- STOP_WORDS imported from constants (no duplication)
- scrape_url() added: fetch competitor product page from URL
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from collections import Counter

from backend.constants import STOP_WORDS
from backend.seo_analyzer import extract_keywords, _words


# ── Feature pattern extraction ─────────────────────────────────────────────────

FEATURE_PHRASES = [
    r"\b(\w+(?:\s+\w+){0,2})\s+(?:technology|certified|compatible|enabled|proof|resistant|free|grade)\b",
    r"\b(\d+[\w\-]+(?:\s+\w+)?)\b",  # specs: "40-hour", "2TB", "4K"
]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _extract_noun_phrases(text: str) -> List[str]:
    pattern = r"\b([A-Z][a-z]+(?:\s+[A-Za-z]+)?|[a-z]+(?:-[a-z]+)+)\b"
    matches = re.findall(pattern, text)
    return [m for m in matches if len(m) > 4 and m.lower() not in STOP_WORDS]


# ── Core Analysis ──────────────────────────────────────────────────────────────

def analyze_competitor(competitor_content: str) -> Dict[str, Any]:
    """
    Analyze competitor product description text.
    Returns keywords, features, insights, and writing patterns.
    """
    if not competitor_content or not competitor_content.strip():
        return {
            "keywords": [],
            "features": [],
            "insights": [],
            "writing_patterns": [],
            "sentiment": "neutral",
        }

    text = competitor_content.strip()
    words = _words(text)
    sentences = _sentences(text)

    keywords = extract_keywords(text, top_n=12)

    # Feature extraction
    features: List[str] = []
    for pattern in FEATURE_PHRASES:
        matches = re.findall(pattern, text, re.IGNORECASE)
        features.extend([m if isinstance(m, str) else m[0] for m in matches])
    features.extend(_extract_noun_phrases(text)[:6])
    seen: set = set()
    clean_features: List[str] = []
    for f in features:
        fl = f.lower().strip()
        if fl not in seen and len(fl) > 3 and fl not in STOP_WORDS:
            seen.add(fl)
            clean_features.append(f.strip())
    features = clean_features[:8]

    # Writing patterns
    patterns: List[str] = []
    avg_sent_len = len(words) / max(1, len(sentences))
    if avg_sent_len < 15:
        patterns.append("Short, punchy sentences for scanability")
    elif avg_sent_len > 25:
        patterns.append("Detailed, information-rich sentences")
    else:
        patterns.append("Balanced sentence length")

    if re.search(r"\b\d+\b", text):
        patterns.append("Uses specific numbers and metrics for credibility")
    if re.search(r"[•\-\*]\s", text):
        patterns.append("Uses bullet points for feature listing")
    else:
        patterns.append("Prose-format description (no bullet points)")
    if re.search(r"\b(buy|shop|order|get|discover|try|learn|explore)\b", text, re.I):
        patterns.append("Includes explicit call-to-action")
    if re.search(r"\b(enjoy|experience|feel|love|perfect|ideal|designed for)\b", text, re.I):
        patterns.append("Benefit-oriented language (experience / feel / enjoy)")

    # Insights
    insights: List[str] = []
    if keywords:
        insights.append(f"Competitor prioritises keywords: {', '.join(keywords[:4])}")
    if features:
        insights.append(f"Key features highlighted: {', '.join(features[:3])}")
    numbers = re.findall(r"\b\d+[\w%]*\b", text)
    if numbers:
        insights.append(f"Uses quantitative claims (e.g. {', '.join(numbers[:3])})")
    insights.append(f"Description spans {len(sentences)} sentences (~{len(words)} words)")

    return {
        "keywords": keywords,
        "features": features,
        "insights": insights,
        "writing_patterns": patterns,
    }


# ── URL Scraping ───────────────────────────────────────────────────────────────

async def scrape_competitor_url(url: str, timeout: float = 10.0) -> str:
    """
    Fetch a competitor product page and return clean text content.
    Raises ValueError on failure.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("httpx and beautifulsoup4 are required for URL scraping. pip install httpx beautifulsoup4 lxml")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    # Remove boilerplate
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Priority: product description areas, then body
    candidates = (
        soup.find_all(attrs={"class": re.compile(r"product.?(desc|detail|info|content)", re.I)})
        or soup.find_all(["main", "article"])
        or [soup.body]
    )

    texts = []
    for el in candidates:
        if el:
            texts.append(el.get_text(separator=" ", strip=True))

    clean = " ".join(texts)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    # Limit to 5000 chars to stay within prompt limits
    return clean[:5000]


# ── Merge helpers ──────────────────────────────────────────────────────────────

def merge_keywords(
    product_keywords: List[str],
    competitor_keywords: List[str],
    max_total: int = 10,
) -> List[str]:
    """Merge and deduplicate keywords, product keywords take priority."""
    seen: set = set()
    merged: List[str] = []
    for kw in product_keywords + competitor_keywords:
        kl = kw.lower()
        if kl not in seen:
            seen.add(kl)
            merged.append(kw)
    return merged[:max_total]
