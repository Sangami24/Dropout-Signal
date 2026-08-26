"""Runtime safeguards for the recovered unified dashboard.

These hooks keep calls tied to a real uploaded cohort and expose the Twilio
webhook state to the existing counselor and administrator screens.
"""

from __future__ import annotations

import json as _json
import os
import time
import threading
import uuid
from io import BytesIO
from pathlib import Path

from flask import jsonify, request

from ml_pipeline import active_metadata, active_records, restore_latest_run
import voice_server


LIVE_UI_SCRIPT = r'''
<style id="dataset-runtime-ui">
  /* Runtime transcript controls must inherit the dark dashboard theme on
     both the counselor and administrator pages. */
  .runtime-transcript-search { display:flex; gap:8px; align-items:center; margin:16px 0; }
  .runtime-transcript-search input {
    min-width:290px; padding:9px 11px; border:1px solid #30303a !important;
    border-radius:7px; background:#101017 !important; color:#f4f4f8 !important;
    color-scheme:dark; outline:none;
  }
  .runtime-transcript-search input::placeholder { color:#9292a0 !important; opacity:1; }
  .runtime-transcript-search input:focus { border-color:#bc8cff !important; box-shadow:0 0 0 2px rgba(188,140,255,.16); }
  .runtime-transcript-search button {
    padding:9px 13px; border:1px solid #30303a !important; border-radius:7px;
    background:#1b1b24 !important; color:#f4f4f8 !important; cursor:pointer;
  }
  .runtime-transcript-search button:hover { border-color:#bc8cff !important; }
  .runtime-transcript-search button.danger { background:#a92731 !important; border-color:#d83d47 !important; color:#fff !important; }
</style>
<script>
(() => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const transcriptMarkup = events => events.map(event => {
    const student = event.side === 'student';
    return `<article class="dataset-message ${student ? 'student' : 'asha'}"><span>${escapeHtml(event.speaker)}</span><p>${escapeHtml(event.text)}</p></article>`;
  }).join('');
  let liveSessions = {};
  let liveWhatsApp = [];

  function ensureLiveRows(session) {
    const studentId = String(session.student_id || '');
    if (!studentId) return;
    const selector = `[data-student-id="${CSS.escape(studentId)}"]`;
    ['full-transcript-panel', 'transcript-panel', 'admin-transcript-panel'].forEach(panelId => {
      const panel = document.getElementById(panelId);
      if (!panel || panel.querySelector(selector)) return;
      const row = document.createElement('details');
      row.className = 'operation-row dataset-conversation high manual-call';
      row.dataset.studentId = studentId;
      row.open = true;
      row.innerHTML = `<summary><strong>${escapeHtml(session.student_name || 'Achal Sangami')}</strong><span class="dataset-live">ACTIVE</span><span class="dataset-presence high"></span><em>HIGH RISK</em></summary><div class="dataset-thread call"></div>`;
      panel.prepend(row);
    });
  }

  function renderLiveTranscripts() {
    Object.values(liveSessions).forEach(session => {
      const events = session.transcript_events || [];
      if (!events.length || !session.student_id) return;
      ensureLiveRows(session);
      const selector = `[data-student-id="${CSS.escape(String(session.student_id))}"]`;
      document.querySelectorAll(selector).forEach(row => {
        const thread = row.querySelector('.dataset-thread.call');
        if (!thread) return;
        const signature = events.map(event => `${event.side}:${event.text}`).join('\u001f');
        if (thread.dataset.liveSignature === signature) return;
        thread.innerHTML = transcriptMarkup(events);
        thread.dataset.liveSignature = signature;
        if (row.open) thread.scrollTop = thread.scrollHeight;
      });
    });
  }

  function applyCallGate(status) {
    const ready = Boolean(status?.dataset_loaded);
    document.querySelectorAll('button').forEach(button => {
      if (!/call student|call students/i.test(button.textContent || '')) return;
      button.disabled = !ready;
      button.title = ready ? '' : 'Upload and score a dataset before calling students.';
      button.classList.toggle('dataset-call-disabled', !ready);
    });
  }

  async function refreshCallGate() {
    try {
      const response = await fetch('/api/dataset/status', {cache: 'no-store'});
      const status = await response.json();
      applyCallGate(status);
    } catch (_) {}
  }

  async function refreshLiveTranscripts() {
    try {
      const response = await fetch('/api/transcripts', {cache: 'no-store'});
      const payload = await response.json();
      liveSessions = payload.sessions || {};
      renderLiveTranscripts();
    } catch (_) {}
  }

  function whatsappMarkup(messages) {
    return messages.map(message => {
      const student = message.role === 'user';
      return `<article class="dataset-message ${student ? 'student' : 'asha'}"><span>${student ? 'ACHAL' : 'ASHA AI'}</span><p>${escapeHtml(message.content)}</p></article>`;
    }).join('');
  }

  function ensureLiveWhatsAppRows(conversation) {
    const studentId = 'STU-ACHAL';
    ['wa-convos-panel', 'admin-wa-panel'].forEach(panelId => {
      const panel = document.getElementById(panelId);
      if (!panel) return;
      let row = panel.querySelector(`[data-student-id="${studentId}"]`);
      if (!row) {
        row = document.createElement('details');
        row.className = 'operation-row dataset-conversation high manual-call';
        row.dataset.studentId = studentId;
        row.open = true;
        row.innerHTML = `<summary><strong>${escapeHtml(conversation.student_name || 'Achal Sangami')}</strong><span class="dataset-live">ACTIVE</span><span class="dataset-presence high"></span><em>HIGH RISK</em></summary><div class="dataset-thread whatsapp"></div>`;
        panel.prepend(row);
      }
    });
  }

  function renderLiveWhatsApp() {
    liveWhatsApp.forEach(conversation => {
      const messages = conversation.messages || [];
      if (!messages.length) return;
      ensureLiveWhatsAppRows(conversation);
      document.querySelectorAll('[data-student-id="STU-ACHAL"]').forEach(row => {
        const thread = row.querySelector('.dataset-thread.whatsapp');
        if (!thread) return;
        const signature = messages.map(message => `${message.role}:${message.content}`).join('\u001f');
        if (thread.dataset.liveSignature === signature) return;
        thread.innerHTML = whatsappMarkup(messages);
        thread.dataset.liveSignature = signature;
        if (row.open) thread.scrollTop = thread.scrollHeight;
      });
    });
  }

  async function refreshLiveWhatsApp() {
    try {
      const response = await fetch('/whatsapp/conversations', {cache: 'no-store'});
      const payload = await response.json();
      liveWhatsApp = (payload.conversations || []).filter(conversation =>
        /achal/i.test(String(conversation.student_name || conversation.profile_name || ''))
      );
      renderLiveWhatsApp();
    } catch (_) {}
  }

  function installTranscriptSearch() {
    [
      ['page-transcript', ['full-transcript-panel', 'transcript-panel']],
      ['page-admin-transcript', ['admin-transcript-panel']],
    ].forEach(([pageId, panelIds]) => {
      const page = document.getElementById(pageId);
      const panel = panelIds.map(id => document.getElementById(id)).find(Boolean);
      if (!page || !panel || page.querySelector('.runtime-transcript-search')) return;
      const toolbar = document.createElement('div');
      toolbar.className = 'operation-toolbar runtime-transcript-search';
      toolbar.innerHTML = '<input aria-label="Search call transcripts" placeholder="Search call transcripts..."><button type="button">Search</button><button type="button" class="danger">Reset</button>';
      const input = toolbar.querySelector('input');
      const filter = () => {
        const query = input.value.trim().toLowerCase();
        panel.querySelectorAll('.dataset-conversation').forEach(row => {
          row.hidden = Boolean(query) && !row.textContent.toLowerCase().includes(query);
        });
      };
      toolbar.querySelector('button').addEventListener('click', filter);
      toolbar.querySelector('.danger').addEventListener('click', () => { input.value = ''; filter(); });
      input.addEventListener('input', filter);
      const header = page.querySelector('.page-hdr');
      if (header) header.insertAdjacentElement('afterend', toolbar);
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  //  UPLOAD CONTROLLER — single, race-free implementation
  // ═══════════════════════════════════════════════════════════════════
  const BACKGROUND_UPLOAD_KEY = 'dropout-signal-background-upload';
  let _pollTimer = null;
  let _pollGeneration = 0;
  let _pollInFlight = false;

  function showUploadOverlay(job) {
    document.getElementById('dataset-training-overlay')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'dataset-training-overlay';
    const progress = Number(job.progress || 0);
    overlay.innerHTML = `<section class="dataset-training-card" role="status" aria-live="polite"><div class="dataset-progress-ring"><span>${progress.toFixed(1)}%</span></div><div><b>Uploading Dataset</b><p>${escapeHtml(job.filename || 'Your dataset')} is processing on the server. You can switch dashboards or browser tabs.</p><small>Uploading file...</small></div><button type="button" class="btn dataset-cancel-upload">Cancel Upload</button></section>`;
    overlay.querySelector('.dataset-cancel-upload').addEventListener('click', () => window.cancelDatasetUpload());
    document.body.appendChild(overlay);
    return overlay;
  }

  function updateUploadOverlay(job) {
    const overlay = document.getElementById('dataset-training-overlay') || showUploadOverlay(job);
    const ring = overlay.querySelector('.dataset-progress-ring');
    const pct = ring?.querySelector('span');
    const stage = overlay.querySelector('small');
    const title = overlay.querySelector('b');
    const detail = overlay.querySelector('p');
    const cancelBtn = overlay.querySelector('.dataset-cancel-upload');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    if (ring) ring.style.setProperty('--dataset-progress', `${progress * 3.6}deg`);
    if (pct) pct.textContent = `${progress.toFixed(1)}%`;
    if (stage) stage.textContent = job.message || 'Processing on the server...';
    if (title && job.state === 'uploading') title.textContent = 'Uploading Dataset';
    if (title && ['queued', 'processing'].includes(job.state)) title.textContent = 'Finalizing Dataset';
    if (title && job.state === 'complete') title.textContent = 'Dataset processing complete';
    if (detail && ['queued', 'processing'].includes(job.state)) detail.textContent = 'Training, scoring, and saving the active cohort. Safe to switch dashboards or browser tabs.';
    if (detail && job.state === 'complete') detail.textContent = 'The scored cohort is active. Refreshing this dashboard...';
    if (cancelBtn) cancelBtn.hidden = (job.state === 'complete');
  }

  function removeOverlay() { document.getElementById('dataset-training-overlay')?.remove(); }

  function clearUploadState() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
  }

  // ── Cancel ────────────────────────────────────────────────────────
  window.cancelDatasetUpload = async () => {
    const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
    if (!raw) { removeOverlay(); return; }
    let job;
    try { job = JSON.parse(raw); } catch (_) { clearUploadState(); removeOverlay(); return; }
    const btn = document.querySelector('#dataset-training-overlay .dataset-cancel-upload');
    if (btn) { btn.disabled = true; btn.textContent = 'Canceling...'; }
    try {
      await fetch('/api/dataset/cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({upload_id: job.id}), keepalive: true,
      });
    } finally {
      ++_pollGeneration;
      clearUploadState();
      removeOverlay();
      toast('Dataset upload canceled.', 'info');
    }
  };

  // ── Single server-authoritative poll ──────────────────────────────
  async function pollOnce(jobId, generation) {
    if (generation !== _pollGeneration) return 'stale';
    if (_pollInFlight) return 'busy';
    _pollInFlight = true;
    try {
      const response = await fetch(`/api/dataset/upload-status?job_id=${encodeURIComponent(jobId)}`, {cache: 'no-store'});
      if (generation !== _pollGeneration) return 'stale';
      if (!response.ok) {
        if (response.status === 404) {
          const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
          if (!raw) return 'gone';
          let stored; try { stored = JSON.parse(raw); } catch (_) { clearUploadState(); removeOverlay(); return 'gone'; }
          const age = Date.now() - Number(stored.created_at_ms || 0);
          if (stored.state === 'uploading' && age < 120000) return 'waiting';
          clearUploadState(); removeOverlay();
          toast('The upload job is no longer available. Please upload the CSV again.', 'err');
          return 'gone';
        }
        return 'error';
      }
      const serverJob = await response.json();
      if (generation !== _pollGeneration) return 'stale';
      updateUploadOverlay(serverJob);

      if (serverJob.state === 'complete') {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        // Remove localStorage BEFORE any reload so other tabs cannot read
        // a stale 'complete' snapshot and re-trigger completion.
        localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
        // Single-fire: only the first tab to see 'complete' for this job
        // triggers a reload. Other tabs detect the removed localStorage
        // key via their storage listener and clean up silently.
        const completionKey = `dropout-signal-upload-complete-${serverJob.id}`;
        if (!sessionStorage.getItem(completionKey)) {
          sessionStorage.setItem(completionKey, '1');
          setTimeout(() => window.location.reload(), 700);
        } else {
          // This tab already completed this job. Just remove the overlay.
          removeOverlay();
        }
        return 'complete';
      }
      if (serverJob.state === 'failed' || serverJob.state === 'canceled') {
        clearUploadState(); removeOverlay();
        toast(serverJob.state === 'canceled' ? 'Dataset upload canceled.' : (serverJob.error || 'Dataset upload failed.'), serverJob.state === 'canceled' ? 'info' : 'err');
        return 'terminal';
      }
      // Keep localStorage in sync so other tabs can pick up the job ID.
      // Never write 'complete' here — that path is handled above.
      const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
      if (raw) {
        try {
          const stored = JSON.parse(raw);
          if (stored.id === jobId) {
            localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify({...stored, ...serverJob, state: serverJob.state}));
          }
        } catch (_) {}
      }
      return 'active';
    } finally { _pollInFlight = false; }
  }

  // ── Resume / start polling ────────────────────────────────────────
  async function resumeUploadPolling() {
    const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
    if (!raw) { removeOverlay(); return; }
    let job;
    try { job = JSON.parse(raw); } catch (_) { clearUploadState(); removeOverlay(); return; }
    // Never revive a terminal state from another tab's leftover storage.
    if (['complete', 'failed', 'canceled'].includes(job.state)) {
      clearUploadState(); removeOverlay(); return;
    }
    const generation = ++_pollGeneration;
    // Show the last-known state while waiting for the server poll.
    updateUploadOverlay(job);
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }

    const result = await pollOnce(job.id, generation);
    if (generation !== _pollGeneration) return;
    if (result === 'complete' || result === 'terminal' || result === 'gone' || result === 'stale') return;

    // Start the regular interval poller.
    _pollTimer = setInterval(async () => {
      const r = await pollOnce(job.id, generation);
      if (r === 'complete' || r === 'terminal' || r === 'gone' || r === 'stale') {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
      }
    }, 800);
  }

  // ── Begin a new upload ────────────────────────────────────────────
  async function beginUpload(file) {
    if (!file) return;
    // Cancel any in-progress upload first.
    ++_pollGeneration;
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    const form = new FormData(); form.append('file', file);
    const job = {id: globalThis.crypto?.randomUUID?.() || `upload-${Date.now()}`, filename: file.name, state: 'uploading', progress: 0, created_at_ms: Date.now()};
    localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(job));
    updateUploadOverlay(job);
    try {
      const response = await fetch('/api/dataset/upload', {method: 'POST', body: form, headers: {'X-Dataset-Upload-Id': job.id}});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Dataset upload failed');
      // The server accepted the file and started background processing.
      const updated = {...job, ...payload, state: payload.state || 'queued'};
      localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(updated));
      await resumeUploadPolling();
    } catch (error) {
      clearUploadState(); removeOverlay();
      toast(error.message || 'Dataset upload failed.', 'err');
    }
  }

  // ── Capture file selection (before the legacy page handler) ───────
  document.addEventListener('change', event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.id !== 'dataset-file-input') return;
    event.stopImmediatePropagation();
    beginUpload(input.files?.[0]);
    input.value = '';
  }, true);

  // ── Cross-tab and visibility event handlers ───────────────────────
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) resumeUploadPolling();
  });
  window.addEventListener('focus', () => resumeUploadPolling());
  window.addEventListener('storage', event => {
    if (event.key !== BACKGROUND_UPLOAD_KEY) return;
    if (event.newValue) {
      // Another tab started or updated an upload — start polling.
      resumeUploadPolling();
    } else {
      // Another tab cleared the key (cancel or completion) — stop and clean up.
      ++_pollGeneration;
      if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
      removeOverlay();
    }
  });

  // ── Direct upload controller ──────────────────────────────────────
  // The user stays on this page during upload. Use the original synchronous
  // train/score/activate endpoint and a single local progress presentation.
  let directUpload = null;
  let directProgressTimer = null;
  const MIN_UPLOAD_DISPLAY_MS = 30000;

  function showUploadOverlay(job) {
    document.getElementById('dataset-training-overlay')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'dataset-training-overlay';
    overlay.innerHTML = `<section class="dataset-training-card" role="status" aria-live="polite"><div class="dataset-progress-ring"><span>0.0%</span></div><div><b>Uploading Dataset</b><p>${escapeHtml(job.filename || 'Your dataset')} is being uploaded.</p><small>Uploading dataset...</small></div><button type="button" class="btn dataset-cancel-upload">Cancel Upload</button></section>`;
    overlay.querySelector('.dataset-cancel-upload').addEventListener('click', () => window.cancelDatasetUpload());
    document.body.appendChild(overlay);
    return overlay;
  }

  function updateUploadOverlay(job) {
    const overlay = document.getElementById('dataset-training-overlay') || showUploadOverlay(job);
    const ring = overlay.querySelector('.dataset-progress-ring');
    const pct = ring?.querySelector('span');
    const title = overlay.querySelector('b');
    const detail = overlay.querySelector('p');
    const stage = overlay.querySelector('small');
    const cancel = overlay.querySelector('.dataset-cancel-upload');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    if (ring) ring.style.setProperty('--dataset-progress', `${progress * 3.6}deg`);
    if (pct) pct.textContent = `${progress.toFixed(1)}%`;
    const labels = {
      uploading: ['Uploading Dataset', 'Sending the CSV securely to the server.', 'Uploading dataset...'],
      reading: ['Reading Dataset', 'Checking columns and preparing the uploaded records.', 'Reading dataset...'],
      analyzing: ['Analyzing Dataset', 'Training models and scoring the uploaded cohort.', 'Analyzing dataset...'],
      finalizing: ['Finalizing Dataset', 'Saving the scored cohort and dataset-specific evidence.', 'Finalizing dataset...'],
      complete: ['Dataset processing complete', 'The uploaded dataset is active. Refreshing this dashboard...', 'Dataset trained, scored, and activated.'],
    };
    const label = labels[job.state] || labels.uploading;
    if (title) title.textContent = label[0];
    if (detail) detail.textContent = label[1];
    if (stage) stage.textContent = label[2];
    if (cancel) cancel.hidden = job.state === 'complete';
  }

  function directStage(progress) {
    if (progress < 18) return 'uploading';
    if (progress < 35) return 'reading';
    if (progress < 82) return 'analyzing';
    return 'finalizing';
  }

  function finishDirectUpload(active) {
    if (directProgressTimer) clearInterval(directProgressTimer);
    const render = () => {
      if (directUpload !== active || active.canceled) return;
      const progress = Math.min(100, ((Date.now() - active.startedAt) / MIN_UPLOAD_DISPLAY_MS) * 100);
      if (progress < 100) {
        updateUploadOverlay({...active.job, progress, state: directStage(progress)});
        return;
      }
      clearInterval(directProgressTimer); directProgressTimer = null;
      updateUploadOverlay({...active.job, progress: 100, state: 'complete'});
      localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
      directUpload = null;
      setTimeout(() => window.location.reload(), 700);
    };
    render();
    directProgressTimer = setInterval(render, 120);
  }

  window.cancelDatasetUpload = async () => {
    const active = directUpload;
    if (active) { active.canceled = true; active.controller.abort(); }
    if (directProgressTimer) clearInterval(directProgressTimer);
    directProgressTimer = null;
    directUpload = null;
    localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
    removeOverlay();
    if (active?.job?.id) {
      await fetch('/api/dataset/cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({upload_id: active.job.id}), keepalive: true,
      }).catch(() => {});
    }
    toast('Dataset upload canceled.', 'info');
  };

  async function beginUpload(file) {
    if (!file) return;
    if (directUpload) await window.cancelDatasetUpload();
    const job = {id: globalThis.crypto?.randomUUID?.() || `upload-${Date.now()}`, filename: file.name, progress: 0, state: 'uploading'};
    const active = {job, controller: new AbortController(), canceled: false, startedAt: Date.now()};
    directUpload = active;
    localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify({id: job.id, filename: job.filename, state: 'uploading'}));
    updateUploadOverlay(job);
    directProgressTimer = setInterval(() => {
      if (directUpload !== active) return;
      const progress = Math.min(94, ((Date.now() - active.startedAt) / MIN_UPLOAD_DISPLAY_MS) * 94);
      updateUploadOverlay({...job, progress, state: directStage(progress)});
    }, 260);
    try {
      const form = new FormData(); form.append('file', file);
      const response = await fetch('/api/dataset/upload', {
        method: 'POST', body: form, signal: active.controller.signal,
        headers: {'X-Dataset-Upload-Id': job.id},
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok || !payload.status?.dataset_loaded) throw new Error(payload.error || 'Dataset was not activated.');
      if (directUpload !== active || active.canceled) return;
      finishDirectUpload(active);
    } catch (error) {
      if (directUpload !== active || active.canceled || error.name === 'AbortError') return;
      clearInterval(directProgressTimer); directProgressTimer = null;
      directUpload = null;
      localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
      removeOverlay();
      toast(error.message || 'Dataset upload failed.', 'err');
    }
  }

  async function resumeUploadPolling() {
    // No background job is used. A stale key from an old page must never
    // recreate a fake progress overlay or alter a new upload.
    if (!directUpload) localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
  }

  function datasetInsightCards() {
    return [...document.querySelectorAll('.card-new')].filter(card => /AI Insights/i.test(card.querySelector('h3')?.textContent || ''));
  }

  function renderEmptyInsight(card) {
    const body = card.querySelector('.card-new-b');
    if (body) body.innerHTML = '<p style="font-size:13px;color:var(--text2);line-height:1.6">Upload and score a dataset to generate AI insights.</p>';
  }

  async function refreshDatasetInsights() {
    const cards = datasetInsightCards();
    if (!cards.length) return;
    try {
      const response = await fetch('/api/dataset/insights', {cache: 'no-store'});
      const data = await response.json();
      cards.forEach(card => {
        card.hidden = false;
        card.style.display = '';
        if (!data.dataset_loaded) { renderEmptyInsight(card); return; }
        const body = card.querySelector('.card-new-b');
        if (body) body.innerHTML = `<p style="font-size:13px;color:var(--text2);line-height:1.6">${escapeHtml(data.summary)}</p>`;
      });
    } catch (_) {
      cards.forEach(card => {
        card.hidden = false;
        card.style.display = '';
        renderEmptyInsight(card);
      });
    }
  }

  // Do not show the template's placeholder insight while dataset status is
  // still unknown. refreshDatasetInsights reveals only active-data insight.
  datasetInsightCards().forEach(card => {
    renderEmptyInsight(card);
  });

  document.addEventListener('DOMContentLoaded', () => {
    refreshCallGate();
    refreshLiveTranscripts();
    refreshLiveWhatsApp();
    installTranscriptSearch();
    resumeUploadPolling();
    refreshDatasetInsights();
    // The legacy dashboard still repaints its call cards. Re-apply the latest
    // webhook transcript in the same turn so it cannot alternate between the
    // greeting variant and the question variant.
    new MutationObserver(() => queueMicrotask(() => { renderLiveTranscripts(); renderLiveWhatsApp(); installTranscriptSearch(); }))
      .observe(document.body, {childList: true, subtree: true});
    setInterval(refreshCallGate, 3000);
    setInterval(refreshLiveTranscripts, 650);
    setInterval(refreshLiveWhatsApp, 900);
    setInterval(installTranscriptSearch, 1500);
    setInterval(refreshDatasetInsights, 5000);
  });
})();
</script>
'''


# ═══════════════════════════════════════════════════════════════════
#  FILE-BACKED JOB STATE (survives worker restarts)
# ═══════════════════════════════════════════════════════════════════

_RUNTIME_DIR = Path(
    os.environ.get(
        "DROPOUT_SIGNAL_RUNTIME_DIR",
        "/tmp/dropout_signal_runtime" if os.environ.get("VERCEL") else str(Path(__file__).resolve().parent / "runtime_data"),
    )
)
_JOBS_FILE = _RUNTIME_DIR / "upload_jobs.json"
_BACKGROUND_UPLOAD_LOCK = threading.RLock()


def _load_jobs() -> dict:
    """Read all background upload jobs from disk."""
    try:
        return _json.loads(_JOBS_FILE.read_text(encoding="utf-8")) if _JOBS_FILE.exists() else {}
    except Exception:
        return {}


def _save_jobs(jobs: dict) -> None:
    """Persist all background upload jobs to disk."""
    _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _JOBS_FILE.write_text(_json.dumps(jobs), encoding="utf-8")


def _get_job(job_id: str) -> dict | None:
    with _BACKGROUND_UPLOAD_LOCK:
        return _load_jobs().get(job_id)


def _set_job(job_id: str, data: dict) -> None:
    with _BACKGROUND_UPLOAD_LOCK:
        jobs = _load_jobs()
        jobs[job_id] = data
        _save_jobs(jobs)


def _update_job(job_id: str, updates: dict) -> None:
    with _BACKGROUND_UPLOAD_LOCK:
        jobs = _load_jobs()
        if job_id in jobs:
            jobs[job_id].update(updates)
            _save_jobs(jobs)


def _background_upload_snapshot(job):
    """Return a job with monotonic progress that reaches 100 only on success."""
    snapshot = dict(job)
    state = snapshot.get("state")
    if state == "complete":
        snapshot["progress"] = 100.0
    elif state in {"failed", "canceled"}:
        snapshot["progress"] = float(snapshot.get("progress") or 0.0)
    elif state == "queued":
        snapshot["progress"] = max(2.0, float(snapshot.get("progress") or 0.0))
    else:
        started = float(snapshot.get("processing_at") or snapshot.get("created_at") or time.time())
        elapsed = max(0.0, time.time() - started)
        # Asymptotically approach 99.4 while training. The display therefore
        # keeps advancing after a tab switch but cannot claim completion before
        # the original upload route confirms that the dataset was activated.
        estimated = 5.0 + 94.4 * (elapsed / (elapsed + 45.0))
        snapshot["progress"] = min(99.4, max(float(snapshot.get("progress") or 0.0), estimated))
    return snapshot


def _dataset_ready() -> bool:
    try:
        return bool(active_metadata()) and not active_records().empty
    except Exception:
        return False


def _manual_call_payload():
    """Use the designated live-call contact for every active dataset."""
    records = active_records().copy()
    if records.empty:
        return None
    if "final_risk_tier" in records:
        high = records[records["final_risk_tier"].astype(str).str.upper().eq("HIGH")]
        if not high.empty:
            records = high
    if "ml_risk_score" in records:
        records = records.sort_values("ml_risk_score", ascending=False)
    row = records.iloc[0]
    return {
        # The dashboard's live demo always calls the same consented test
        # contact; the uploaded cohort is used solely as the eligibility gate.
        "student_id": "STU-ACHAL",
        "student_name": "Achal Sangami",
        "ml_risk_score": float(row.get("ml_risk_score") or 0),
        "risk_tier": "HIGH",
    }


def install(app, namespace):
    """Install call gating, a real manual-call endpoint, and live UI sync."""

    # If a request or deploy lost only the small active-run marker while the
    # scored run files remain on disk, recover the newest completed run before
    # either dashboard reads its shared dataset status. An explicit Reset
    # writes a disabled marker, so restore_latest_run deliberately does not
    # resurrect a dataset the user reset.
    status_rule = next((rule for rule in app.url_map.iter_rules() if rule.rule == "/api/dataset/status"), None)
    if status_rule:
        original_dataset_status = app.view_functions[status_rule.endpoint]

        def recovered_dataset_status():
            if not active_metadata():
                restore_latest_run()
            return original_dataset_status()

        app.view_functions[status_rule.endpoint] = recovered_dataset_status

    # The legacy upload route trains synchronously inside the browser request.
    # Wrap it in a server worker after receiving the file so a tab switch does
    # not cancel scoring or leave an upload modal frozen in another dashboard.
    upload_rule = next((rule for rule in app.url_map.iter_rules() if rule.rule == "/api/dataset/upload"), None)
    if upload_rule:
        original_upload = app.view_functions[upload_rule.endpoint]
        cancel_rule = next((rule for rule in app.url_map.iter_rules() if rule.rule == "/api/dataset/cancel"), None)
        original_cancel = app.view_functions[cancel_rule.endpoint] if cancel_rule else None

        def background_dataset_upload():
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                return jsonify({"error": "Choose a CSV file to upload."}), 400
            file_bytes = upload.read()
            if not file_bytes:
                return jsonify({"error": "The selected CSV is empty."}), 400
            job_id = request.headers.get("X-Dataset-Upload-Id") or str(uuid.uuid4())
            filename = upload.filename
            _set_job(job_id, {
                "id": job_id,
                "filename": filename,
                "state": "queued",
                "message": "Dataset received. Starting background analysis\u2026",
                "created_at": time.time(),
            })

            def run_upload_job():
                _update_job(job_id, {
                    "state": "processing",
                    "processing_at": time.time(),
                    "progress": 5.0,
                    "message": "Training and scoring in the background\u2026",
                })
                try:
                    with app.test_request_context(
                        "/api/dataset/upload",
                        method="POST",
                        data={"file": (BytesIO(file_bytes), filename)},
                        headers={"X-Dataset-Upload-Id": job_id},
                    ):
                        response = app.make_response(original_upload())
                    payload = response.get_json(silent=True) or {}
                    if response.status_code >= 400:
                        raise RuntimeError(payload.get("error") or "Dataset analysis failed.")
                    status = payload.get("status") or {}
                    if not payload.get("ok") or not status.get("dataset_loaded"):
                        raise RuntimeError("Dataset processing finished without activating the uploaded cohort.")
                    # Check cancel before marking complete.
                    job = _get_job(job_id) or {}
                    if job.get("state") == "canceled":
                        return
                    _update_job(job_id, {
                        "state": "complete",
                        "message": "Dataset trained, scored, and activated.",
                        "status": status,
                        "progress": 100.0,
                        "completed_at": time.time(),
                    })
                except Exception as exc:
                    app.logger.exception("Background dataset upload failed")
                    job = _get_job(job_id) or {}
                    if job.get("state") == "canceled":
                        return
                    _update_job(job_id, {
                        "state": "failed",
                        "error": str(exc),
                        "message": "Background dataset processing failed.",
                        "completed_at": time.time(),
                    })

            threading.Thread(target=run_upload_job, name=f"dataset-upload-{job_id[:8]}", daemon=True).start()
            return jsonify({
                "ok": True,
                "id": job_id,
                "state": "queued",
                "filename": filename,
                "message": "Dataset received and processing in the background.",
            }), 202

        def background_dataset_upload_status():
            job_id = request.args.get("job_id", "")
            job = _get_job(job_id) if job_id else None
            if not job:
                return jsonify({"error": "Upload job not found."}), 404
            return jsonify(_background_upload_snapshot(job))

        def background_dataset_cancel():
            payload = request.get_json(silent=True) or {}
            job_id = str(payload.get("upload_id") or "").strip()
            response = app.make_response(original_cancel()) if original_cancel else jsonify({"ok": True, "canceled": True})
            job = _get_job(job_id) if job_id else None
            if job and job.get("state") != "complete":
                snapshot = _background_upload_snapshot(job)
                _update_job(job_id, {
                    "state": "canceled",
                    "message": "Dataset upload canceled.",
                    "progress": snapshot.get("progress", 0.0),
                    "completed_at": time.time(),
                })
            return response

        # Keep uploads on the original request path. It already performs the
        # validated train/score/activate flow atomically when the user stays on
        # the page; the background wrapper remains only as legacy code.
        app.view_functions[upload_rule.endpoint] = original_upload
        if not any(rule.rule == "/api/dataset/upload-status" for rule in app.url_map.iter_rules()):
            app.add_url_rule(
                "/api/dataset/upload-status",
                "background_dataset_upload_status",
                background_dataset_upload_status,
                methods=["GET"],
            )
        if cancel_rule and original_cancel:
            app.view_functions[cancel_rule.endpoint] = original_cancel

    def dataset_insights():
        """Return insight text derived only from the active scored cohort."""
        if not _dataset_ready():
            return jsonify({"dataset_loaded": False})
        records = active_records().copy()
        total = len(records)
        tiers = records.get("final_risk_tier")
        if tiers is not None:
            high = int(tiers.astype(str).str.upper().eq("HIGH").sum())
            medium = int(tiers.astype(str).str.upper().eq("MEDIUM").sum())
        else:
            scores = records.get("ml_risk_score")
            high = int((scores >= 0.67).sum()) if scores is not None else 0
            medium = int(((scores >= 0.34) & (scores < 0.67)).sum()) if scores is not None else 0
        return jsonify({
            "dataset_loaded": True,
            "total_students": total,
            "high_risk_students": high,
            "medium_risk_students": medium,
            "summary": f"This uploaded dataset contains {total:,} scored students, including {high:,} high-risk and {medium:,} medium-risk students.",
        })

    if not any(rule.rule == "/api/dataset/insights" for rule in app.url_map.iter_rules()):
        app.add_url_rule("/api/dataset/insights", "dataset_insights", dataset_insights, methods=["GET"])

    def manual_call():
        if not _dataset_ready():
            return jsonify({
                "error": "Upload and score a dataset before starting student calls.",
                "code": "dataset_required",
            }), 409
        student = _manual_call_payload()
        if not student:
            return jsonify({"error": "No scored student is available to call."}), 409
        phone = voice_server.DEMO_PHONE
        if not phone or not str(phone).startswith("+"):
            return jsonify({"error": "Set DEMO_PHONE to an E.164 phone number before calling."}), 503
        try:
            result = voice_server._start_call(
                student["student_id"],
                student["student_name"],
                phone,
                student["ml_risk_score"],
            )
        except Exception as exc:
            app.logger.exception("Manual call could not be started")
            return jsonify({"error": str(exc)}), 502
        if result.get("error"):
            return jsonify(result), 409 if result.get("code") == "dataset_required" else 503
        return jsonify({**student, **result})

    existing = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/manual-call"]
    if existing:
        for rule in existing:
            app.view_functions[rule.endpoint] = manual_call
    else:
        app.add_url_rule("/api/manual-call", "runtime_manual_call", manual_call, methods=["POST"])

    # The historical app replaced this endpoint with a local-only queue entry.
    # Keep its URL but dispatch it to the actual Twilio-backed implementation.
    for rule in app.url_map.iter_rules():
        if rule.rule == "/whatsapp/demo":
            app.view_functions[rule.endpoint] = voice_server.whatsapp_demo

    def dataset_experience():
        """Combine real webhook activity with synchronized active demo streams."""
        payload = namespace["_dataset_experience_payload"]()
        if payload.get("dataset_loaded"):
            real_calls = namespace["_merge_real_operations"]([])
            real_ids = {str(call.get("student_id")) for call in real_calls}
            active_dummies = []
            completed_dummies = []
            # Request more records so we can fill both active and completed
            # buckets even when there are fewer than 14 unique students.
            for index, student in enumerate(namespace["_dataset_records"](limit=24)):
                if str(student.get("student_id")) in real_ids:
                    continue
                dummy = namespace["_experience_conversation"](student, index)
                dummy["student_id"] = f"DEMO-{student.get('student_id', index)}"
                dummy["student_name"] = f"{student.get('student_name', 'Student')} (Demo)"
                elapsed_steps = int(time.time() // 2) + index
                call_turns = list(dummy.get("call", []))
                wa_turns = list(dummy.get("whatsapp", []))
                if len(active_dummies) < 7:
                    # Active: show a time-sliced subset of turns.
                    dummy["call"] = call_turns[:min(len(call_turns), 2 + elapsed_steps % max(1, len(call_turns)))]
                    dummy["whatsapp"] = wa_turns[:min(len(wa_turns), 2 + elapsed_steps % max(1, len(wa_turns)))]
                    dummy["status"] = "active"
                    dummy["summary"] = "Live synchronized demonstration stream."
                    active_dummies.append(dummy)
                elif len(completed_dummies) < 7:
                    # Completed: show all turns, mark as completed.
                    dummy["call"] = call_turns
                    dummy["whatsapp"] = wa_turns
                    dummy["status"] = "completed"
                    dummy["summary"] = "Completed demonstration transcript."
                    completed_dummies.append(dummy)
                if len(active_dummies) == 7 and len(completed_dummies) == 7:
                    break
            active_states = {"active", "ringing", "in-progress", "in_progress"}
            real_active = [call for call in real_calls if str(call.get("status", "")).lower() in active_states]
            real_completed = [call for call in real_calls if call not in real_active]
            # Active transcripts first, then completed — for both calls and WhatsApp.
            payload["conversations"] = real_active + active_dummies + real_completed + completed_dummies
        return jsonify(payload)

    # The old endpoint generated eight active conversations from every upload.
    # These restored samples are completed history, so they cannot replace or
    # interfere with Achal's real, webhook-backed call.
    for rule in app.url_map.iter_rules():
        if rule.rule == "/api/dataset/experience":
            app.view_functions[rule.endpoint] = dataset_experience

    # The restored templates are immutable historical strings. Append a small
    # script to both role views instead of duplicating their large HTML payload.
    for key in ("ADMIN_DASHBOARD", "COUNSELOR_DASHBOARD"):
        template = namespace.get(key)
        if isinstance(template, str) and "refreshLiveTranscripts" not in template:
            # Remove the legacy fabricated sentence from the HTML itself. The
            # card is populated only by the dataset-backed insights endpoint.
            template = template.replace(
                "Based on recent data, 87 students are at high risk of dropping out. Key factors include attendance (42%), low engagement (28%), and academic performance (30%). Early intervention can improve outcomes.",
                "",
            )
            namespace[key] = template.replace("</body>", LIVE_UI_SCRIPT + "</body>")
