"""Runtime safeguards for the recovered unified dashboard.

These hooks keep calls tied to a real uploaded cohort and expose the Twilio
webhook state to the existing counselor and administrator screens.
"""

from __future__ import annotations

import time

from flask import jsonify

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

  document.addEventListener('DOMContentLoaded', () => {
    refreshCallGate();
    refreshLiveTranscripts();
    refreshLiveWhatsApp();
    installTranscriptSearch();
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
            dummy_calls = []
            for index, student in enumerate(namespace["_dataset_records"](limit=7)):
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
                dummy_calls.append(dummy)
                if len(dummy_calls) == 7:
                    break
            payload["conversations"] = real_calls + dummy_calls
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
