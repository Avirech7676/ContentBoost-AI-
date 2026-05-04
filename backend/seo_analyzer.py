"""
seo_analyzer.py — SEO scoring and analysis engine for ContentBoost AI.

Fixes vs original:
- keyword_density now computes per-keyword average (no more inflated totals)
- STOP_WORDS imported from constants (single source of truth)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

from backend.constants import STOP_WORDS

try:
    import nltk
    from nltk.stem.snowball import SnowballStemmer
    # We use english stemmer
    _stemmer = SnowballStemmer("english")
    HAS_NLTK = True
except ImportError:
    HAS_NLTK = False
    _stemmer = None

try:
    import textstat
    HAS_TEXTSTAT = True
except ImportError:
    HAS_TEXTSTAT = False


# ── Text helpers ───────────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len(text.split())


def _clean(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower())


def _words(text: str) -> List[str]:
    return _clean(text).split()


# ── Core Metrics ───────────────────────────────────────────────────────────────

def flesch_reading_ease(text: str) -> float:
    """Flesch Reading Ease score (0–100, higher = easier to read)."""
    if HAS_TEXTSTAT:
        return round(textstat.flesch_reading_ease(text), 1)
    # Fallback manual calculation
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    words = _word_count(text)
    if words == 0:
        return 0.0
    syllables = sum(_count_syllables(w) for w in text.split())
    score = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    return round(max(0.0, min(100.0, score)), 1)


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".,!?;:")
    if not word:
        return 0
    vowels = "aeiouy"
    count, prev_vowel = 0, False
    for char in word:
        is_v = char in vowels
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def readability_score(text: str) -> float:
    """Combined readability score 0–100."""
    if not text:
        return 0.0
    flesch = flesch_reading_ease(text)
    words = _word_count(text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    avg_sent_len = words / sentences
    sentence_score = max(0.0, min(100.0, 100 - max(0, (avg_sent_len - 20) * 2)))
    avg_word_len = sum(len(w) for w in text.split()) / max(1, words)
    word_score = max(0.0, min(100.0, 100 - max(0, (avg_word_len - 5) * 10)))
    return round(flesch * 0.5 + sentence_score * 0.3 + word_score * 0.2, 1)


def keyword_density(text: str, keywords: List[str]) -> float:
    """
    Average keyword density as a percentage.

    FIX: compute density per keyword, then average across all keywords.
    Old approach summed all hits together → artificially inflated values.
    """
    if not text or not keywords:
        return 0.0
    words = _words(text)
    total = len(words)
    if total == 0:
        return 0.0

    stemmed_words = [_stemmer.stem(w) for w in words] if _stemmer else words

    per_kw = []
    for kw in keywords:
        kw_words = _words(kw)  # handle multi-word keywords
        
        if len(kw_words) == 1:
            if _stemmer:
                kw_stem = _stemmer.stem(kw_words[0])
                count = stemmed_words.count(kw_stem)
            else:
                count = words.count(kw_words[0])
        else:
            # multi-word: count occurrences as phrase
            # For simplicity, we match the exact clean phrase even with stemmer,
            # but we could stem the entire phrase if needed.
            phrase = " ".join(kw_words)
            clean_text = " ".join(words)
            count = clean_text.count(phrase)
            
        per_kw.append((count / total) * 100)

    return round(sum(per_kw) / len(per_kw), 2)


def title_score(title: str) -> Dict[str, Any]:
    """Score a product title."""
    length = len(title)
    wc = _word_count(title)
    score = 100.0
    issues = []
    if length > 70:
        score -= 20
        issues.append("Title exceeds 70 characters — may be truncated in search results")
    if length < 20:
        score -= 15
        issues.append("Title is very short — add more descriptive keywords")
    if wc < 3:
        score -= 10
        issues.append("Title has too few words")
    return {"length": length, "word_count": wc, "score": round(score, 1), "issues": issues}


def description_score(description: str) -> Dict[str, Any]:
    """Score a product description."""
    wc = _word_count(description)
    score = 100.0
    issues = []
    if wc < 100:
        score -= 25
        issues.append("Description is too short — aim for 150–200 words")
    elif wc < 150:
        score -= 10
        issues.append("Description could be slightly longer for better SEO coverage")
    if wc > 300:
        score -= 10
        issues.append("Description may be too long — consider condensing")
    has_cta = bool(re.search(r"\b(buy|shop|order|get|discover|try|learn|explore)\b", description, re.I))
    if not has_cta:
        score -= 10
        issues.append("Add a call-to-action (e.g. 'Shop now', 'Discover', 'Get yours today')")
    return {"word_count": wc, "score": round(score, 1), "issues": issues}


def overall_seo_score(
    readability: float,
    kw_density: float,
    title_len: int,
    description_words: int,
    flesch: float,
) -> float:
    """Weighted overall SEO score 0–100."""
    r_score = readability

    # Keyword density: ideal 1.5–3%
    if 1.5 <= kw_density <= 3.0:
        kd_score = 100.0
    elif kw_density < 1.5:
        kd_score = max(0.0, kw_density / 1.5 * 100)
    else:
        kd_score = max(0.0, 100 - (kw_density - 3.0) * 30)

    tl_score = 100.0 if title_len <= 70 else max(0.0, 100 - (title_len - 70) * 2)

    if 150 <= description_words <= 200:
        dl_score = 100.0
    elif description_words < 150:
        dl_score = max(0.0, description_words / 150 * 100)
    else:
        dl_score = max(0.0, 100 - (description_words - 200) * 0.5)

    weighted = (
        r_score * 0.25
        + kd_score * 0.25
        + tl_score * 0.15
        + dl_score * 0.20
        + flesch * 0.15
    )
    return round(weighted, 1)


# ── Full Analysis ──────────────────────────────────────────────────────────────

def analyze(title: str, description: str, keywords: List[str]) -> Dict[str, Any]:
    """
    Full SEO analysis on a title + description pair.
    Returns metrics dict compatible with SEOMetrics model.
    """
    flesch = flesch_reading_ease(description)
    r_score = readability_score(description)
    kd = keyword_density(description, keywords)
    title_info = title_score(title)
    desc_info = description_score(description)

    overall = overall_seo_score(
        readability=r_score,
        kw_density=kd,
        title_len=title_info["length"],
        description_words=desc_info["word_count"],
        flesch=flesch,
    )

    suggestions = []
    for issue in title_info["issues"]:
        suggestions.append({"type": "warn", "text": issue})
    for issue in desc_info["issues"]:
        suggestions.append({"type": "warn", "text": issue})
    if kd < 1.0:
        suggestions.append({"type": "warn", "text": "Keyword density is low — weave in more target keywords naturally"})
    elif kd > 4.0:
        suggestions.append({"type": "warn", "text": "Keyword density too high — reduce repetition to avoid stuffing"})
    else:
        suggestions.append({"type": "tip", "text": f"Keyword density {kd}% — within the ideal 1.5–3% range ✓"})
    if flesch >= 60:
        suggestions.append({"type": "tip", "text": f"Flesch score {flesch} — content is easy to read ✓"})
    else:
        suggestions.append({"type": "warn", "text": f"Flesch score {flesch} — simplify language for broader audience"})

    return {
        "readability_score": r_score,
        "keyword_density": kd,
        "title_length": title_info["length"],
        "description_length": desc_info["word_count"],
        "flesch_score": flesch,
        "overall_score": overall,
        "suggestions": suggestions[:5],
    }


def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """Top keywords by frequency, filtering stop words."""
    words = _words(text)
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 3]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(top_n)]
