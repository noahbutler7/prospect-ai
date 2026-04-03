"""
models.py — Pydantic data models for ProspectAI
"""
from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Literal
from datetime import datetime
import uuid


# ─── ICP Config ──────────────────────────────────────────────────────────────

class ICPConfig(BaseModel):
    titles: list[str] = Field(
        default=["VP of Sales", "Head of Sales Development", "Director of Revenue Operations"],
        description="Target job titles to match against"
    )
    keywords: list[str] = Field(
        default=["hiring SDRs", "recently promoted", "expanding team"],
        description="Buying signals and keywords to look for in LinkedIn activity"
    )
    seniority: list[Literal["C-Suite", "VP", "Director", "Manager", "Individual Contributor"]] = Field(
        default=["C-Suite", "VP", "Director"],
        description="Seniority levels to target"
    )
    min_icp_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum ICP match score (0–1) to include a prospect"
    )


# ─── Account ─────────────────────────────────────────────────────────────────

class TargetAccount(BaseModel):
    name: str = Field(..., description="Company name e.g. 'Salesforce'")
    domain: str = Field(..., description="Email domain e.g. 'salesforce.com'")
    linkedin_slug: Optional[str] = Field(
        None,
        description="LinkedIn company URL slug e.g. 'salesforce'. Inferred from name if not provided."
    )


# ─── Prospect ─────────────────────────────────────────────────────────────────

class ProspectSignal(BaseModel):
    text: str = Field(..., description="Raw signal text e.g. 'Hiring 3 SDRs'")
    source: Literal["post", "activity", "headline", "inferred"] = "inferred"
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class EmailDraft(BaseModel):
    subject: str
    body: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    model: str = "claude-3-5-sonnet-20241022"


class Prospect(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Identity
    first_name: str
    last_name: str
    full_name: str
    title: str
    company: str
    company_domain: str
    # LinkedIn
    linkedin_url: str
    linkedin_urn: Optional[str] = None          # e.g. "ACoAAA..." internal ID
    profile_picture_url: Optional[str] = None
    # Email
    email: Optional[str] = None
    email_confidence: Optional[Literal["verified", "inferred", "guessed"]] = None
    email_source: Optional[str] = None          # "hunter", "pattern", "smtp_verify"
    # Scoring
    icp_score: float = Field(default=0.0, ge=0.0, le=1.0)
    icp_match_reasons: list[str] = Field(default_factory=list)
    # Signals
    signals: list[ProspectSignal] = Field(default_factory=list)
    headline: Optional[str] = None
    recent_activity: Optional[str] = None       # Last LinkedIn post snippet
    # Email draft
    email_draft: Optional[EmailDraft] = None
    # Status
    status: Literal["pending", "reviewing", "approved", "rejected", "sent"] = "pending"
    # Meta
    found_at: datetime = Field(default_factory=datetime.utcnow)
    scan_job_id: str = ""


# ─── Scan Job ─────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    accounts: list[TargetAccount]
    icp: ICPConfig = Field(default_factory=ICPConfig)
    max_prospects_per_account: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of prospects to scrape per account"
    )
    draft_emails: bool = Field(
        default=True,
        description="Auto-generate email drafts for each matched prospect"
    )


class ScanStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "stopped", "error"]
    accounts_total: int
    accounts_done: int
    prospects_found: int
    prospects_matched: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


# ─── API Response types ───────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    """Shape of each JSON payload pushed over the SSE stream."""
    type: Literal["prospect", "status", "error", "done"]
    data: dict


class ProspectUpdate(BaseModel):
    status: Optional[Literal["pending", "reviewing", "approved", "rejected", "sent"]] = None
    email_draft: Optional[EmailDraft] = None


class SendEmailRequest(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str
    body: str
    from_name: Optional[str] = None
