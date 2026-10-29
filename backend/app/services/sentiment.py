"""Lexicon sentiment scoring for financial headlines.

A general-purpose sentiment model reads "shares plunge" as mildly
negative; in a market context it is strongly negative. This is a
Loughran-McDonald-style finance lexicon with weighted terms, negation
handling and headline-length normalisation, so the score stays
explainable -- the matched terms travel with every document.

Score is in [-1, 1]; the label thresholds are +/-0.15.
"""
from __future__ import annotations

import re
from typing import Iterable

POSITIVE: dict[str, float] = {
    "surge": 2.5, "surges": 2.5, "surged": 2.5, "soar": 2.8, "soars": 2.8,
    "soared": 2.8, "rally": 2.0, "rallies": 2.0, "rallied": 2.0,
    "jump": 2.0, "jumps": 2.0, "jumped": 2.0, "climb": 1.6, "climbs": 1.6,
    "climbed": 1.6, "gain": 1.5, "gains": 1.5, "gained": 1.5, "rise": 1.3,
    "rises": 1.3, "rose": 1.3, "beat": 2.2, "beats": 2.2, "outperform": 2.3,
    "outperforms": 2.3, "upgrade": 2.6, "upgrades": 2.6, "upgraded": 2.6,
    "buy": 1.4, "overweight": 1.8, "bullish": 2.4, "record": 1.8,
    "profit": 1.6, "profits": 1.6, "profitable": 1.8, "growth": 1.5,
    "strong": 1.7, "stronger": 1.8, "robust": 1.7, "exceed": 2.0,
    "exceeds": 2.0, "exceeded": 2.0, "top": 1.2, "tops": 1.6, "topped": 1.6,
    "high": 1.0, "highs": 1.4, "approval": 1.9, "approved": 1.9,
    "dividend": 1.1, "buyback": 1.8, "expand": 1.3, "expansion": 1.3,
    "partnership": 1.2, "launch": 1.0, "wins": 1.8, "win": 1.8, "won": 1.8,
    "award": 1.4, "awarded": 1.4, "raise": 1.5, "raises": 1.5, "raised": 1.5,
    "boost": 1.9, "boosts": 1.9, "boosted": 1.9, "optimistic": 1.9,
    "momentum": 1.3, "breakthrough": 2.2, "accelerate": 1.6, "upside": 1.7,
    "positive": 1.5, "success": 1.6, "successful": 1.6, "recovery": 1.4,
}

NEGATIVE: dict[str, float] = {
    "plunge": 2.8, "plunges": 2.8, "plunged": 2.8, "crash": 3.0,
    "crashes": 3.0, "crashed": 3.0, "tumble": 2.5, "tumbles": 2.5,
    "tumbled": 2.5, "slump": 2.3, "slumps": 2.3, "slumped": 2.3,
    "sink": 2.2, "sinks": 2.2, "sank": 2.2, "fall": 1.6, "falls": 1.6,
    "fell": 1.6, "drop": 1.7, "drops": 1.7, "dropped": 1.7,
    "decline": 1.6, "declines": 1.6, "declined": 1.6, "slide": 1.7,
    "slides": 1.7, "slid": 1.7, "loss": 2.0, "losses": 2.0, "lose": 1.8,
    "loses": 1.8, "lost": 1.8, "miss": 2.2, "misses": 2.2, "missed": 2.2,
    "downgrade": 2.7, "downgrades": 2.7, "downgraded": 2.7, "sell": 1.4,
    "underweight": 1.8, "underperform": 2.3, "bearish": 2.4, "weak": 1.8,
    "weaker": 1.9, "weakness": 1.9, "warn": 2.2, "warns": 2.2,
    "warning": 2.2, "cut": 1.8, "cuts": 1.8, "slash": 2.4, "slashes": 2.4,
    "slashed": 2.4, "lawsuit": 2.3, "sue": 2.1, "sues": 2.1, "sued": 2.1,
    "investigation": 2.4, "probe": 2.2, "fraud": 3.0, "bankruptcy": 3.0,
    "bankrupt": 3.0, "default": 2.6, "layoff": 2.3, "layoffs": 2.3,
    "recall": 2.1, "recalls": 2.1, "halt": 1.9, "halted": 1.9,
    "delay": 1.5, "delays": 1.5, "delayed": 1.5, "concern": 1.4,
    "concerns": 1.4, "risk": 1.3, "risks": 1.3, "deficit": 1.8,
    "lawsuits": 2.3, "penalty": 2.0, "fine": 1.7, "fined": 1.9,
    "resign": 1.9, "resigns": 1.9, "resigned": 1.9, "short": 1.1,
    "negative": 1.5, "disappointing": 2.2, "disappoints": 2.2,
    "struggle": 1.9, "struggles": 1.9, "struggling": 1.9, "low": 1.0,
    "lows": 1.4, "selloff": 2.4, "shortfall": 2.1, "writedown": 2.3,
}

NEGATORS = {"not", "no", "never", "without", "despite", "fails", "fail",
            "failed", "avoid", "avoids", "unlikely", "less", "halts"}

INTENSIFIERS = {"very": 1.4, "sharply": 1.5, "significantly": 1.4,
                "massive": 1.6, "massively": 1.6, "slightly": 0.6,
                "modestly": 0.7, "marginally": 0.6, "record": 1.3}

_TOKEN_RE = re.compile(r"[a-z']+")

POSITIVE_THRESHOLD = 0.15
NEGATIVE_THRESHOLD = -0.15


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def score_text(text: str) -> tuple[float, str, list[str]]:
    """Return (score in [-1,1], label, matched terms)."""
    if not text:
        return 0.0, "neutral", []

    tokens = tokenize(text)
    if not tokens:
        return 0.0, "neutral", []

    total = 0.0
    matched: list[str] = []

    for i, token in enumerate(tokens):
        weight = POSITIVE.get(token)
        polarity = 1.0
        if weight is None:
            weight = NEGATIVE.get(token)
            polarity = -1.0
        if weight is None:
            continue

        # Look back two tokens for a negator or an intensifier.
        multiplier = 1.0
        for back in (1, 2):
            if i - back < 0:
                break
            prev = tokens[i - back]
            if prev in NEGATORS:
                polarity *= -1.0
                break
            if prev in INTENSIFIERS:
                multiplier *= INTENSIFIERS[prev]

        total += polarity * weight * multiplier
        matched.append(token)

    if not matched:
        return 0.0, "neutral", []

    # Normalise by sqrt of headline length so long headlines are not
    # mechanically more extreme, then squash into [-1, 1].
    normalised = total / (len(tokens) ** 0.5)
    score = max(-1.0, min(1.0, normalised / 3.0))

    if score >= POSITIVE_THRESHOLD:
        label = "positive"
    elif score <= NEGATIVE_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return round(score, 4), label, matched[:8]


def score_many(texts: Iterable[str]) -> list[tuple[float, str, list[str]]]:
    return [score_text(t) for t in texts]
