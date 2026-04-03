"""
drafter.py — Claude-powered personalized email drafter for ProspectAI

Generates a cold outreach email for each prospect using:
  - Their name, title, company
  - Detected LinkedIn signals (recent posts, hiring activity, etc.)
  - Your ICP configuration (who you're targeting and why)
  - Optional: your company's pitch context (loaded from .env or passed at runtime)

The system prompt teaches Claude to write emails that are:
  - Short (< 120 words in the body)
  - Personal — references the specific signal detected
  - Problem-first, not feature-first
  - Ends with a single, low-friction CTA
"""

from __future__ import annotations

import logging
from typing import Optional

import anthropic

from config import get_settings
from models import EmailDraft, Prospect

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Prompt templates ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert B2B sales copywriter specializing in cold email outreach for SDR teams.

Your job is to draft a personalized cold email from an SDR to a prospect.

Rules you MUST follow:
- Subject line: max 8 words, specific, no clickbait, no "Quick question" clichés
- Body: 3–5 sentences MAXIMUM. Under 120 words.
- Opening: reference something specific about the prospect (their signal, title, company context)
- Middle: one crisp sentence connecting their likely pain point to a concrete outcome you deliver
- CTA: one soft, specific ask — e.g., "Worth a 15-min call this week?" — NOT "Would you be open to learning more?"
- Tone: direct, confident, peer-to-peer. Not salesy. No buzzwords.
- Do NOT use: "I hope this finds you well", "touching base", "reaching out", "synergy", "leverage"
- Do NOT mention features — only outcomes and pain points
- Sign off: just "Best," — leave [Your name] as a placeholder

Output ONLY valid JSON with two keys: "subject" and "body". No markdown, no extra text."""


USER_PROMPT_TEMPLATE = """Draft a cold email for this prospect:

PROSPECT:
- Name: {full_name}
- Title: {title}
- Company: {company}
- LinkedIn signals detected: {signals}
- Recent LinkedIn post: {recent_post}
- Headline: {headline}

YOUR COMPANY CONTEXT:
{company_context}

ICP WE'RE TARGETING:
{icp_summary}

Remember: output ONLY JSON with "subject" and "body" keys."""


DEFAULT_COMPANY_CONTEXT = """We help B2B SaaS companies scale their outbound motion.
Our AI agent finds, qualifies, and drafts personalized outreach for every prospect in your ICP —
cutting prospecting time by 60% while keeping reply rates high.
We work with SDR teams at companies like Gong, Drift, and Outreach."""


# ─── Drafter ─────────────────────────────────────────────────────────────────

class EmailDrafter:
    """
    Async email draft generator backed by Claude.

    Usage:
        drafter = EmailDrafter()
        draft = await drafter.draft(prospect, icp_summary="VP Sales at SaaS companies")
    """

    def __init__(
        self,
        company_context: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.claude_model
        self._company_context = company_context or DEFAULT_COMPANY_CONTEXT

    async def draft(
        self,
        prospect: Prospect,
        icp_summary: str = "",
        retries: int = 2,
    ) -> Optional[EmailDraft]:
        """
        Generate a personalized email draft for the given prospect.
        Returns an EmailDraft, or None on failure.
        """
        signals_text = (
            ", ".join(s.text for s in prospect.signals)
            if prospect.signals
            else "None detected"
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            full_name=prospect.full_name,
            title=prospect.title,
            company=prospect.company,
            signals=signals_text,
            recent_post=prospect.recent_activity or "N/A",
            headline=prospect.headline or prospect.title,
            company_context=self._company_context,
            icp_summary=icp_summary or f"Targeting {', '.join(['VP of Sales', 'Head of SDR'])} at SaaS companies",
        )

        for attempt in range(retries + 1):
            try:
                message = await self._client.messages.create(
                    model=self._model,
                    max_tokens=512,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.7,
                )
                raw = message.content[0].text.strip()
                subject, body = self._parse_response(raw)

                if subject and body:
                    logger.info(f"Email drafted for {prospect.full_name}: \"{subject}\"")
                    return EmailDraft(
                        subject=subject,
                        body=body,
                        model=self._model,
                    )

            except anthropic.APIStatusError as e:
                logger.error(f"Claude API error (attempt {attempt + 1}): {e}")
                if e.status_code == 429:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)  # exponential back-off
            except Exception as e:
                logger.error(f"Draft generation failed (attempt {attempt + 1}): {e}")

        logger.warning(f"All draft attempts failed for {prospect.full_name}")
        return None

    def _parse_response(self, raw: str) -> tuple[str, str]:
        """
        Parse Claude's JSON response into (subject, body).
        Handles minor formatting issues gracefully.
        """
        import json
        import re

        # Strip markdown code fences if Claude wraps in them
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE)

        try:
            data = json.loads(raw.strip())
            return data.get("subject", ""), data.get("body", "")
        except json.JSONDecodeError:
            # Fallback: extract with regex
            subject_match = re.search(r'"subject"\s*:\s*"([^"]+)"', raw)
            body_match = re.search(r'"body"\s*:\s*"([\s\S]+?)"\s*[,}]', raw)
            subject = subject_match.group(1) if subject_match else ""
            body = body_match.group(1).replace("\\n", "\n") if body_match else ""
            return subject, body


# ─── ICP summary builder ──────────────────────────────────────────────────────

def build_icp_summary(icp_titles: list[str], icp_seniority: list[str]) -> str:
    """Build a natural-language ICP summary string for the prompt."""
    parts = []
    if icp_seniority:
        parts.append(f"Seniority: {', '.join(icp_seniority)}")
    if icp_titles:
        parts.append(f"Titles: {', '.join(icp_titles[:4])}")
    return " | ".join(parts) if parts else "B2B SaaS revenue leaders"
