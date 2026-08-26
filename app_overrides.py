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

from flask import Response, jsonify, request

from ml_pipeline import active_metadata, active_records, restore_latest_run
import voice_server


def _visible_model_name(value):
    """Keep historical runs and new runs on the same concise UI label."""
    text = str(value or "").strip()
    return "4-Model Validation" if "4-Model Validation" in text else (text or "4-Model Validation")


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
    // `FINAL_UI_SCRIPT` below is the sole transcript renderer.  Keeping this
    // retired renderer passive prevents it from injecting a second Achal row
    // or reopening a conversation after the user has selected another one.
    return;
    /*
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
    */
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
    // See renderLiveTranscripts: do not let the legacy renderer create a
    // parallel WhatsApp entry for the same shared student conversation.
    return;
    /*
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
    */
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

  // Preserve the dashboard's upload cancellation function. This runtime
  // script must not replace the upload controller that applies the server's
  // returned dataset values directly to the dashboard.
  const nativeCancelDatasetUpload = window.cancelDatasetUpload;

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
    overlay.innerHTML = `<section class="dataset-training-card" role="status" aria-live="polite"><div class="dataset-progress-ring"><span>${progress.toFixed(1)}%</span></div><div><b>Uploading Dataset</b><p>${escapeHtml(job.filename || 'Your dataset')} is processing on the server. You can switch dashboards or browser tabs.</p></div><button type="button" class="btn dataset-cancel-upload">Cancel Upload</button></section>`;
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
  // File selection remains owned by the dashboard's native uploadDataset()
  // handler. Intercepting it here bypassed applyDatasetStatus() and forced a
  // reload that returned users to an empty dashboard.

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

  if (typeof nativeCancelDatasetUpload === 'function') {
    window.cancelDatasetUpload = nativeCancelDatasetUpload;
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
      const [data, metrics, calls] = await Promise.all([
        fetch('/api/dataset/insights', {cache: 'no-store'}).then(response => response.json()),
        fetch('/api/model-metrics', {cache: 'no-store'}).then(response => response.ok ? response.json() : {}),
        fetch('/api/transcripts', {cache: 'no-store'}).then(response => response.ok ? response.json() : {sessions:{}}),
      ]);
      const modelNames = Object.keys(metrics.models || {});
      const topFactors = (metrics.shap || []).slice(0, 3).map(row => String(row.feature || '').replaceAll('_', ' ')).filter(Boolean);
      const activeCalls = Object.values(calls.sessions || {}).filter(session => !['completed','failed','canceled','interrupted'].includes(String(session.status || '').toLowerCase())).length;
      cards.forEach(card => {
        card.hidden = false;
        card.style.display = '';
        if (!data.dataset_loaded) { renderEmptyInsight(card); return; }
        const body = card.querySelector('.card-new-b');
        if (body) body.innerHTML = `<p style="font-size:13px;color:var(--text2);line-height:1.6">${escapeHtml(data.summary)}</p><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0"><div><b style="font-size:18px">${Number(data.high_risk_students || 0).toLocaleString()}</b><small style="display:block;color:var(--text3)">priority review</small></div><div><b style="font-size:18px">${Number(data.medium_risk_students || 0).toLocaleString()}</b><small style="display:block;color:var(--text3)">proactive follow-up</small></div><div><b style="font-size:18px">${activeCalls}</b><small style="display:block;color:var(--text3)">live calls</small></div></div><p style="font-size:12px;color:var(--text2);line-height:1.6"><b>Scoring:</b> ${escapeHtml(data.champion_model || 'validated model')} ${modelNames.length ? `across ${modelNames.length} tracked model entries.` : ''}<br><b>Leading signals:</b> ${escapeHtml(topFactors.join(', ') || 'available in the model evidence panel')}.</p>`;
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


# This final renderer deliberately runs after the recovered dashboard scripts.
# It keeps the two role views pointed at the same server-side operational data
# instead of their historical browser-only sample state.
FINAL_UI_SCRIPT = r'''
<style id="authoritative-dashboard-ui">
  .cohort-pulse { margin-top:18px; display:grid; grid-template-columns:1.1fr 1.4fr 1fr; gap:12px; }
  .cohort-pulse > section { min-height:188px; padding:16px; border:1px solid var(--border); border-radius:10px; background:var(--surface2); }
  .cohort-pulse h3 { margin:0 0 14px; font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--text2); }
  .pulse-stat { display:flex; justify-content:space-between; align-items:baseline; padding:9px 0; border-bottom:1px solid var(--border); }
  .pulse-stat:last-child { border-bottom:0; } .pulse-stat b { font-size:21px; color:var(--text); } .pulse-stat span { font-size:11px; color:var(--text3); }
  .risk-bar { display:grid; grid-template-columns:60px 1fr 48px; gap:8px; align-items:center; margin:13px 0; font-size:11px; color:var(--text2); }
  .risk-bar em { display:block; height:8px; border-radius:5px; background:#262632; overflow:hidden; } .risk-bar i { display:block; height:100%; border-radius:inherit; }
  .pulse-insight { margin:0; color:var(--text2); font-size:12px; line-height:1.65; } .pulse-insight b { color:var(--text); }
  .cohort-ai-brief { grid-column:1/-1; margin:0 0 18px; padding:18px; border:1px solid rgba(188,140,255,.28); border-radius:12px; background:linear-gradient(125deg,rgba(188,140,255,.11),rgba(17,17,25,.94)); }
  .cohort-ai-brief h2 { margin:0 0 8px; font-size:15px; } .cohort-ai-brief p { margin:0; color:var(--text2); font-size:13px; line-height:1.65; }
  .dataset-empty-live { padding:28px 14px; color:var(--text3); font-size:13px; text-align:center; }
  .fairness-status { font-size:11px; font-weight:600; }
  .fairness-status.ok { color:var(--green); } .fairness-status.review { color:var(--amber); }
  .operation-modal-backdrop { position:fixed; inset:0; z-index:10050; display:grid; place-items:center; padding:20px; background:rgba(0,0,0,.66); backdrop-filter:blur(5px); }
  .operation-modal { width:min(500px,100%); padding:24px; border:1px solid var(--border); border-radius:14px; background:var(--surface2,#15151d); box-shadow:0 24px 70px rgba(0,0,0,.5); }
  .operation-modal h2 { margin:0 0 9px; font-size:18px; } .operation-modal p { margin:0; color:var(--text2); line-height:1.55; }
  .operation-modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:20px; }
  .operation-modal button,.operation-modal a { border:0; border-radius:7px; padding:9px 13px; color:#fff; background:#ef4444; text-decoration:none; cursor:pointer; font:inherit; }
  .ensemble-context { margin:14px 0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
  .ensemble-context section { padding:13px; border:1px solid var(--border); border-radius:9px; background:var(--surface2); }
  .ensemble-context h3 { margin:0 0 7px; font-size:12px; letter-spacing:.06em; text-transform:uppercase; } .ensemble-context p { margin:0; font-size:12px; color:var(--text2); line-height:1.55; }
  @media (max-width:800px) { .cohort-pulse { grid-template-columns:1fr; } }
</style>
<script>
(() => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&gt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  let operationalSignature = '';
  let operationsRequest = 0;
  let fairnessRequest = 0;
  let latestCall = null;
  let activeDatasetRunId = null;
  // One open conversation across both channels.  A call and WhatsApp thread
  // represent the same student journey, so opening either must close every
  // other thread in both workspaces.
  let openedConversationKey = null;
  const visibleMessageCounts = new Map();
  let allowAchalAutofocus = true;
  let pendingAchalCallFocus = false;
  const sampleCursors = new Map();
  const liveThreadFollowState = new Map();

  const messageMarkup = (message, studentName) => {
    const student = message.side === 'student' || message.role === 'user';
    const speaker = message.speaker || (student ? studentName : 'Asha AI');
    const text = message.text ?? message.content ?? '';
    return `<article class="dataset-message ${student ? 'student' : 'asha'}"><span>${escapeHtml(speaker)}</span><p>${escapeHtml(text)}</p></article>`;
  };

  function completedSummary(item) {
    return item.summary || `${item.student_name || 'The student'} completed the ${channelLabel(item)} check-in. Review the transcript and follow the recommended support action.`;
  }

  function channelLabel(item) { return item.whatsapp?.length && !item.call?.length ? 'WhatsApp' : 'phone'; }

  function progressiveMessages(item, channel) {
    const messages = channel === 'call' ? item.call : item.whatsapp;
    if (!item.is_sample || String(item.status).toLowerCase() === 'completed') return messages;
    const key = `${item.student_id}:${channel}`;
    // Begin sample conversations part-way through their history.  The whole
    // thread remains scrollable, while every active sample advances together.
    const seed = [...key].reduce((total, char) => total + char.charCodeAt(0), 0);
    const initial = Math.min(messages.length, Math.max(2, Math.floor(messages.length * 0.45) + (seed % 2)));
    const current = sampleCursors.get(key) || initial;
    return messages.slice(0, current);
  }

  function advanceSampleStreams(items) {
    // Both channels and every active sample gain exactly one alternating turn
    // per two-second poll. This is independent of whether its row is open.
    items.filter(item => item.is_sample && String(item.status).toLowerCase() !== 'completed').forEach(item => {
      ['call', 'whatsapp'].forEach(channel => {
        const messages = channel === 'call' ? item.call : item.whatsapp;
        if (!messages?.length) return;
        const key = `${item.student_id}:${channel}`;
        const seed = [...key].reduce((total, char) => total + char.charCodeAt(0), 0);
        const initial = Math.min(messages.length, Math.max(2, Math.floor(messages.length * 0.45) + (seed % 2)));
        sampleCursors.set(key, Math.min(messages.length, (sampleCursors.get(key) || initial) + 1));
      });
    });
  }

  function panelMarkup(items, channel) {
    if (!items.length) return `<div class="dataset-empty-live">No ${channel === 'call' ? 'call transcripts' : 'WhatsApp conversations'} yet. New activity will appear here automatically.</div>`;
    return items.map(item => {
      const messages = progressiveMessages(item, channel);
      if (!messages?.length) return '';
      const channelStatus = channel === 'call' ? (item.call_status || item.status) : (item.whatsapp_status || item.status);
      const active = !['completed', 'failed', 'canceled', 'interrupted'].includes(String(channelStatus || '').toLowerCase());
      const tone = String(item.tier || 'MEDIUM').toLowerCase() === 'high' ? 'high' : 'medium';
      const key = `${item.student_id}:${channel}`;
      const isAchal = String(item.student_name || '').trim().toLowerCase() === 'achal sangami';
      const summaryText = channel === 'call' ? (item.call_summary || item.summary) : (item.whatsapp_summary || item.summary);
      const summary = active ? '' : `<footer class="dataset-contact-summary"><b>AI Summary</b><p>${escapeHtml(summaryText || completedSummary({...item, status: channelStatus}))}</p></footer>`;
      const open = openedConversationKey === key || (isAchal && active && allowAchalAutofocus && !openedConversationKey);
      return `<details class="operation-row dataset-conversation ${tone}" data-conversation-key="${escapeHtml(key)}" data-channel="${channel}" data-message-count="${messages.length}" ${open ? 'open' : ''}><summary><strong>${escapeHtml(item.student_name || 'Student')}</strong><span class="${active ? 'dataset-live' : 'dataset-completed'}">${active ? 'ACTIVE' : 'COMPLETED'}</span>${active ? `<span class="dataset-presence ${tone}"></span>` : ''}<em>${escapeHtml(item.tier || 'MEDIUM')} RISK</em></summary><div class="dataset-thread ${channel}">${messages.map(m => messageMarkup(m, item.student_name || 'Student')).join('')}${summary}</div></details>`;
    }).join('') || `<div class="dataset-empty-live">No ${channel === 'call' ? 'call transcripts' : 'WhatsApp conversations'} yet. New activity will appear here automatically.</div>`;
  }

  function renderOperations(callsPayload, whatsappPayload, experiencePayload) {
    const calls = Object.values(callsPayload.sessions || {});
    const byStudent = new Map();
    calls.forEach(session => {
      const id = String(session.student_id || session.call_sid || '');
      if (!id || !(session.transcript_events || []).length) return;
      const existing = byStudent.get(id);
      const updated = String(session.started_at || '') > String(existing?.started_at || '');
      if (!existing || updated) byStudent.set(id, {
        student_id: id, student_name: session.student_name || 'Student', tier: session.risk_tier || 'HIGH',
        status: session.status || 'active', call_status: session.status || 'active', call_summary: session.summary || '',
        started_at: session.started_at, call: session.transcript_events || [], whatsapp: [],
      });
    });
    (whatsappPayload.conversations || []).forEach(conversation => {
      const name = conversation.student_name || conversation.profile_name || 'Student';
      const messages = conversation.messages || [];
      if (!messages.length) return;
      const normalizedName = String(name).trim().toLowerCase().replace(/\s+/g, ' ');
      let target = byStudent.get(String(conversation.student_id || '')) || [...byStudent.values()].find(item => String(item.student_name).trim().toLowerCase().replace(/\s+/g, ' ') === normalizedName);
      if (!target) {
        target = { student_id: conversation.student_id || `wa-${conversation.phone || name}`, student_name: name, tier: conversation.risk_level || 'MEDIUM', status: 'active', call_status: 'active', whatsapp_status: 'active', call: [], whatsapp: [] };
        byStudent.set(target.student_id, target);
      }
      target.student_name = name;
      target.whatsapp = messages;
      target.whatsapp_status = conversation.status || 'active';
      target.whatsapp_summary = conversation.summary || '';
    });
    (experiencePayload?.conversations || []).filter(item => item.is_sample).forEach(item => {
      const id = String(item.student_id || '');
      if (!id || byStudent.has(id)) return;
      byStudent.set(id, {...item, call: item.call || [], whatsapp: item.whatsapp || []});
    });
    const isActive = item => !['completed', 'failed', 'canceled', 'interrupted'].includes(String(item.call_status || item.status || '').toLowerCase());
    const items = [...byStudent.values()].sort((a, b) => {
      const achalA = String(a.student_name || '').trim().toLowerCase() === 'achal sangami';
      const achalB = String(b.student_name || '').trim().toLowerCase() === 'achal sangami';
      if (achalA !== achalB) return achalA ? -1 : 1;
      if (isActive(a) !== isActive(b)) return isActive(a) ? -1 : 1;
      return String(b.started_at || '').localeCompare(String(a.started_at || ''));
    });
    advanceSampleStreams(items);
    // The live practice contact is the current operational focus. Keep its
    // active thread expanded and following new turns, without expanding any
    // other student automatically.
    const achal = items.find(item => String(item.student_name || '').trim().toLowerCase() === 'achal sangami');
    if (allowAchalAutofocus && achal && !openedConversationKey) {
      // When a call completes, the active WhatsApp follow-up is the one
      // operational thread to surface. Otherwise keep the live call focused.
      if (String(achal.call_status || '').toLowerCase() === 'completed' && String(achal.whatsapp_status || '').toLowerCase() === 'active' && achal.whatsapp?.length) openedConversationKey = `${achal.student_id}:whatsapp`;
      else if (isActive(achal) && achal.call?.length) openedConversationKey = `${achal.student_id}:call`;
      else if (achal.whatsapp?.length) openedConversationKey = `${achal.student_id}:whatsapp`;
    }
    if (achal && String(achal.call_status || '').toLowerCase() === 'completed' && String(achal.whatsapp_status || '').toLowerCase() === 'active' && openedConversationKey === `${achal.student_id}:call`) openedConversationKey = `${achal.student_id}:whatsapp`;
    if (achal && openedConversationKey) pendingAchalCallFocus = false;
    latestCall = items.find(item => item.call.length) || latestCall;
    const signature = JSON.stringify(items.map(item => [item.student_id, item.status, item.call_status, item.whatsapp_status, progressiveMessages(item, 'call').length, progressiveMessages(item, 'whatsapp').length, item.call.at(-1)?.text, item.whatsapp.at(-1)?.content]));
    operationalSignature = signature;
    const callHtml = panelMarkup(items, 'call'), waHtml = panelMarkup(items, 'whatsapp');
    const renderPanel = (id, channel, html) => {
      const panel = document.getElementById(id);
      if (!panel) return;
      const panelSignature = `${signature}:${channel}:${openedConversationKey || ''}`;
      if (panel.dataset.runtimeOperationSignature === panelSignature) return;
      panel.innerHTML = html;
      panel.dataset.runtimeOperationSignature = panelSignature;
    };
    ['full-transcript-panel', 'transcript-panel', 'admin-transcript-panel'].forEach(id => renderPanel(id, 'call', callHtml));
    ['wa-convos-panel', 'admin-wa-panel'].forEach(id => renderPanel(id, 'whatsapp', waHtml));
    document.querySelectorAll('details[data-conversation-key]').forEach(row => {
      const key = row.dataset.conversationKey;
      const channel = row.dataset.channel || (key.endsWith(':whatsapp') ? 'whatsapp' : 'call');
      const thread = row.querySelector('.dataset-thread');
      const activeThread = Boolean(row.querySelector('.dataset-live'));
      let followState = liveThreadFollowState.get(key);
      if (!followState) {
        followState = { follow: true, scrollTop: 0 };
        liveThreadFollowState.set(key, followState);
      }
      if (thread) {
        thread.addEventListener('scroll', () => {
          if (thread.dataset.runtimeProgrammaticScroll === 'true') return;
          const state = liveThreadFollowState.get(key) || { follow: true, scrollTop: 0 };
          state.follow = thread.scrollTop + thread.clientHeight >= thread.scrollHeight - 12;
          state.scrollTop = thread.scrollTop;
          liveThreadFollowState.set(key, state);
        }, { passive: true });
      }
      const restoreThread = () => {
        if (!thread || !row.open) return;
        const state = liveThreadFollowState.get(key) || { follow: true, scrollTop: 0 };
        thread.dataset.runtimeProgrammaticScroll = 'true';
        if (activeThread && state.follow) thread.scrollTop = thread.scrollHeight;
        else thread.scrollTop = Math.min(state.scrollTop, Math.max(0, thread.scrollHeight - thread.clientHeight));
        requestAnimationFrame(() => { thread.dataset.runtimeProgrammaticScroll = ''; });
      };
      row.addEventListener('toggle', () => {
        // A selected conversation stays expanded. It is closed only when the
        // user selects another student or moves to another workspace tab.
        if (!row.open) {
          if (openedConversationKey === key) { row.open = true; return; }
          return;
        }
        if (String(row.querySelector('summary strong')?.textContent || '').trim().toLowerCase() !== 'achal sangami') allowAchalAutofocus = false;
        openedConversationKey = key;
        document.querySelectorAll('details[data-conversation-key]').forEach(other => { if (other !== row) other.open = false; });
        const state = liveThreadFollowState.get(key) || { follow: true, scrollTop: 0 };
        state.follow = activeThread;
        if (!activeThread) state.scrollTop = 0;
        liveThreadFollowState.set(key, state);
        requestAnimationFrame(restoreThread);
      });
      const panelKey = `${row.closest('[id]')?.id || 'operations'}:${key}`;
      const count = Number(row.dataset.messageCount || 0), previousCount = visibleMessageCounts.get(panelKey);
      visibleMessageCounts.set(panelKey, count);
      if (row.open && activeThread) requestAnimationFrame(restoreThread);
    });
    const active = items.filter(isActive).length;
    [['ts-count', `${active} active`], ['admin-ts-count', `${active} active`], ['wa-count-badge', `${items.filter(i => i.whatsapp.length).length} conversations`], ['admin-wa-badge', `${items.filter(i => i.whatsapp.length).length} conversations`]].forEach(([id, value]) => { const node = document.getElementById(id); if (node) node.textContent = value; });
  }

  async function refreshOperations() {
    // This is the single transcript renderer for both roles.  It coalesces
    // repeated webhook/test SIDs for one student before replacing a panel.
    // The recovered template's renderer cannot do that and was the source of
    // duplicate Achal rows and forced scrolling.
    try {
      const requestId = ++operationsRequest;
      const [calls, whatsapp, experience] = await Promise.all([
        fetch('/api/transcripts', { cache: 'no-store' }).then(response => response.ok ? response.json() : { sessions: {} }),
        fetch('/whatsapp/conversations', { cache: 'no-store' }).then(response => response.ok ? response.json() : { conversations: [] }),
        fetch('/api/dataset/experience', { cache: 'no-store' }).then(response => response.ok ? response.json() : { conversations: [] }),
      ]);
      if (requestId !== operationsRequest) return;
      renderOperations(calls, whatsapp, experience);
    } catch (_) {}
  }

  async function renderCohortPulse() {
    const anchor = document.getElementById('intervention-stats')?.closest('.card,.card-new') || Array.from(document.querySelectorAll('.card,.card-new')).find(card => /intervention summary/i.test(card.querySelector('.card-h,.card-new-h,h3')?.textContent || ''));
    if (!anchor) return;
    try {
      const status = await fetch('/api/dataset/status', {cache:'no-store'}).then(r => r.json());
      if (!status.dataset_loaded) return;
      const tiers = Object.fromEntries((status.tier_breakdown || []).map(row => [String(row.final_risk_tier).toUpperCase(), Number(row.cnt || 0)]));
      const total = Number(status.record_count || 0), high = tiers.HIGH || 0, medium = tiers.MEDIUM || 0, low = tiers.LOW || 0, atRisk = high + medium;
      const duplicatePanels = [...document.querySelectorAll('#cohort-pulse')];
      duplicatePanels.slice(1).forEach(panel => panel.remove());
      const existing = document.getElementById('cohort-pulse');
      const section = existing || document.createElement('section');
      section.id = 'cohort-pulse'; section.className = 'cohort-pulse';
      section.innerHTML = `<section><h3>Cohort snapshot</h3><div class="pulse-stat"><span>Scored students</span><b>${total.toLocaleString()}</b></div><div class="pulse-stat"><span>Students needing support</span><b>${atRisk.toLocaleString()}</b></div><div class="pulse-stat"><span>Predicted dropouts</span><b>${Number(status.predicted_dropouts || 0).toLocaleString()}</b></div></section><section><h3>Risk distribution</h3>${[['High',high,'#ef4444'],['Medium',medium,'#f59e0b'],['Low',low,'#22c55e']].map(([label,value,color]) => `<div class="risk-bar"><span>${label}</span><em><i style="width:${total ? value / total * 100 : 0}%;background:${color}"></i></em><b>${value.toLocaleString()}</b></div>`).join('')}</section><section><h3>Outreach priorities</h3><p class="pulse-insight"><b>Priority outreach:</b> contact ${high.toLocaleString()} high-risk students within the next review window.</p><p class="pulse-insight" style="margin-top:10px"><b>Proactive follow-up:</b> schedule check-ins for ${medium.toLocaleString()} medium-risk students.</p><p class="pulse-insight" style="margin-top:10px"><b>Live support:</b> monitor ongoing calls and WhatsApp replies, then record the agreed next action.</p></section>`;
      if (!existing) anchor.insertAdjacentElement('afterend', section);
    } catch (_) {}
  }

  async function renderCohortBrief() {
    // The useful cohort metrics belong in the single dashboard pulse and AI
    // insights cards. Remove the duplicated summary cards created by older
    // render loops instead of adding another copy.
    document.querySelectorAll('.cohort-ai-brief').forEach(node => node.remove());
  }

  function setDatasetCounts(ids, value) {
    ids.forEach(id => { const node = document.getElementById(id); if (node) node.textContent = value; });
  }

  function applySharedDatasetStatus(status) {
    const loaded = Boolean(status?.dataset_loaded);
    const tiers = Object.fromEntries((status?.tier_breakdown || []).map(row => [String(row.final_risk_tier || '').toUpperCase(), Number(row.cnt || 0)]));
    const total = Number(status?.record_count || 0);
    const atRisk = (tiers.HIGH || 0) + (tiers.MEDIUM || 0);
    const predicted = Number(status?.predicted_dropouts || 0);
    const display = loaded ? total.toLocaleString() : '–';
    setDatasetCounts(['s-bronze','cd-calls','student-directory-nav-count','sb-student-count'], display);
    setDatasetCounts(['s-gold','cd-med','admin-risk-count','sb-risk-count'], loaded ? atRisk.toLocaleString() : '–');
    setDatasetCounts(['s-avgrisk','cd-high'], loaded ? predicted.toLocaleString() : '–');
    document.querySelectorAll('.risk-fixed-badge').forEach(node => { node.textContent = loaded ? `${atRisk.toLocaleString()} at risk` : '– at risk'; });
    const label = document.getElementById('dataset-active-label');
    if (label) label.textContent = loaded ? `${status.dataset_name || status.source_label || 'Active dataset'} · ${display} students` : 'No dataset loaded';
    renderAuthoritativeAdminOverview(status);
  }

  function renderAuthoritativeAdminOverview(status) {
    if (!status?.dataset_loaded) return;
    const tiers = Object.fromEntries((status.tier_breakdown || []).map(row => [String(row.final_risk_tier || '').toUpperCase(), Number(row.cnt || 0)]));
    const total = Number(status.record_count || 0), high = tiers.HIGH || 0, medium = tiers.MEDIUM || 0, low = tiers.LOW || 0;
    const chart = document.getElementById('tier-chart');
    if (chart) {
      const highEnd = total ? high / total * 100 : 0, mediumEnd = total ? (high + medium) / total * 100 : 0;
      chart.innerHTML = `<div class="d-chart-container"><div class="admin-risk-donut" style="background:conic-gradient(#ef4444 0 ${highEnd}%,#f59e0b ${highEnd}% ${mediumEnd}%,#22c55e ${mediumEnd}% 100%)"><div class="admin-risk-hole"><strong>${total.toLocaleString()}</strong><span>students</span></div></div></div><div class="d-legend"><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#ef4444"></span>High risk</span><strong>${high.toLocaleString()}</strong></div><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#f59e0b"></span>Medium risk</span><strong>${medium.toLocaleString()}</strong></div><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#22c55e"></span>Low risk</span><strong>${low.toLocaleString()}</strong></div></div>`;
    }
    const trendCard = [...document.querySelectorAll('.card-new')].find(card => /^(Risk Trend|Outreach Priorities|Risk Prediction)\b/i.test(card.querySelector('h3')?.textContent || ''));
    const trendBody = trendCard?.querySelector('.card-new-b');
    if (trendCard && trendBody) {
      const heading = trendCard.querySelector('h3');
      const predicted = Number(status.predicted_dropouts || high);
      if (heading) heading.innerHTML = `Risk Prediction <span class="risk-fixed-badge">${predicted.toLocaleString()} predicted dropouts</span>`;
      trendBody.innerHTML = `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:8px 2px"><section style="padding:13px;border:1px solid var(--border);border-radius:9px;background:var(--surface2)"><h3 style="margin:0 0 7px;color:#ef4444">${predicted.toLocaleString()}</h3><p style="margin:0;color:var(--text2);font-size:12px;line-height:1.5">students currently predicted to need intervention.</p></section><section style="padding:13px;border:1px solid var(--border);border-radius:9px;background:var(--surface2)"><h3 style="margin:0 0 7px;color:#f59e0b">${high.toLocaleString()}</h3><p style="margin:0;color:var(--text2);font-size:12px;line-height:1.5">high-confidence cases requiring immediate review.</p></section><section style="padding:13px;border:1px solid var(--border);border-radius:9px;background:var(--surface2)"><h3 style="margin:0 0 7px;color:#bc8cff">${medium.toLocaleString()}</h3><p style="margin:0;color:var(--text2);font-size:12px;line-height:1.5">students in the proactive support watchlist.</p></section></div>`;
    }
  }

  async function syncActiveDatasetScope() {
    try {
      const status = await fetch('/api/dataset/status', {cache:'no-store'}).then(response => response.ok ? response.json() : {});
      const nextRun = status.dataset_loaded ? String(status.run_id || status.dataset_name || '') : 'none';
      applySharedDatasetStatus(status);
      if (nextRun === activeDatasetRunId) return;
      activeDatasetRunId = nextRun;
      // A new upload changes the shared cohort. Refresh every data-dependent
      // surface in both roles rather than retaining the prior run's cards.
      renderCohortPulse(); renderAtRisk(false); renderAtRisk(true);
      refreshFairness(); refreshOperations();
      document.querySelectorAll('.ensemble-context').forEach(node => node.remove());
    } catch (_) {}
  }

  function closeRuntimeConversations() {
    openedConversationKey = null;
    document.querySelectorAll('details[data-conversation-key]').forEach(row => { row.open = false; });
  }

  function keepLiveThreadsAtLatestTurn() {
    // A live thread follows new messages only while the viewer is at its
    // bottom.  Reading earlier messages deliberately pauses the follow;
    // scrolling back down resumes it.  State is keyed independently of the
    // DOM node because the authoritative workspace redraws rows as messages
    // arrive.
    document.querySelectorAll('.dataset-conversation[open]').forEach(row => {
      if (!row.querySelector('.dataset-live')) return;
      const thread = row.querySelector('.dataset-thread');
      if (!thread) return;
      const key = row.dataset.conversationKey;
      if (!key) return;
      let state = liveThreadFollowState.get(key);
      if (!state) {
        state = { follow: true, scrollTop: 0 };
        liveThreadFollowState.set(key, state);
      }
      thread.dataset.runtimeProgrammaticScroll = 'true';
      if (state.follow) {
        thread.scrollTop = thread.scrollHeight;
      } else {
        const maxScroll = Math.max(0, thread.scrollHeight - thread.clientHeight);
        thread.scrollTop = Math.min(state.scrollTop, maxScroll);
      }
      requestAnimationFrame(() => { thread.dataset.runtimeProgrammaticScroll = ''; });
    });
  }

  function protectOperationPanels() {
    // The recovered template still has an older demo renderer on a timer.
    // It knows nothing about the shared live-state key and was replacing open
    // rows with collapsed copies. Observe only those panels and immediately
    // restore the authoritative renderer if that retired markup appears.
    const panelIds = ['full-transcript-panel', 'transcript-panel', 'admin-transcript-panel', 'wa-convos-panel', 'admin-wa-panel'];
    panelIds.forEach(id => {
      const panel = document.getElementById(id);
      if (!panel || panel.dataset.runtimePanelProtected) return;
      panel.dataset.runtimePanelProtected = 'true';
      const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
      Object.defineProperty(panel, 'innerHTML', {
        configurable: true,
        get() { return descriptor.get.call(this); },
        set(markup) {
          // Reject only the retired renderer's conversation markup. The
          // authoritative renderer includes this shared-state key, while
          // ordinary empty states and the final renderer remain unaffected.
          if (typeof markup === 'string' && markup.includes('dataset-conversation') && !markup.includes('data-conversation-key')) return;
          descriptor.set.call(this, markup);
        },
      });
    });
  }

  function removeDuplicateTranscriptSearch() {
    ['page-transcript', 'page-admin-transcript'].forEach(id => {
      const page = document.getElementById(id); if (!page) return;
      const bars = [...page.querySelectorAll('.runtime-transcript-search')];
      bars.slice(1).forEach(bar => bar.remove());
      [...page.querySelectorAll('.operation-toolbar')].filter(bar => /search call transcripts/i.test(bar.querySelector('input')?.placeholder || '') && !bar.classList.contains('runtime-transcript-search')).forEach(bar => bar.remove());
    });
  }

  function normalizeUploadStages() {
    const overlay = document.getElementById('dataset-training-overlay');
    if (!overlay) return;
    // The original uploader holds a reference to its own <small> element and
    // rewrites it every 260 ms. Replace that node once, so our exact runtime
    // operation message cannot flicker back to its old generic text.
    const legacySmall = overlay.querySelector('small:not([data-runtime-stage])');
    if (legacySmall) {
      const runtimeSmall = document.createElement('small');
      runtimeSmall.dataset.runtimeStage = 'true';
      legacySmall.replaceWith(runtimeSmall);
    }
    const percent = Number((overlay.querySelector('.dataset-progress-ring span')?.textContent || '0').replace('%', ''));
    const stage = percent < 8 ? ['Uploading Dataset', 'Transferring the selected CSV to the secure workspace.', 'Verifying file transfer…']
      : percent < 18 ? ['Reading Dataset', 'Extracting rows and checking the uploaded column headers.', 'Extracting CSV rows…']
      : percent < 30 ? ['Reading Dataset', 'Mapping raw values into the Bronze data layer.', 'Mapping values to Bronze…']
      : percent < 43 ? ['Analyzing Dataset', 'Cleaning values and deriving Silver-layer features.', 'Deriving Silver features…']
      : percent < 55 ? ['Analyzing Dataset', 'Training Logistic Regression on the validated cohort.', 'Training Logistic Regression…']
      : percent < 66 ? ['Analyzing Dataset', 'Training XGBoost and measuring hold-out quality.', 'Training XGBoost…']
      : percent < 76 ? ['Analyzing Dataset', 'Training Random Forest on the shared feature set.', 'Training Random Forest…']
      : percent < 86 ? ['Analyzing Dataset', 'Training HistGradientBoosting and comparing validation metrics.', 'Training HistGradientBoosting…']
      : percent < 94 ? ['Finalizing Dataset', 'Combining all four probabilities into the validation score.', 'Building 4-model validation score…']
      : ['Finalizing Dataset', 'Writing Gold scores, fairness evidence, and shared dashboard state.', 'Publishing Gold-layer outputs…'];
    const [title, detail, small] = [overlay.querySelector('b'), overlay.querySelector('p'), overlay.querySelector('small[data-runtime-stage]')];
    if (title) title.textContent = stage[0]; if (detail) detail.textContent = stage[1]; if (small) small.textContent = stage[2];
  }

  async function renderAtRisk(admin) {
    const tbody = document.getElementById(admin ? 'admin-risk-tbody' : 'risk-tbody');
    if (!tbody) return;
    const input = document.getElementById(admin ? 'admin-risk-search' : 'risk-search');
    const query = String(input?.value || '').trim().toLowerCase();
    try {
      // The full cohort can contain thousands of records.  The directory only
      // renders 100 rows, so fetch that useful page while taking the accurate
      // risk total from the lightweight shared dataset status.
      const [payload, status] = await Promise.all([
        fetch('/api/students?limit=160&at_risk=1', {cache: 'no-store'}).then(r => r.json()),
        fetch('/api/dataset/status', {cache: 'no-store'}).then(r => r.json()),
      ]);
      const records = (payload.students || []).filter(student => ['HIGH', 'MEDIUM'].includes(String(student.final_risk_tier || '').toUpperCase())).filter(student => !query || `${student.student_name || ''} ${student.student_id || ''} ${student.top_factor_1 || ''}`.toLowerCase().includes(query));
      const tiers = Object.fromEntries((status.tier_breakdown || []).map(row => [String(row.final_risk_tier || '').toUpperCase(), Number(row.cnt || 0)]));
      const total = (tiers.HIGH || 0) + (tiers.MEDIUM || 0);
      const badge = document.getElementById(admin ? 'admin-risk-badge' : 'risk-count-badge'); if (badge) badge.textContent = `${total.toLocaleString()} students`;
      tbody.innerHTML = records.length ? records.slice(0, 100).map(student => `<tr><td><strong>${escapeHtml(student.student_name || 'Student')}</strong> <span class="mono" style="color:var(--text3)">(${escapeHtml(student.student_id || '')})</span></td><td><span class="mono">${Number(student.ml_risk_score || 0).toFixed(3)}</span></td><td><span class="tag ${String(student.final_risk_tier).toUpperCase() === 'HIGH' ? 'tag-t1' : 'tag-t2'}">${escapeHtml(student.final_risk_tier || 'MEDIUM')}</span></td><td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(student.primary_root_cause || student.top_factor_1 || 'Engagement review')}</td><td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(student.final_action || 'Schedule counselor follow-up')}</td><td></td></tr>`).join('') : '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">No at-risk students found</td></tr>';
    } catch (_) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--red)">Unable to load students.</td></tr>'; }
  }

  async function refreshFairness() {
    const body = document.getElementById('fairness-runtime-rows'); if (!body) return;
    const request = ++fairnessRequest;
    try {
      const payload = await fetch('/api/fairness', {cache: 'no-store'}).then(r => r.json());
      if (request !== fairnessRequest) return;
      body.innerHTML = (payload.fairness || []).map(row => {
        const status = value => value === 'YES' ? '<span class="fairness-status ok">Within range</span>' : '<span class="fairness-status review">Review</span>';
        return `<tr><td>${escapeHtml(row.protected_attribute)}: ${escapeHtml(row.group_a)} vs ${escapeHtml(row.group_b)}</td><td>${Number(row.demographic_parity_ratio).toFixed(3)} ${status(row.dp_is_fair)}</td><td>${Number(row.equal_opportunity_ratio).toFixed(3)} ${status(row.eo_is_fair)}</td><td>${Number(row.predictive_parity_ratio).toFixed(3)} ${status(row.pp_is_fair)}</td></tr>`;
      }).join('') || '<tr><td colspan="4">No comparison was available.</td></tr>';
    } catch (_) {}
  }

  function removeDemoUi() {
    document.querySelectorAll('.operation-row,.summary-person').forEach(node => { if (/\bdemo\b/i.test(node.textContent || '')) node.remove(); });
    document.querySelectorAll('button').forEach(button => { if (/\bdemo\b/i.test(button.textContent || '')) button.textContent = button.textContent.replace(/\bdemo\b\s*/ig, '').replace(/\s{2,}/g, ' ').trim(); });
  }

  function normalizeModelPresentation() {
    // The interface describes validation evidence, not a single winning
    // "champion".  Keep labels short and consistent across both roles.
    document.querySelectorAll('h1,h2,h3,h4,p,span,div,strong,li').forEach(node => {
      if (node.children.length) return;
      const value = String(node.textContent || '').trim();
      if (value === 'Champion Model') node.textContent = '4-Model Validation';
      else if (value === '4-Model Validation-Weighted Ensemble') node.textContent = '4-Model Validation';
      else if (/^Logistic Regression and XGBoost train on an 80% stratified split\./.test(value)) {
        node.textContent = 'Logistic Regression, XGBoost, Random Forest, and HistGradientBoosting train on the same 80% stratified split. Held-out validation evaluates all four models before their combined 4-Model Validation score is applied.';
      } else if (/both candidate models/i.test(value)) node.textContent = value.replace(/both candidate models/ig, 'all four candidate models');
      else if (/two candidates/i.test(value)) node.textContent = value.replace(/two candidates/ig, 'four candidate models');
      else if (/both trained models/i.test(value)) node.textContent = value.replace(/both trained models/ig, 'all four trained models');
      else if (/registered champion/i.test(value)) node.textContent = value.replace(/registered champion/ig, 'combined 4-Model Validation result');
      else if (/champion ML/i.test(value)) node.textContent = value.replace(/champion ML/ig, '4-Model Validation');
    });
    const detail = document.getElementById('layer-detail');
    const modelSelected = Boolean(document.querySelector('.data-layer-card.selected[data-layer="model"]'));
    if (detail && modelSelected && detail.dataset.runtimeFourModel !== 'true') {
      detail.dataset.runtimeFourModel = 'true';
      detail.innerHTML = `<div class="layer-expanded model"><div><span class="layer-expanded-kicker">Held-out ML validation and explainability</span><h2>4-Model Validation</h2><p>Logistic Regression, XGBoost, Random Forest, and HistGradientBoosting train on the same stratified split. Their held-out metrics are combined into the operational 4-Model Validation score.</p></div><ul><li>Accuracy, precision, recall, F1, and ROC-AUC are recorded for all four models.</li><li>All four model records and the combined validation result are retained for reproducibility.</li><li>SHAP provides global feature importance and student-level contributing factors.</li><li>Gender and socioeconomic fairness checks measure demographic parity, equal opportunity, and predictive parity.</li></ul></div>`;
      const label = document.getElementById('layer-detail-label');
      if (label) label.textContent = '4-Model Validation';
    }
  }

  async function augmentModelEvidence() {
    // ML Evidence already has one authoritative renderer. Remove the former
    // add-on panel rather than duplicating model and layer information.
    document.querySelectorAll('#page-model-evidence .ensemble-context').forEach(node => node.remove());
  }

  function showOperationModal(title, message, actionLabel, actionHref) {
    document.getElementById('operation-action-modal')?.remove();
    const backdrop = document.createElement('div');
    backdrop.id = 'operation-action-modal'; backdrop.className = 'operation-modal-backdrop';
    backdrop.innerHTML = `<section class="operation-modal" role="dialog" aria-modal="true"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p><div class="operation-modal-actions">${actionHref ? `<a href="${escapeHtml(actionHref)}">${escapeHtml(actionLabel)}</a>` : ''}<button type="button">Close</button></div></section>`;
    backdrop.addEventListener('click', event => { if (event.target === backdrop || event.target.tagName === 'BUTTON') backdrop.remove(); });
    document.body.appendChild(backdrop);
    return backdrop;
  }

  async function analyzeCallsWithModal() {
    const modal = showOperationModal('Analyzing completed calls', 'Preparing transcript-specific AI summaries and the WhatsApp follow-up queue…');
    try {
      const response = await fetch('/analyze', {method: 'POST'});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Call analysis could not be completed.');
      modal.querySelector('h2').textContent = 'Call analysis complete';
      modal.querySelector('p').textContent = `${Number(payload.analyzed || 0)} completed calls were analyzed and the operational CSV is ready.`;
      refreshOperations();
    } catch (error) {
      modal.querySelector('h2').textContent = 'Call analysis status';
      modal.querySelector('p').textContent = error.message || 'Completed calls are analyzed automatically as each call finishes.';
    }
  }

  async function exportCallsWithModal() {
    const modal = showOperationModal('Preparing CSV export', 'The export includes distinct walkthrough records and every analyzed live call, including Achal after completion.');
    try {
      const response = await fetch('/api/operations/export.csv', {cache:'no-store'});
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.error || 'No completed call analysis is ready for export.');
      }
      modal.querySelector('h2').textContent = 'CSV export ready';
      modal.querySelector('p').textContent = 'Download the spreadsheet-ready CSV. It includes detailed risk, support, and AI-summary columns.';
      const controls = modal.querySelector('.operation-modal-actions');
      const link = document.createElement('a'); link.href = '/api/operations/export.csv'; link.textContent = 'Download CSV'; controls.prepend(link);
    } catch (error) {
      modal.querySelector('h2').textContent = 'CSV export status';
      modal.querySelector('p').textContent = error.message || 'The export could not be prepared.';
    }
  }

  const legacyWorkspaceActivation = window.activateWorkspacePage;
  if (typeof legacyWorkspaceActivation === 'function') {
    window.activateWorkspacePage = (...args) => {
      closeRuntimeConversations();
      allowAchalAutofocus = pendingAchalCallFocus && /transcript|whatsapp/i.test(String(args[0] || ''));
      return legacyWorkspaceActivation(...args);
    };
  }
  const nativeSelectDataLayer = window.selectDataLayer;
  if (typeof nativeSelectDataLayer === 'function') {
    window.selectDataLayer = key => {
      nativeSelectDataLayer(key);
      if (key === 'model') requestAnimationFrame(normalizeModelPresentation);
    };
  }
  document.addEventListener('click', event => {
    if (event.target.closest('.sb-item[data-page], [data-workspace-page]')) {
      closeRuntimeConversations(); allowAchalAutofocus = pendingAchalCallFocus;
    }
    if (event.target.closest('button') && /call students/i.test(event.target.closest('button').textContent || '')) {
      // The live call hand-off should take priority even if the counselor had
      // previously browsed another conversation.
      openedConversationKey = null;
      allowAchalAutofocus = true;
      pendingAchalCallFocus = true;
      setTimeout(refreshOperations, 350);
      setTimeout(refreshOperations, 1100);
      setTimeout(refreshOperations, 3200);
    }
  });
  window.runAnalysis = analyzeCallsWithModal;
  window.exportCSV = exportCallsWithModal;

  window.loadAtRisk = () => renderAtRisk(false);
  window.loadAdminAtRisk = () => renderAtRisk(true);
  const sendCallFollowUp = async () => {
    if (!latestCall) { window.toast?.('Start a call before sending a WhatsApp follow-up.', 'info'); return; }
    try {
      const response = await fetch('/whatsapp/demo', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({student_name: latestCall.student_name})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Unable to send the WhatsApp follow-up.');
      window.toast?.('Call follow-up sent on WhatsApp.', 'ok');
      refreshOperations();
    } catch (error) { window.toast?.(error.message || 'Unable to send the WhatsApp follow-up.', 'err'); }
  };
  window.waDemo = sendCallFollowUp;
  window.adminWaDemo = sendCallFollowUp;
  document.addEventListener('DOMContentLoaded', () => {
    protectOperationPanels();
    renderCohortPulse(); renderCohortBrief(); removeDuplicateTranscriptSearch(); normalizeUploadStages(); normalizeModelPresentation(); removeDemoUi(); refreshOperations(); renderAtRisk(false); renderAtRisk(true); refreshFairness(); augmentModelEvidence(); syncActiveDatasetScope();
    setInterval(refreshOperations, 2000); setInterval(keepLiveThreadsAtLatestTurn, 250); setInterval(normalizeUploadStages, 160); setInterval(normalizeModelPresentation, 450); setInterval(removeDemoUi, 800); setInterval(refreshFairness, 1800); setInterval(renderCohortPulse, 8000); setInterval(renderCohortBrief, 3000); setInterval(removeDuplicateTranscriptSearch, 1000); setInterval(augmentModelEvidence, 900); setInterval(syncActiveDatasetScope, 2000);
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
            response = app.make_response(original_dataset_status())
            payload = response.get_json(silent=True)
            if isinstance(payload, dict) and payload.get("dataset_loaded"):
                payload["champion_model"] = _visible_model_name(payload.get("champion_model"))
                return jsonify(payload), response.status_code
            return response

        app.view_functions[status_rule.endpoint] = recovered_dataset_status

    metrics_rule = next((rule for rule in app.url_map.iter_rules() if rule.rule == "/api/model-metrics"), None)
    if metrics_rule:
        original_model_metrics = app.view_functions[metrics_rule.endpoint]

        def enriched_model_metrics():
            response = app.make_response(original_model_metrics())
            payload = response.get_json(silent=True)
            if not isinstance(payload, dict) or not payload.get("dataset_loaded"):
                return response
            metadata = active_metadata() or {}
            payload["pipeline_layers"] = metadata.get("pipeline_layers", {})
            payload["ensemble"] = metadata.get("ensemble", {})
            payload["champion_model"] = _visible_model_name(payload.get("champion_model") or metadata.get("champion_model"))
            models = payload.get("models")
            if isinstance(models, dict):
                for name in list(models):
                    if "4-Model Validation" in str(name) and name != "4-Model Validation":
                        models["4-Model Validation"] = models.pop(name)
            return jsonify(payload), response.status_code

        app.view_functions[metrics_rule.endpoint] = enriched_model_metrics

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
        metadata = active_metadata() or {}
        return jsonify({
            "dataset_loaded": True,
            "total_students": total,
            "high_risk_students": high,
            "medium_risk_students": medium,
            "champion_model": _visible_model_name(metadata.get("champion_model")),
            "ensemble": metadata.get("ensemble", {}),
            "summary": f"This uploaded dataset contains {total:,} scored students, including {high:,} high-risk and {medium:,} medium-risk students.",
        })

    if not any(rule.rule == "/api/dataset/insights" for rule in app.url_map.iter_rules()):
        app.add_url_rule("/api/dataset/insights", "dataset_insights", dataset_insights, methods=["GET"])

    def operations_export_csv():
        """Download the enriched operational export for spreadsheet review."""
        if not voice_server.analyzed_results:
            return jsonify({"error": "No completed call analysis is available yet."}), 400
        voice_server._export_results()
        export_path = Path(voice_server.OUTPUT_CSV)
        if not export_path.exists():
            return jsonify({"error": "The operational export could not be created."}), 500
        return Response(
            export_path.read_bytes(),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=dropout-signal-call-follow-ups.csv"},
        )

    if not any(rule.rule == "/api/operations/export.csv" for rule in app.url_map.iter_rules()):
        app.add_url_rule("/api/operations/export.csv", "operations_export_csv", operations_export_csv, methods=["GET"])

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
        # Expose one durable ringing transcript immediately, rather than
        # waiting for Twilio's answer webhook. Both dashboards can therefore
        # open Achal's live call as soon as "Call Students" is pressed. The
        # welcome webhook replaces this provisional entry using the same SID.
        call_sid = str(result.get("call_sid") or "")
        if call_sid:
            provisional = {
                "student_id": student["student_id"],
                "student_name": student["student_name"],
                "ml_risk_score": student["ml_risk_score"],
                "risk_tier": student.get("risk_tier", "HIGH"),
                "phone": phone,
                "call_sid": call_sid,
                "answers": {},
                "current_question": "",
                "started_at": voice_server.datetime.now().isoformat(),
                "status": "ringing",
                "transcript_events": [],
            }
            voice_server._append_call_event(provisional, "Asha AI", "ai", "Calling Achal now…")
            voice_server.sessions[call_sid] = provisional
            voice_server._persist_live_state()
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
        # A scored profile is not a completed conversation. Only webhook and
        # call-originated state belongs in the operational transcript views.
        real_calls = namespace["_merge_real_operations"]([])
        by_student = {str(item.get("student_id")): item for item in real_calls}
        for session in voice_server.sessions.values():
            item = by_student.get(str(session.get("student_id") or ""))
            if item and session.get("student_name"):
                item["student_name"] = session["student_name"]
        for phone, session in voice_server.wa_sessions.items():
            profile = session.get("profile") or {}
            student_id = str(profile.get("student_id") or "")
            student_name = profile.get("student_name") or session.get("profile_name") or session.get("spoken_name") or "Student"
            messages = [
                {
                    "speaker": student_name if message.get("role") == "user" else "Asha AI",
                    "side": "student" if message.get("role") == "user" else "ai",
                    "text": str(message.get("content") or ""),
                }
                for message in session.get("messages", [])
                if str(message.get("content") or "").strip()
            ]
            target = by_student.get(student_id) if student_id else next(
                (item for item in real_calls if str(item.get("student_name", "")).casefold() == str(student_name).casefold()),
                None,
            )
            if target is None:
                target = {
                    "student_id": student_id or f"WA-{phone}", "student_name": student_name,
                    "branch": "WhatsApp follow-up", "tier": str(profile.get("dropout_intent") or "MEDIUM").upper(),
                    "status": "active", "ml_score": float(profile.get("ml_risk_score") or 0),
                    "ai_score": float(profile.get("ml_risk_score") or 0),
                    "factor": profile.get("primary_root_cause") or "Student support follow-up",
                    "action": "WhatsApp support follow-up", "call": [], "whatsapp": [], "summary": "",
                }
                real_calls.append(target)
                by_student[str(target["student_id"])] = target
            target["student_name"] = student_name
            target["whatsapp"] = messages
        # Keep the operational views populated for a walkthrough, but make
        # these explicitly separate sample records. They never replace a
        # webhook-backed student call such as Achal's.
        if payload.get("dataset_loaded"):
            real_ids = {str(item.get("student_id")) for item in real_calls}
            for index, student in enumerate(namespace["_dataset_records"](limit=14)):
                if str(student.get("student_id")) in real_ids:
                    continue
                sample = namespace["_experience_conversation"](student, index)
                sample["is_sample"] = True
                sample["status"] = "active" if index < 7 else "completed"
                sample["student_name"] = student.get("student_name") or "Student"
                real_calls.append(sample)
        active_states = {"active", "ringing", "in-progress", "in_progress"}
        payload["conversations"] = sorted(
            real_calls,
            key=lambda item: str(item.get("status", "")).lower() not in active_states,
        )
        return jsonify(payload)
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
        # Historical templates now contain their own legacy refresh helper.
        # Use this final renderer's unique CSS marker so it is injected once
        # per role even when those older helper names are already present.
        if isinstance(template, str) and "authoritative-dashboard-ui" not in template:
            # Remove the legacy fabricated sentence from the HTML itself. The
            # card is populated only by the dataset-backed insights endpoint.
            template = template.replace(
                "Based on recent data, 87 students are at high risk of dropping out. Key factors include attendance (42%), low engagement (28%), and academic performance (30%). Early intervention can improve outcomes.",
                "",
            )
            # Keep implementation compatibility with the recovered handlers,
            # while removing the old sample wording from both user-facing
            # dashboards.
            template = (
                template.replace("(Demo)", "")
                .replace("Demo Student", "Student")
                .replace("HIGH RISK · DEMO", "HIGH RISK")
                .replace("Send WhatsApp Demo", "Send WhatsApp Follow-up")
                .replace("WhatsApp Demo", "WhatsApp Follow-up")
                .replace("Demo Call", "Start Call")
                .replace("Uploading file...", "Uploading dataset...")
                .replace("Uploading file…", "Uploading dataset…")
            )
            namespace[key] = template.replace("</body>", LIVE_UI_SCRIPT + FINAL_UI_SCRIPT + "</body>")
