/**
 * useProspectScan.js — React hook that wires the ProspectAI frontend to the backend
 *
 * Drop this hook into your app and replace the mock scan logic in prospect-agent.jsx.
 *
 * Usage:
 *   const {
 *     prospects, scanning, scanProgress,
 *     startScan, stopScan,
 *     approve, reject, updateDraft,
 *   } = useProspectScan();
 */

import { useState, useRef, useCallback, useEffect } from "react";
import {
  startScan as apiStartScan,
  stopScan as apiStopScan,
  streamScan,
  approveProspect as apiApprove,
  rejectProspect as apiReject,
  updateProspect as apiUpdate,
} from "./api";

export function useProspectScan() {
  const [prospects, setProspects] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanError, setScanError] = useState(null);
  const [newIds, setNewIds] = useState(new Set());

  const currentJobId = useRef(null);
  const eventSourceRef = useRef(null);

  // Clean up SSE on unmount
  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  // ── Start scan ────────────────────────────────────────────────────────────

  const startScan = useCallback(async ({ accounts, icp, maxPerAccount = 25 } = {}) => {
    if (scanning) return;
    setScanError(null);
    setScanning(true);
    setScanProgress(0);

    try {
      const { job_id } = await apiStartScan({ accounts, icp, maxPerAccount });
      currentJobId.current = job_id;

      // Open SSE stream
      const es = streamScan(job_id, {
        onProspect: (prospect) => {
          setProspects((prev) => [prospect, ...prev]);

          // Flag as "new" for 5 seconds (highlights the card)
          setNewIds((prev) => new Set([...prev, prospect.id]));
          setTimeout(() => {
            setNewIds((prev) => {
              const next = new Set(prev);
              next.delete(prospect.id);
              return next;
            });
          }, 5000);
        },

        onStatus: (status) => {
          const { accounts_done, accounts_total } = status;
          if (accounts_total > 0) {
            setScanProgress(Math.round((accounts_done / accounts_total) * 100));
          }
        },

        onError: (msg) => {
          setScanError(msg);
          setScanning(false);
        },

        onDone: () => {
          setScanProgress(100);
          setTimeout(() => setScanning(false), 600);
        },
      });

      eventSourceRef.current = es;
    } catch (err) {
      setScanError(err.message);
      setScanning(false);
    }
  }, [scanning]);

  // ── Stop scan ─────────────────────────────────────────────────────────────

  const stopScan = useCallback(async () => {
    eventSourceRef.current?.close();
    if (currentJobId.current) {
      await apiStopScan(currentJobId.current).catch(() => {});
    }
    setScanning(false);
    setScanProgress(0);
  }, []);

  // ── Prospect actions ──────────────────────────────────────────────────────

  const _patchLocal = (id, changes) => {
    setProspects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...changes } : p))
    );
  };

  const approve = useCallback(async (id, draft, send = false) => {
    _patchLocal(id, {
      status: send ? "sent" : "approved",
      email_draft: draft,
    });
    await apiApprove(id, draft, send);
  }, []);

  const reject = useCallback(async (id) => {
    _patchLocal(id, { status: "rejected" });
    await apiReject(id);
  }, []);

  const updateDraft = useCallback(async (id, draft) => {
    _patchLocal(id, { email_draft: draft });
    await apiUpdate(id, { email_draft: draft });
  }, []);

  return {
    prospects,
    scanning,
    scanProgress,
    scanError,
    newIds,
    startScan,
    stopScan,
    approve,
    reject,
    updateDraft,
  };
}
