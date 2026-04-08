/**
 * api.js — ProspectAI frontend API client
 *
 * Wraps all calls to the FastAPI backend.
 * Set VITE_API_BASE_URL in your .env to point at your server.
 */

const BASE = "https://prospect-ai.railway.app";  // your Railway URL

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── Scan ─────────────────────────────────────────────────────────────────────

/**
 * Start a new scan job.
 * @param {object} params
 * @param {Array}  params.accounts   — [{ name, domain, linkedin_slug? }]
 * @param {object} params.icp        — { titles, keywords, seniority, min_icp_score }
 * @param {number} params.maxPerAccount
 * @returns {Promise<{ job_id: string }>}
 */
export async function startScan({ accounts, icp, maxPerAccount = 25 }) {
  return request("/api/scan/start", {
    method: "POST",
    body: JSON.stringify({
      accounts,
      icp,
      max_prospects_per_account: maxPerAccount,
      draft_emails: true,
    }),
  });
}

/**
 * Stop a running scan.
 */
export async function stopScan(jobId) {
  return request(`/api/scan/${jobId}/stop`, { method: "POST" });
}

/**
 * Get scan job status.
 */
export async function getScanStatus(jobId) {
  return request(`/api/scan/${jobId}`);
}

/**
 * Open an SSE connection to the scan stream.
 * Calls onProspect(prospect), onStatus(status), onError(msg), onDone() as events arrive.
 *
 * Returns an EventSource instance (call .close() to disconnect).
 *
 * @example
 * const es = streamScan(jobId, {
 *   onProspect: (p) => setProspects(prev => [p, ...prev]),
 *   onDone:     ()  => setScanning(false),
 * });
 * // later: es.close();
 */
export function streamScan(jobId, { onProspect, onStatus, onError, onDone }) {
  const es = new EventSource(`${BASE}/api/scan/${jobId}/stream`);

  es.onmessage = (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (payload.type) {
      case "prospect":
        onProspect?.(payload.data);
        break;
      case "status":
        onStatus?.(payload.data);
        break;
      case "error":
        onError?.(payload.data?.message ?? "Unknown error");
        es.close();
        break;
      case "done":
        onDone?.();
        es.close();
        break;
      default:
        break;
    }
  };

  es.onerror = () => {
    onError?.("Connection to scan stream lost.");
    es.close();
  };

  return es;
}

// ─── Prospects ────────────────────────────────────────────────────────────────

/**
 * List prospects with optional filters.
 */
export async function listProspects({ status, company, jobId, limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status)  params.set("status", status);
  if (company) params.set("company", company);
  if (jobId)   params.set("job_id", jobId);
  params.set("limit", limit);
  params.set("offset", offset);
  return request(`/api/prospects?${params}`);
}

/**
 * Update a prospect's status or email draft.
 * @param {string} id
 * @param {{ status?, email_draft?: { subject, body } }} update
 */
export async function updateProspect(id, update) {
  return request(`/api/prospects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

/**
 * Approve and optionally send the email for a prospect.
 * @param {string} id
 * @param {{ subject: string, body: string }} draft  — updated draft to save first
 * @param {boolean} send                            — also trigger email send
 */
export async function approveProspect(id, draft, send = false) {
  // Save the (possibly edited) draft and set status to approved
  await updateProspect(id, {
    status: send ? "sent" : "approved",
    email_draft: draft,
  });
  // Trigger actual send if requested
  if (send) {
    return request(`/api/prospects/${id}/send`, { method: "POST" });
  }
}

/**
 * Reject a prospect.
 */
export async function rejectProspect(id) {
  return updateProspect(id, { status: "rejected" });
}

/**
 * Delete a prospect.
 */
export async function deleteProspect(id) {
  return request(`/api/prospects/${id}`, { method: "DELETE" });
}
