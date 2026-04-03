"""
icp_matcher.py — ICP scoring engine for ProspectAI

Scores each RawProfile against the user's Ideal Customer Profile (ICP)
and returns a normalized score between 0.0 and 1.0, plus the reasons
that contributed to the score.

Scoring breakdown (weights sum to 1.0):
  - Title match        0.40  — does the title contain a target keyword?
  - Seniority match    0.30  — is the person at the right seniority level?
  - Signal match       0.30  — do their LinkedIn posts/headline contain ICP signals?
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

from models import ICPConfig, ProspectSignal
from scraper import RawProfile

logger = logging.getLogger(__name__)


# ─── Seniority keyword map ────────────────────────────────────────────────────

SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "C-Suite": [
        "chief", "ceo", "cto", "cro", "cmo", "coo", "cfo",
        "president", "founder", "co-founder", "owner",
    ],
    "VP": [
        "vp", "vice president", "v.p.",
    ],
    "Director": [
        "director", "head of", "global head",
    ],
    "Manager": [
        "manager", "lead", "team lead", "senior manager",
    ],
    "Individual Contributor": [
        "specialist", "analyst", "associate", "coordinator",
        "representative", "rep", "executive", "account executive",
        "business development", "sdr", "bdr",
    ],
}

# Signals that strongly indicate buying intent / budget ownership
STRONG_BUYING_SIGNALS = [
    "hiring", "we're growing", "expanding", "looking for",
    "building our team", "just raised", "series", "funding",
    "new budget", "evaluating", "looking for solutions",
    "open to connect", "recently joined",
]


# ─── Normalisation helpers ────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return text.lower().strip()


def _contains_any(haystack: str, needles: list[str]) -> Optional[str]:
    """Return the first needle found in haystack (case-insensitive), or None."""
    h = _normalise(haystack)
    for needle in needles:
        if _normalise(needle) in h:
            return needle
    return None


# ─── Scoring sub-functions ────────────────────────────────────────────────────

def _score_title(title: str, target_titles: list[str]) -> tuple[float, list[str]]:
    """
    Score 0–1 for title match.
    Exact substring match → 1.0
    Partial word overlap  → 0.5
    No match              → 0.0
    """
    reasons: list[str] = []
    if not title or not target_titles:
        return 0.0, reasons

    title_lower = _normalise(title)

    for target in target_titles:
        target_lower = _normalise(target)
        if target_lower in title_lower:
            reasons.append(f'Title matches "{target}"')
            return 1.0, reasons

    # Partial: any significant word overlap
    title_words = set(re.findall(r"\b\w{4,}\b", title_lower))
    for target in target_titles:
        target_words = set(re.findall(r"\b\w{4,}\b", _normalise(target)))
        overlap = title_words & target_words
        if overlap:
            reasons.append(f'Title partially matches ({", ".join(overlap)})')
            return 0.5, reasons

    return 0.0, reasons


def _score_seniority(
    title: str,
    target_seniority: list[str],
) -> tuple[float, list[str]]:
    """
    Score 0–1 for seniority match.
    Maps title keywords to seniority buckets.
    """
    reasons: list[str] = []
    if not title or not target_seniority:
        return 0.0, reasons

    title_lower = _normalise(title)

    for level in target_seniority:
        keywords = SENIORITY_KEYWORDS.get(level, [])
        match = _contains_any(title_lower, keywords)
        if match:
            reasons.append(f'Seniority level: {level} ("{match}")')
            return 1.0, reasons

    return 0.0, reasons


def _score_signals(
    profile: RawProfile,
    icp_keywords: list[str],
) -> tuple[float, list[ProspectSignal]]:
    """
    Score 0–1 for buying signal match.
    Checks headline, recent post, and raw_signals against ICP keywords
    and a built-in list of strong buying intent signals.
    """
    detected: list[ProspectSignal] = []
    if not icp_keywords:
        return 0.0, detected

    # Aggregate all signal text
    signal_sources: list[tuple[str, str]] = []  # (source_type, text)
    if profile.headline:
        signal_sources.append(("headline", profile.headline))
    if profile.recent_post:
        signal_sources.append(("post", profile.recent_post))
    for s in profile.raw_signals:
        signal_sources.append(("activity", s))

    total_score = 0.0
    max_score = 0.0

    for source_type, text in signal_sources:
        # ICP-defined keywords
        for keyword in icp_keywords:
            if _normalise(keyword) in _normalise(text):
                detected.append(ProspectSignal(
                    text=keyword,
                    source=source_type,  # type: ignore[arg-type]
                ))
                total_score += 0.4
                break  # one match per source is enough

        # Built-in strong signals
        for sig in STRONG_BUYING_SIGNALS:
            if sig in _normalise(text):
                detected.append(ProspectSignal(
                    text=sig.title(),
                    source=source_type,  # type: ignore[arg-type]
                ))
                total_score += 0.3
                break

        max_score += 0.7  # max per source

    if max_score == 0:
        return 0.0, detected

    score = min(total_score / max_score, 1.0)
    return score, detected


# ─── Main scoring function ────────────────────────────────────────────────────

@dataclass
class ICPMatchResult:
    score: float                      # 0.0 – 1.0
    passes: bool                      # score >= min_icp_score
    match_reasons: list[str]
    signals: list[ProspectSignal]
    title_score: float
    seniority_score: float
    signal_score: float


def score_prospect(profile: RawProfile, icp: ICPConfig) -> ICPMatchResult:
    """
    Score a RawProfile against the given ICP and return a full ICPMatchResult.

    Weights:
      title      40%
      seniority  30%
      signals    30%
    """
    title_score, title_reasons = _score_title(profile.title, icp.titles)
    seniority_score, seniority_reasons = _score_seniority(profile.title, icp.seniority)
    signal_score, signals = _score_signals(profile, icp.keywords)

    # Weighted composite
    composite = (
        title_score * 0.40
        + seniority_score * 0.30
        + signal_score * 0.30
    )

    all_reasons = title_reasons + seniority_reasons
    # Add signal reason summaries
    if signals:
        signal_texts = list({s.text for s in signals})[:3]
        all_reasons.append(f'Signals: {", ".join(signal_texts)}')

    passes = composite >= icp.min_icp_score

    logger.debug(
        f"{profile.full_name} | title={title_score:.2f} sen={seniority_score:.2f} "
        f"sig={signal_score:.2f} → composite={composite:.2f} pass={passes}"
    )

    return ICPMatchResult(
        score=round(composite, 3),
        passes=passes,
        match_reasons=all_reasons,
        signals=signals,
        title_score=title_score,
        seniority_score=seniority_score,
        signal_score=signal_score,
    )
