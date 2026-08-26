"""Runtime safeguards for the recovered unified dashboard.

These hooks keep calls tied to a real uploaded cohort and expose the Twilio
webhook state to the existing counselor and administrator screens.
"""

from __future__ import annotations

import time
import threading
import uuid
from io import BytesIO

from flask import jsonify, request

from ml_pipeline import active_metadata, active_records
import voice_server


LIVE_UI_SCRIPT = r'''
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

  const BACKGROUND_UPLOAD_KEY = 'dropout-signal-background-upload';
  let backgroundUploadPoller = null;

  function showBackgroundUpload(job) {
    document.getElementById('dataset-training-overlay')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'dataset-training-overlay';
    overlay.innerHTML = `<section class="dataset-training-card" role="status" aria-live="polite"><div class="dataset-progress-ring"><span>…</span></div><div><b>Dataset processing in background</b><p>${escapeHtml(job.filename || 'Your dataset')} is safely processing on the server. You can switch dashboards or browser tabs.</p><small>Waiting for server progress…</small></div><button type="button" class="btn dataset-cancel-upload">Hide</button></section>`;
    overlay.querySelector('.dataset-cancel-upload').addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
    return overlay;
  }

  function updateBackgroundUpload(job) {
    const overlay = document.getElementById('dataset-training-overlay') || showBackgroundUpload(job);
    const stage = overlay.querySelector('small');
    const title = overlay.querySelector('b');
    const detail = overlay.querySelector('p');
    if (stage) stage.textContent = job.message || 'Processing on the server…';
    if (title && job.state === 'queued') title.textContent = 'Dataset upload queued in background';
    if (title && job.state === 'complete') title.textContent = 'Dataset processing complete';
    if (detail && job.state === 'complete') detail.textContent = 'The scored cohort is ready. Refreshing this dashboard…';
  }

  async function resumeBackgroundUpload() {
    const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
    if (!raw) return;
    let job;
    try { job = JSON.parse(raw); } catch (_) { localStorage.removeItem(BACKGROUND_UPLOAD_KEY); return; }
    updateBackgroundUpload(job);
    if (backgroundUploadPoller) clearInterval(backgroundUploadPoller);
    const poll = async () => {
      try {
        const response = await fetch(`/api/dataset/upload-status?job_id=${encodeURIComponent(job.id)}`, {cache: 'no-store'});
        if (!response.ok) return;
        const next = await response.json();
        const state = {...job, ...next};
        localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(state));
        updateBackgroundUpload(state);
        if (state.state === 'complete') {
          clearInterval(backgroundUploadPoller); backgroundUploadPoller = null;
          localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
          setTimeout(() => window.location.reload(), 700);
        } else if (state.state === 'failed') {
          clearInterval(backgroundUploadPoller); backgroundUploadPoller = null;
          localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
          document.getElementById('dataset-training-overlay')?.remove();
          toast(state.error || 'Dataset upload failed.', 'err');
        }
      } catch (_) {}
    };
    await poll();
    if (!backgroundUploadPoller) backgroundUploadPoller = setInterval(poll, 1200);
  }

  async function beginBackgroundUpload(file) {
    if (!file) return;
    const form = new FormData(); form.append('file', file);
    const job = { id: globalThis.crypto?.randomUUID?.() || `upload-${Date.now()}`, filename: file.name, state: 'uploading' };
    localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(job));
    showBackgroundUpload(job);
    try {
      const response = await fetch('/api/dataset/upload', { method: 'POST', body: form, headers: { 'X-Dataset-Upload-Id': job.id } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Dataset upload failed');
      localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify({...job, ...payload, state: payload.state || 'queued'}));
      resumeBackgroundUpload();
    } catch (error) {
      localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
      document.getElementById('dataset-training-overlay')?.remove();
      toast(error.message || 'Dataset upload failed.', 'err');
    }
  }

  // Capture the file selection before the legacy page-local handler runs.
  // The actual analysis is now a server job, so navigation or a backgrounded
  // browser tab cannot abort it after the bytes are received.
  document.addEventListener('change', event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.id !== 'dataset-file-input') return;
    event.stopImmediatePropagation();
    beginBackgroundUpload(input.files?.[0]);
    input.value = '';
  }, true);

  // Server-authoritative upload UI. These declarations intentionally replace
  // the earlier compatibility versions in this same scope.
  function showBackgroundUpload(job) {
    document.getElementById('dataset-training-overlay')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'dataset-training-overlay';
    const progress = Number(job.progress || 0);
    overlay.innerHTML = `<section class="dataset-training-card" role="status" aria-live="polite"><div class="dataset-progress-ring"><span>${progress.toFixed(1)}%</span></div><div><b>Uploading Dataset</b><p>${escapeHtml(job.filename || 'Your dataset')} is processing on the server. You can switch dashboards or browser tabs.</p><small>Uploading file...</small></div><button type="button" class="btn dataset-cancel-upload">Cancel Upload</button></section>`;
    overlay.querySelector('.dataset-cancel-upload').addEventListener('click', () => window.cancelDatasetUpload());
    document.body.appendChild(overlay);
    return overlay;
  }

  function updateBackgroundUpload(job) {
    const overlay = document.getElementById('dataset-training-overlay') || showBackgroundUpload(job);
    const ring = overlay.querySelector('.dataset-progress-ring');
    const percentage = ring?.querySelector('span');
    const stage = overlay.querySelector('small');
    const title = overlay.querySelector('b');
    const detail = overlay.querySelector('p');
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    if (ring) ring.style.setProperty('--dataset-progress', `${progress * 3.6}deg`);
    if (percentage) percentage.textContent = `${progress.toFixed(1)}%`;
    if (stage) stage.textContent = job.message || 'Processing on the server...';
    if (title && job.state === 'uploading') title.textContent = 'Uploading Dataset';
    if (title && ['queued', 'processing'].includes(job.state)) title.textContent = 'Finalizing Dataset';
    if (title && job.state === 'complete') title.textContent = 'Dataset processing complete';
    if (detail && ['queued', 'processing'].includes(job.state)) detail.textContent = 'Training, scoring, and saving the active cohort. Safe to switch dashboards or browser tabs.';
    if (detail && job.state === 'complete') detail.textContent = 'The scored cohort is active. Refreshing this dashboard...';
  }

  window.cancelDatasetUpload = async () => {
    const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
    if (!raw) { document.getElementById('dataset-training-overlay')?.remove(); return; }
    let job;
    try { job = JSON.parse(raw); } catch (_) { localStorage.removeItem(BACKGROUND_UPLOAD_KEY); return; }
    const button = document.querySelector('#dataset-training-overlay .dataset-cancel-upload');
    if (button) { button.disabled = true; button.textContent = 'Canceling...'; }
    try {
      await fetch('/api/dataset/cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({upload_id: job.id}), keepalive: true,
      });
    } finally {
      if (backgroundUploadPoller) clearInterval(backgroundUploadPoller);
      backgroundUploadPoller = null;
      localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
      document.getElementById('dataset-training-overlay')?.remove();
      toast('Dataset upload canceled.', 'info');
    }
  };

  async function resumeBackgroundUpload() {
    const raw = localStorage.getItem(BACKGROUND_UPLOAD_KEY);
    if (!raw) return;
    let job;
    try { job = JSON.parse(raw); } catch (_) { localStorage.removeItem(BACKGROUND_UPLOAD_KEY); return; }
    updateBackgroundUpload(job);
    if (backgroundUploadPoller) clearInterval(backgroundUploadPoller);
    const poll = async () => {
      try {
        const response = await fetch(`/api/dataset/upload-status?job_id=${encodeURIComponent(job.id)}`, {cache: 'no-store'});
        if (!response.ok) {
          if (response.status === 404) {
            clearInterval(backgroundUploadPoller); backgroundUploadPoller = null;
            localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
            document.getElementById('dataset-training-overlay')?.remove();
            toast('The upload job is no longer available. Please upload the CSV again.', 'err');
          }
          return;
        }
        job = {...job, ...await response.json()};
        localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(job));
        updateBackgroundUpload(job);
        if (job.state === 'complete') {
          clearInterval(backgroundUploadPoller); backgroundUploadPoller = null;
          localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
          setTimeout(() => window.location.reload(), 700);
        } else if (['failed', 'canceled'].includes(job.state)) {
          clearInterval(backgroundUploadPoller); backgroundUploadPoller = null;
          localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
          document.getElementById('dataset-training-overlay')?.remove();
          toast(job.state === 'canceled' ? 'Dataset upload canceled.' : (job.error || 'Dataset upload failed.'), job.state === 'canceled' ? 'info' : 'err');
        }
      } catch (_) {}
    };
    await poll();
    if (!backgroundUploadPoller && !['complete', 'failed', 'canceled'].includes(job.state)) backgroundUploadPoller = setInterval(poll, 800);
  }

  async function beginBackgroundUpload(file) {
    if (!file) return;
    const form = new FormData(); form.append('file', file);
    const job = {id: globalThis.crypto?.randomUUID?.() || `upload-${Date.now()}`, filename: file.name, state: 'uploading', progress: 0};
    localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify(job));
    updateBackgroundUpload(job);
    try {
      const response = await fetch('/api/dataset/upload', {method: 'POST', body: form, headers: {'X-Dataset-Upload-Id': job.id}});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Dataset upload failed');
      localStorage.setItem(BACKGROUND_UPLOAD_KEY, JSON.stringify({...job, ...payload}));
      await resumeBackgroundUpload();
    } catch (error) {
      localStorage.removeItem(BACKGROUND_UPLOAD_KEY);
      document.getElementById('dataset-training-overlay')?.remove();
      toast(error.message || 'Dataset upload failed.', 'err');
    }
  }

  document.addEventListener('visibilitychange', () => { if (!document.hidden) resumeBackgroundUpload(); });
  window.addEventListener('focus', resumeBackgroundUpload);
  window.addEventListener('storage', event => {
    if (event.key === BACKGROUND_UPLOAD_KEY && event.newValue) resumeBackgroundUpload();
  });

  document.addEventListener('DOMContentLoaded', () => {
    refreshCallGate();
    refreshLiveTranscripts();
    refreshLiveWhatsApp();
    installTranscriptSearch();
    resumeBackgroundUpload();
    // The legacy dashboard still repaints its call cards. Re-apply the latest
    // webhook transcript in the same turn so it cannot alternate between the
    // greeting variant and the question variant.
    new MutationObserver(() => queueMicrotask(() => { renderLiveTranscripts(); renderLiveWhatsApp(); installTranscriptSearch(); }))
      .observe(document.body, {childList: true, subtree: true});
    setInterval(refreshCallGate, 3000);
    setInterval(refreshLiveTranscripts, 650);
    setInterval(refreshLiveWhatsApp, 900);
    setInterval(installTranscriptSearch, 1500);
  });
})();
</script>
'''


_BACKGROUND_UPLOADS = {}
_BACKGROUND_UPLOAD_LOCK = threading.RLock()


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
            with _BACKGROUND_UPLOAD_LOCK:
                _BACKGROUND_UPLOADS[job_id] = {
                    "id": job_id,
                    "filename": filename,
                    "state": "queued",
                    "message": "Dataset received. Starting background analysis…",
                    "created_at": time.time(),
                }

            def run_upload_job():
                with _BACKGROUND_UPLOAD_LOCK:
                    _BACKGROUND_UPLOADS[job_id].update({
                        "state": "processing",
                        "processing_at": time.time(),
                        "progress": 5.0,
                        "message": "Training and scoring in the background…",
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
                    with _BACKGROUND_UPLOAD_LOCK:
                        if _BACKGROUND_UPLOADS[job_id].get("state") == "canceled":
                            return
                        _BACKGROUND_UPLOADS[job_id].update({
                            "state": "complete",
                            "message": "Dataset trained, scored, and activated.",
                            "status": status,
                            "progress": 100.0,
                            "completed_at": time.time(),
                        })
                except Exception as exc:
                    app.logger.exception("Background dataset upload failed")
                    with _BACKGROUND_UPLOAD_LOCK:
                        if _BACKGROUND_UPLOADS[job_id].get("state") == "canceled":
                            return
                        _BACKGROUND_UPLOADS[job_id].update({
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
            with _BACKGROUND_UPLOAD_LOCK:
                job = _background_upload_snapshot(_BACKGROUND_UPLOADS[job_id]) if job_id in _BACKGROUND_UPLOADS else {}
            if not job:
                return jsonify({"error": "Upload job not found."}), 404
            return jsonify(job)

        def background_dataset_cancel():
            payload = request.get_json(silent=True) or {}
            job_id = str(payload.get("upload_id") or "").strip()
            response = app.make_response(original_cancel()) if original_cancel else jsonify({"ok": True, "canceled": True})
            with _BACKGROUND_UPLOAD_LOCK:
                job = _BACKGROUND_UPLOADS.get(job_id)
                if job and job.get("state") != "complete":
                    snapshot = _background_upload_snapshot(job)
                    job.update({
                        "state": "canceled",
                        "message": "Dataset upload canceled.",
                        "progress": snapshot.get("progress", 0.0),
                        "completed_at": time.time(),
                    })
            return response

        app.view_functions[upload_rule.endpoint] = background_dataset_upload
        if not any(rule.rule == "/api/dataset/upload-status" for rule in app.url_map.iter_rules()):
            app.add_url_rule(
                "/api/dataset/upload-status",
                "background_dataset_upload_status",
                background_dataset_upload_status,
                methods=["GET"],
            )
        if cancel_rule and original_cancel:
            app.view_functions[cancel_rule.endpoint] = background_dataset_cancel

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
            for index, student in enumerate(namespace["_dataset_records"](limit=14)):
                if str(student.get("student_id")) in real_ids:
                    continue
                dummy = namespace["_experience_conversation"](student, index)
                dummy["student_id"] = f"DEMO-{student.get('student_id', index)}"
                dummy["student_name"] = f"{student.get('student_name', 'Student')} (Demo)"
                # Every dashboard reads the same time-sliced stream from this
                # endpoint. It is visually live, but it is kept separate from
                # the real Achal webhook transcript.
                elapsed_steps = int(time.time() // 2) + index
                call_turns = list(dummy.get("call", []))
                wa_turns = list(dummy.get("whatsapp", []))
                dummy["call"] = call_turns[:min(len(call_turns), 2 + elapsed_steps % max(1, len(call_turns)))]
                dummy["whatsapp"] = wa_turns[:min(len(wa_turns), 2 + elapsed_steps % max(1, len(wa_turns)))]
                dummy["status"] = "active"
                dummy["summary"] = "Saved demonstration transcript — not an active phone call."
                dummy["summary"] = "Live synchronized demonstration stream."
                if len(active_dummies) < 7:
                    active_dummies.append(dummy)
                else:
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
            namespace[key] = template.replace("</body>", LIVE_UI_SCRIPT + "</body>")
