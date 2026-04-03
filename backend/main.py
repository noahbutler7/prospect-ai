"""
main.py — ProspectAI FastAPI application

Endpoints:
  POST   /api/scan/start              Start a new LinkedIn scan job
  GET    /api/scan/{job_id}/stream    SSE stream — receive prospects in real time
  POST   /api/scan/{job_id}/stop      Stop a running scan
  GET    /api/scan/{job_id}           Get scan job status
  GET    /api/prospects               List all prospects (filterable)
  GET    /api/prospects/{id}          Get a single prospect
  PATCH  /api/prospects/{id}          Update status or email draft
  POST   /api/prospects/{id}/send     Send the approved email
  DELETE /api/prospects/{id}          Remove a prospect
  GET    /api/health                  Health check

Real-time flow:
  1. Client POSTs to /scan/start → gets back { job_id }
  2. Client opens EventSource to /scan/{job_id}/stream
  3. Backend runs scan pipeline in a background task:
       scrape → ICP match → email enrich → Claude draft
     Pushes each matched prospect as an SSE "prospect" event.
  4. When done, pushes a "done" event and closes the stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import get_settings
from drafter import EmailDrafter, build_icp_summary
from enricher import find_email
from icp_matcher import score_prospect
from models import (
    EmailDraft,
    Prospect,
    ProspectUpdate,
    ScanRequest,
    ScanStatus,
)
from scraper import LinkedInScraper, RawProfile

# ─── App setup ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="ProspectAI API",
    description="LinkedIn prospect discovery and AI email drafting engine",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── In-memory state ──────────────────────────────────────────────────────────
# Replace with Redis + Postgres for production.

# job_id → ScanStatus
scan_jobs: dict[str, ScanStatus] = {}

# job_id → asyncio.Queue (SSE channel per job)
# Sentinel: None = stream finished
job_queues: dict[str, asyncio.Queue] = {}

# prospect_id → Prospect
prospects_db: dict[str, Prospect] = {}


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def _raw_to_prospect(raw: RawProfile, job_id: str) -> Prospect:
    return Prospect(
        first_name=raw.first_name,
        last_name=raw.last_name,
        full_name=raw.full_name,
        title=raw.title,
        company=raw.company,
        company_domain=raw.company_domain,
        linkedin_url=raw.linkedin_url,
        linkedin_urn=raw.linkedin_urn,
        profile_picture_url=raw.profile_picture_url,
        headline=raw.headline,
        recent_activity=raw.recent_post,
        scan_job_id=job_id,
    )


async def _run_scan_pipeline(job_id: str, request: ScanRequest) -> None:
    """
    Background task that:
      1. Iterates over target accounts
      2. Scrapes LinkedIn profiles via Playwright
      3. Scores against ICP
      4. Enriches emails
      5. Drafts emails with Claude
      6. Pushes each matched Prospect into the SSE queue
    """
    queue = job_queues[job_id]
    job = scan_jobs[job_id]
    job.status = "running"
    job.started_at = datetime.utcnow()

    drafter = EmailDrafter()
    icp_summary = build_icp_summary(request.icp.titles, request.icp.seniority)

    logger.info(f"[{job_id}] Starting scan: {len(request.accounts)} accounts")

    try:
        async with LinkedInScraper() as scraper:

            # Verify LinkedIn session before starting
            if not await scraper.verify_session():
                err = "LinkedIn session is invalid or expired. Please refresh linkedin_cookies.json."
                logger.error(f"[{job_id}] {err}")
                job.status = "error"
                job.error = err
                await queue.put({"type": "error", "data": {"message": err}})
                await queue.put(None)
                return

            for account in request.accounts:
                logger.info(f"[{job_id}] Scanning account: {account.name}")

                async for raw in scraper.scrape_account(
                    company_name=account.name,
                    company_domain=account.domain,
                    linkedin_slug=account.linkedin_slug,
                    max_results=request.max_prospects_per_account,
                    visit_profiles=True,
                ):
                    job.prospects_found += 1

                    # ── ICP scoring ────────────────────────────────────────
                    result = score_prospect(raw, request.icp)
                    if not result.passes:
                        logger.debug(f"ICP fail: {raw.full_name} score={result.score:.2f}")
                        continue

                    job.prospects_matched += 1

                    # ── Build Prospect object ──────────────────────────────
                    prospect = _raw_to_prospect(raw, job_id)
                    prospect.icp_score = result.score
                    prospect.icp_match_reasons = result.match_reasons
                    prospect.signals = result.signals

                    # ── Email enrichment ───────────────────────────────────
                    email, confidence, source = await find_email(
                        raw.first_name,
                        raw.last_name,
                        raw.company,
                        raw.company_domain,
                    )
                    prospect.email = email
                    prospect.email_confidence = confidence
                    prospect.email_source = source

                    # ── Email draft ────────────────────────────────────────
                    if request.draft_emails:
                        draft = await drafter.draft(prospect, icp_summary)
                        prospect.email_draft = draft

                    # ── Store + push to SSE queue ──────────────────────────
                    prospects_db[prospect.id] = prospect
                    await queue.put({
                        "type": "prospect",
                        "data": prospect.model_dump(mode="json"),
                    })

                    logger.info(
                        f"[{job_id}] ✓ {prospect.full_name} @ {prospect.company} "
                        f"(score={result.score:.2f}, email={prospect.email or 'none'})"
                    )

                # Push account-done status update
                job.accounts_done += 1
                await queue.put({
                    "type": "status",
                    "data": {
                        "accounts_done": job.accounts_done,
                        "accounts_total": job.accounts_total,
                        "prospects_found": job.prospects_found,
                        "prospects_matched": job.prospects_matched,
                    },
                })

        job.status = "done"
        job.finished_at = datetime.utcnow()
        logger.info(
            f"[{job_id}] Scan complete: {job.prospects_matched} matched / "
            f"{job.prospects_found} found"
        )

    except asyncio.CancelledError:
        job.status = "stopped"
        logger.info(f"[{job_id}] Scan stopped by user")
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        logger.exception(f"[{job_id}] Scan pipeline error: {e}")
        await queue.put({"type": "error", "data": {"message": str(e)}})
    finally:
        await queue.put(None)  # Sentinel: close SSE stream


# ─── SSE generator ────────────────────────────────────────────────────────────

async def _sse_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Async generator that pulls events from the job queue and formats them
    as SSE (text/event-stream) data frames.
    """
    queue = job_queues.get(job_id)
    if not queue:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Job not found'}})}\n\n"
        return

    # Send immediate confirmation
    yield f"data: {json.dumps({'type': 'status', 'data': {'job_id': job_id, 'status': 'connected'}})}\n\n"

    while True:
        try:
            # Poll queue with a timeout so we can send keepalives
            item = await asyncio.wait_for(queue.get(), timeout=20.0)
        except asyncio.TimeoutError:
            # Keepalive comment to prevent proxy/browser from closing the connection
            yield ": keepalive\n\n"
            continue

        if item is None:
            # Sentinel — pipeline is done
            yield f"data: {json.dumps({'type': 'done', 'data': {}})}\n\n"
            break

        yield f"data: {json.dumps(item)}\n\n"


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/scan/start", status_code=201)
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Start a new LinkedIn scan job.

    Returns { job_id } immediately. Connect to /api/scan/{job_id}/stream
    to receive prospects in real time via SSE.
    """
    job_id = str(uuid.uuid4())

    job = ScanStatus(
        job_id=job_id,
        status="queued",
        accounts_total=len(request.accounts),
        accounts_done=0,
        prospects_found=0,
        prospects_matched=0,
    )
    scan_jobs[job_id] = job
    job_queues[job_id] = asyncio.Queue()

    background_tasks.add_task(_run_scan_pipeline, job_id, request)
    logger.info(f"Scan queued: {job_id}")

    return {"job_id": job_id}


@app.get("/api/scan/{job_id}/stream")
async def stream_scan(job_id: str):
    """
    SSE endpoint. Open as EventSource in the browser:

        const es = new EventSource(`/api/scan/${jobId}/stream`);
        es.onmessage = (e) => {
            const event = JSON.parse(e.data);
            if (event.type === 'prospect') addToQueue(event.data);
            if (event.type === 'done')     es.close();
        };

    Event types: "prospect" | "status" | "error" | "done"
    """
    if job_id not in scan_jobs:
        raise HTTPException(status_code=404, detail="Scan job not found")

    return StreamingResponse(
        _sse_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",       # Disable Nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.post("/api/scan/{job_id}/stop")
async def stop_scan(job_id: str):
    """Stop a running scan job."""
    job = scan_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")

    if job.status not in ("queued", "running"):
        return {"message": f"Job is already {job.status}"}

    job.status = "stopped"
    # Push sentinel to close any open SSE streams
    q = job_queues.get(job_id)
    if q:
        await q.put(None)

    return {"message": "Scan stopped", "job_id": job_id}


@app.get("/api/scan/{job_id}")
async def get_scan_status(job_id: str):
    """Get the current status of a scan job."""
    job = scan_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")
    return job


@app.get("/api/prospects")
async def list_prospects(
    status: Optional[str] = Query(None, description="Filter by status"),
    company: Optional[str] = Query(None, description="Filter by company name"),
    job_id: Optional[str] = Query(None, description="Filter by scan job ID"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """List all prospects with optional filters."""
    results = list(prospects_db.values())

    if status:
        results = [p for p in results if p.status == status]
    if company:
        results = [p for p in results if company.lower() in p.company.lower()]
    if job_id:
        results = [p for p in results if p.scan_job_id == job_id]

    # Sort newest first
    results.sort(key=lambda p: p.found_at, reverse=True)

    return {
        "total": len(results),
        "prospects": results[offset: offset + limit],
    }


@app.get("/api/prospects/{prospect_id}")
async def get_prospect(prospect_id: str):
    """Get a single prospect by ID."""
    prospect = prospects_db.get(prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return prospect


@app.patch("/api/prospects/{prospect_id}")
async def update_prospect(prospect_id: str, update: ProspectUpdate):
    """
    Update a prospect's status or email draft.
    Used when the SDR approves/rejects or edits an email in the UI.
    """
    prospect = prospects_db.get(prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    if update.status is not None:
        prospect.status = update.status
    if update.email_draft is not None:
        prospect.email_draft = update.email_draft

    prospects_db[prospect_id] = prospect
    return prospect


@app.post("/api/prospects/{prospect_id}/send")
async def send_email(prospect_id: str):
    """
    Send the approved email draft for this prospect.
    Requires SENDGRID_API_KEY and FROM_EMAIL set in .env.
    """
    prospect = prospects_db.get(prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    if not prospect.email_draft:
        raise HTTPException(status_code=400, detail="No email draft to send")
    if not prospect.email:
        raise HTTPException(status_code=400, detail="No email address for prospect")

    if not settings.sendgrid_api_key or not settings.from_email:
        raise HTTPException(
            status_code=501,
            detail="Email sending not configured. Set SENDGRID_API_KEY and FROM_EMAIL in .env"
        )

    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": prospect.email}]}],
                "from": {"email": settings.from_email, "name": settings.from_name},
                "subject": prospect.email_draft.subject,
                "content": [{"type": "text/plain", "value": prospect.email_draft.body}],
            },
            timeout=15,
        )

    if response.status_code not in (200, 202):
        raise HTTPException(
            status_code=502,
            detail=f"SendGrid error: {response.status_code} {response.text}"
        )

    prospect.status = "sent"
    prospects_db[prospect_id] = prospect
    logger.info(f"Email sent to {prospect.email} for {prospect.full_name}")
    return {"message": "Email sent", "to": prospect.email}


@app.delete("/api/prospects/{prospect_id}")
async def delete_prospect(prospect_id: str):
    """Remove a prospect from the system."""
    if prospect_id not in prospects_db:
        raise HTTPException(status_code=404, detail="Prospect not found")
    del prospects_db[prospect_id]
    return {"message": "Deleted"}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
