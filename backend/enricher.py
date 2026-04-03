"""
enricher.py — Email address discovery and enrichment for ProspectAI

Enrichment cascade (tries each strategy in order, stops at first success):

  1. Hunter.io API       — verified email lookup by name + domain
  2. Apollo.io API       — people search by name + company
  3. Pattern inference   — generate probable email formats and optionally
                           verify via SMTP or DNS
  4. Give up             — return None

Each result is tagged with a confidence level:
  "verified" — confirmed deliverable by an external service
  "inferred" — pattern-based, unverified but likely
  "guessed"  — low-confidence guess
"""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import socket
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Common email patterns ────────────────────────────────────────────────────

def _generate_email_candidates(
    first: str,
    last: str,
    domain: str,
) -> list[str]:
    """
    Generate common business email format guesses for a given name + domain.
    Returns in rough order of likelihood.
    """
    f = re.sub(r"[^a-z]", "", first.lower())
    l = re.sub(r"[^a-z]", "", last.lower())

    if not f or not l:
        return []

    return [
        f"{f}.{l}@{domain}",           # john.doe
        f"{f}{l}@{domain}",            # johndoe
        f"{f[0]}{l}@{domain}",         # jdoe
        f"{f}@{domain}",               # john
        f"{f}.{l[0]}@{domain}",        # john.d
        f"{f[0]}.{l}@{domain}",        # j.doe
        f"{l}.{f}@{domain}",           # doe.john
        f"{l}{f[0]}@{domain}",         # doej
    ]


# ─── DNS MX check ─────────────────────────────────────────────────────────────

def _domain_has_mx(domain: str) -> bool:
    """Check whether the domain has MX records (fast sanity check)."""
    try:
        import dns.resolver  # dnspython
        answers = dns.resolver.resolve(domain, "MX", lifetime=3)
        return len(answers) > 0
    except Exception:
        # Fallback: try basic socket lookup
        try:
            socket.getaddrinfo(domain, 25, socket.AF_UNSPEC, socket.SOCK_STREAM)
            return True
        except Exception:
            return False


# ─── SMTP verification ────────────────────────────────────────────────────────

async def _smtp_verify(email: str) -> bool:
    """
    Attempt to verify email existence via SMTP RCPT TO handshake.
    NOTE: Many mail servers block this or return false positives.
    Use with SMTP_VERIFY=true in .env only if you're comfortable with the trade-offs.
    """
    domain = email.split("@")[-1]
    try:
        import dns.resolver
        mx_records = dns.resolver.resolve(domain, "MX", lifetime=5)
        mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange)
    except Exception:
        return False

    def _verify_sync() -> bool:
        try:
            with smtplib.SMTP(timeout=8) as smtp:
                smtp.connect(mx_host, 25)
                smtp.helo("verify.prospectai.io")
                smtp.mail("verify@prospectai.io")
                code, _ = smtp.rcpt(email)
                return code == 250
        except Exception:
            return False

    # Run blocking SMTP call in thread pool
    return await asyncio.get_event_loop().run_in_executor(None, _verify_sync)


# ─── Hunter.io ────────────────────────────────────────────────────────────────

async def _hunter_lookup(
    first: str,
    last: str,
    domain: str,
    client: httpx.AsyncClient,
) -> Optional[tuple[str, str]]:
    """
    Returns (email, confidence) or None.
    Hunter confidence: "verified" | "guessed"
    """
    if not settings.hunter_api_key:
        return None

    try:
        resp = await client.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "first_name": first,
                "last_name": last,
                "api_key": settings.hunter_api_key,
            },
            timeout=10,
        )
        data = resp.json()
        email = data.get("data", {}).get("email")
        confidence = data.get("data", {}).get("confidence", 0)
        if email:
            tier = "verified" if confidence >= 80 else "inferred"
            logger.info(f"Hunter found: {email} ({confidence}% confidence)")
            return email, tier
    except Exception as e:
        logger.warning(f"Hunter API error: {e}")
    return None


# ─── Apollo.io ────────────────────────────────────────────────────────────────

async def _apollo_lookup(
    first: str,
    last: str,
    company: str,
    client: httpx.AsyncClient,
) -> Optional[tuple[str, str]]:
    """
    Returns (email, confidence) or None.
    """
    if not settings.apollo_api_key:
        return None

    try:
        resp = await client.post(
            "https://api.apollo.io/v1/people/match",
            json={
                "first_name": first,
                "last_name": last,
                "organization_name": company,
                "reveal_personal_emails": False,
            },
            headers={"x-api-key": settings.apollo_api_key, "Content-Type": "application/json"},
            timeout=12,
        )
        data = resp.json()
        person = data.get("person") or {}
        email = person.get("email")
        if email and "@" in email:
            logger.info(f"Apollo found: {email}")
            return email, "verified"
    except Exception as e:
        logger.warning(f"Apollo API error: {e}")
    return None


# ─── Main enricher ────────────────────────────────────────────────────────────

async def find_email(
    first_name: str,
    last_name: str,
    company: str,
    domain: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Attempt to find a work email address for the given person.

    Returns:
        (email, confidence, source)
        All three are None if no email could be found.

    confidence: "verified" | "inferred" | "guessed" | None
    source:     "hunter" | "apollo" | "pattern" | "smtp" | None
    """
    async with httpx.AsyncClient() as client:

        # ── 1. Hunter.io ──────────────────────────────────────────────────
        result = await _hunter_lookup(first_name, last_name, domain, client)
        if result:
            return result[0], result[1], "hunter"

        # ── 2. Apollo.io ──────────────────────────────────────────────────
        result = await _apollo_lookup(first_name, last_name, company, client)
        if result:
            return result[0], result[1], "apollo"

        # ── 3. Pattern inference ──────────────────────────────────────────
        candidates = _generate_email_candidates(first_name, last_name, domain)
        if not candidates:
            return None, None, None

        if settings.smtp_verify:
            # Try to SMTP-verify each candidate
            for email in candidates:
                verified = await _smtp_verify(email)
                if verified:
                    logger.info(f"SMTP verified: {email}")
                    return email, "verified", "smtp"

        # Return the highest-probability guess without verification
        best_guess = candidates[0]
        logger.info(f"Pattern-inferred email: {best_guess} (unverified)")
        return best_guess, "inferred", "pattern"
