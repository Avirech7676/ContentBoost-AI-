"""
constants.py — Shared constants for ContentBoost AI.
Single source of truth for stop words, tone definitions, and prompt examples.
"""

from __future__ import annotations

# ── Shared stop words ──────────────────────────────────────────────────────────

STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "this", "that", "these", "those", "it", "its", "their", "they",
    "our", "we", "you", "your", "i", "my", "he", "she", "his", "her", "us",
    "them", "not", "no", "by", "from", "as", "also", "which", "who", "what",
    "when", "where", "how", "all", "any", "each", "more", "than", "so", "if",
    "just", "can", "into", "about", "up", "out", "then", "there", "very",
})

# ── Tone definitions injected into LLM prompts ─────────────────────────────────

TONE_DEFINITIONS: dict[str, str] = {
    "persuasive": (
        "PERSUASIVE TONE: Use compelling, action-oriented language. Emphasise benefits "
        "over features. Build urgency ('limited stock', 'join thousands of happy customers'). "
        "Speak directly to the reader using 'you' and 'your'. End with a strong CTA."
    ),
    "formal": (
        "FORMAL TONE: Use professional, authoritative language. Maintain a neutral or "
        "third-person perspective. Avoid contractions and colloquialisms. Precise vocabulary "
        "appropriate for B2B, corporate, or academic audiences."
    ),
    "casual": (
        "CASUAL TONE: Friendly and conversational. Contractions welcome ('it's', 'you'll'). "
        "Short sentences. Relatable language as if talking to a friend. Light and approachable."
    ),
    "technical": (
        "TECHNICAL TONE: Lead with specifications, performance metrics, and technical data. "
        "Use industry terminology. Be precise. Target engineers and tech-savvy buyers. "
        "No marketing fluff — facts and figures take priority."
    ),
    "luxury": (
        "LUXURY TONE: Sophisticated, evocative vocabulary conveying exclusivity and "
        "craftsmanship. Focus on heritage, rarity, and sensory experience. Never mention "
        "discounts or deals. Use words like 'meticulously crafted', 'unparalleled elegance', "
        "'reserved for the discerning few', 'timeless'."
    ),
}

# ── Few-shot example for SEO descriptions ─────────────────────────────────────

FEW_SHOT_SEO_EXAMPLE: str = """\
REFERENCE EXAMPLE (do NOT copy — for style guidance only):
Title: "Sony WH-1000XM5 Wireless Headphones — 30-Hour ANC Battery"
Description: "Experience industry-leading noise cancellation with the Sony WH-1000XM5. \
Powered by the V1 processor, these over-ear headphones block ambient sound for total focus \
whether commuting, working, or travelling. Enjoy up to 30 hours of playtime with ANC on, \
multipoint Bluetooth 5.2 connection, and crystal-clear hands-free calls via the 8-mic array. \
Lightweight foldable design pairs with the Sony Headphones Connect app for personalised EQ. \
Compatible with Google Assistant and Amazon Alexa. Upgrade your listening — order yours today."
"""
