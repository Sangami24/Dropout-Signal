import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import voice_server


class VoiceTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_file = voice_server._LIVE_STATE_FILE
        self.original_sessions = copy.deepcopy(voice_server.sessions)
        self.original_completed = copy.deepcopy(voice_server.completed_calls)
        self.original_results = copy.deepcopy(voice_server.analyzed_results)
        self.original_whatsapp = copy.deepcopy(voice_server.wa_sessions)
        voice_server._LIVE_STATE_FILE = Path(self.temp_dir.name) / "live.json"
        voice_server.sessions.clear()
        voice_server.completed_calls.clear()
        voice_server.analyzed_results.clear()
        voice_server.wa_sessions.clear()

    def tearDown(self):
        voice_server._LIVE_STATE_FILE = self.original_file
        voice_server.sessions.clear()
        voice_server.sessions.update(self.original_sessions)
        voice_server.completed_calls[:] = self.original_completed
        voice_server.analyzed_results[:] = self.original_results
        voice_server.wa_sessions.clear()
        voice_server.wa_sessions.update(self.original_whatsapp)
        self.temp_dir.cleanup()

    def _session(self, sid="CA-test"):
        session = {
            "student_id": "STU-ACHAL",
            "student_name": "Achal Sangami",
            "spoken_name": "Achal",
            "ml_risk_score": 0.87,
            "phone": "+910000000000",
            "call_sid": sid,
            "answers": {},
            "current_question": voice_server.QUESTIONS[0],
            "started_at": "2026-09-09T10:00:00",
            "status": "active",
            "transcript_events": [
                {"speaker": "Asha AI", "side": "ai", "text": voice_server.QUESTIONS[0]}
            ],
        }
        voice_server.sessions[sid] = session
        voice_server._persist_live_state()
        return session

    def test_gather_publishes_only_final_speech_and_uses_supported_auto_model(self):
        xml = str(voice_server._speech_gather(0, "CA-test"))
        self.assertNotIn("partialResultCallback=", xml)
        self.assertNotIn("/voice/partial", xml)
        self.assertIn('language="en-IN"', xml)
        self.assertIn('speechTimeout="auto"', xml)
        self.assertNotIn("speechModel=", xml)

    def test_partial_speech_is_not_published_and_final_answer_is_stored_once(self):
        session = self._session()
        client = voice_server.app.test_client()
        response = client.post(
            "/voice/partial?q=0&sid=CA-test",
            data={"CallSid": "CA-test", "UnstableSpeechResult": "I am finding this semester hard"},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(session["transcript_events"]), 1)

        response = client.post(
            "/voice/respond?q=0&sid=CA-test",
            data={
                "CallSid": "CA-test",
                "SpeechResult": "I am finding this semester hard",
                "Confidence": "0.92",
            },
        )
        self.assertEqual(response.status_code, 200)
        events = voice_server.sessions["CA-test"]["transcript_events"]
        self.assertFalse(any(event.get("partial") for event in events))
        self.assertEqual(
            [event["text"] for event in events].count("I am finding this semester hard"),
            1,
        )
        self.assertEqual(voice_server.sessions["CA-test"]["current_question"], voice_server.QUESTIONS[1])
        self.assertGreater(
            events[-1].get("available_at", 0), voice_server.time.time() + 0.7
        )

        duplicate = client.post(
            "/voice/respond?q=0&sid=CA-test",
            data={"CallSid": "CA-test", "SpeechResult": "a stale repeated answer", "Confidence": "0.99"},
        )
        self.assertEqual(duplicate.status_code, 200)
        events = voice_server.sessions["CA-test"]["transcript_events"]
        self.assertFalse(any(event.get("text") == "a stale repeated answer" for event in events))
        self.assertEqual(voice_server.sessions["CA-test"]["answers"][voice_server.Q_KEYS[0]]["text"], "I am finding this semester hard")

    def test_restore_treats_disk_as_authoritative(self):
        self._session("CA-stale")
        voice_server._LIVE_STATE_FILE.write_text(
            json.dumps({"sessions": {}, "completed_call_sids": [], "wa_sessions": {}, "analyzed_results": []}),
            encoding="utf-8",
        )
        voice_server._restore_live_state()
        self.assertEqual(voice_server.sessions, {})

    def test_whatsapp_fallback_reply_is_persisted(self):
        phone = "+910000000001"
        voice_server.wa_sessions[phone] = {
            "messages": [{"role": "assistant", "content": "Hello"}],
            "profile": {"student_name": "Achal Sangami"},
            "status": "active",
        }
        with patch.object(voice_server, "LLM_AVAILABLE", False):
            reply = voice_server._wa_llm_reply(phone, "I need help")
        self.assertIn("saved your message", reply)
        self.assertEqual(len(voice_server.wa_sessions[phone]["messages"]), 2)
        persisted = json.loads(voice_server._LIVE_STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(persisted["wa_sessions"][phone]["messages"]), 2)

    def test_whatsapp_outreach_without_twilio_is_saved_locally(self):
        phone = "+910000000009"
        result = {
            "student_id": "STU-LOCAL",
            "student_name": "Local Student",
            "spoken_name": "Local",
            "phone": phone,
            "dropout_intent": "HIGH",
            "primary_root_cause": "academic",
            "summary": "The student requested academic support.",
        }
        with (
            patch.object(voice_server, "twilio_ready", False),
            patch.object(voice_server, "twilio_client", None),
        ):
            sent = voice_server._auto_whatsapp_outreach([result])
        self.assertEqual(sent, 0)
        self.assertEqual(voice_server.wa_sessions[phone]["profile"]["student_id"], "STU-LOCAL")
        message = voice_server.wa_sessions[phone]["messages"][0]["content"].lower()
        self.assertIn("academic", message)
        self.assertIn("support", message)

    def test_demo_handset_preserves_selected_student_identity(self):
        phone = "+910000000002"
        voice_server.wa_sessions[phone] = {
            "messages": [{"role": "assistant", "content": "Hello"}],
            "profile": {"student_id": "old", "student_name": "Old Profile"},
            "profile_name": "Old Profile",
            "status": "active",
        }
        with patch.object(voice_server, "DEMO_PHONE", phone):
            voice_server._normalize_demo_whatsapp_identity(f"whatsapp:{phone}")
        self.assertEqual(voice_server.wa_sessions[phone]["profile"]["student_id"], "old")
        self.assertEqual(voice_server.wa_sessions[phone]["profile"]["student_name"], "Old Profile")
        self.assertEqual(voice_server.wa_sessions[phone]["profile_name"], "Old Profile")

    def test_spoken_language_retry_then_kannada_four_question_flow(self):
        session = self._session("CA-language")
        session.update({"current_question": "language_preference", "questions": [], "academic_profile": {"attendance_rate": "62%", "lowest_subject": "Mathematics", "lowest_subject_marks": "44"}})
        client = voice_server.app.test_client()
        retry = client.post("/voice/language?sid=CA-language&nospeech=1", data={"CallSid": "CA-language"})
        self.assertEqual(retry.status_code, 200)
        self.assertIn("did not hear that properly", retry.get_data(as_text=True))
        selected = client.post("/voice/language?sid=CA-language", data={"CallSid": "CA-language", "SpeechResult": "ಕನ್ನಡ", "Confidence": "0.95"})
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(session["language_code"], "kn-IN")
        self.assertEqual(len(session["questions"]), 4)
        self.assertIn('language="kn-IN"', selected.get_data(as_text=True))

    def test_strong_academic_profile_still_gets_four_questions(self):
        questions = voice_server._build_adaptive_questions(
            {"attendance_rate": "96%", "lowest_subject": "Mathematics", "lowest_subject_marks": "91"},
            "en-IN",
        )
        self.assertEqual(len(questions), 4)
        self.assertEqual(len(set(questions)), 4)

    def test_unheard_question_repeats_without_advancing(self):
        session = self._session("CA-unheard")
        session.update({
            "language_code": "en-IN",
            "tts_voice": voice_server.LANGUAGES["en-IN"]["voice"],
            "questions": voice_server._build_adaptive_questions({}, "en-IN"),
        })
        session["current_question"] = session["questions"][0]
        response = voice_server.app.test_client().post(
            "/voice/respond?q=0&sid=CA-unheard&nospeech=1",
            data={"CallSid": "CA-unheard"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session["answers"], {})
        self.assertEqual(session["current_question"], session["questions"][0])
        self.assertIn("Could you please repeat your answer", response.get_data(as_text=True))

    def test_live_fused_score_can_reach_all_three_tiers(self):
        def score(text):
            session = self._session(f"CA-{text[:3]}")
            session["answers"] = {key: {"text": text, "twilio_confidence": .92} for key in voice_server.Q_KEYS}
            return voice_server._live_voice_assessment(session)[3]
        self.assertEqual(score("Everything is great and manageable. I am excited, doing well, and will continue."), "LOW")
        self.assertEqual(score("Things are okay and I am still deciding what support would help."), "MEDIUM")
        self.assertEqual(score("I am struggling, failing, missing classes, and I may leave college and quit."), "HIGH")

    def test_whatsapp_completion_builds_one_combined_summary(self):
        phone = "+910000000003"
        result = {
            "student_id": "STU-ACHAL", "student_name": "Achal Sangami",
            "call_status": "completed", "summary": "Call found academic workload pressure.",
            "primary_root_cause": "academic", "dropout_intent": "HIGH",
        }
        voice_server.analyzed_results.append(result)
        self._session("CA-summary")["summary"] = result["summary"]
        voice_server.wa_sessions[phone] = {
            "messages": [
                {"role": "assistant", "content": "Following up on academic workload."},
                {"role": "user", "content": "A tutor and a weekly plan would help."},
                {"role": "user", "content": "bye"},
            ],
            "profile": {"student_id": "STU-ACHAL", "student_name": "Achal Sangami", "primary_root_cause": "academic", "call_summary": result["summary"]},
            "status": "active",
        }
        voice_server._complete_whatsapp_conversation(phone, "bye")
        summary = voice_server.wa_sessions[phone]["summary"]
        self.assertIn("Call found academic workload pressure", summary)
        self.assertIn("A tutor and a weekly plan would help", summary)
        self.assertEqual(voice_server.sessions["CA-summary"]["summary"], summary)


class UnifiedDashboardTests(VoiceTranscriptTests):
    @classmethod
    def setUpClass(cls):
        import app

        cls.unified = app

    def test_reset_clears_and_persists_live_operations(self):
        self._session("CA-reset")
        voice_server.wa_sessions["+910000000000"] = {"messages": [{"role": "assistant", "content": "Hi"}]}
        response = self.unified.app.test_client().post(
            "/api/reset", headers={"X-Operations-Reset": "explicit"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(voice_server.sessions, {})
        persisted = json.loads(voice_server._LIVE_STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(persisted["sessions"], {})
        self.assertEqual(persisted["wa_sessions"], {})

    def test_answer_webhook_wins_manual_call_race(self):
        sid = "CA-race"

        def answered_before_rest_response(*_args, **_kwargs):
            voice_server.sessions[sid] = {
                "student_id": "STU-ACHAL",
                "student_name": "Achal Sangami",
                "call_sid": sid,
                "answers": {},
                "current_question": voice_server.QUESTIONS[0],
                "started_at": "2026-09-09T10:00:00",
                "status": "active",
                "transcript_events": [
                    {"speaker": "Asha AI", "side": "ai", "text": voice_server.QUESTIONS[0]}
                ],
            }
            return {"call_sid": sid, "status": "initiated"}

        student = {
            "student_id": "STU-ACHAL",
            "student_name": "Achal Sangami",
            "ml_risk_score": 0.87,
            "risk_tier": "HIGH",
        }
        with (
            patch("app_overrides._dataset_ready", return_value=True),
            patch("app_overrides._manual_call_payload", return_value=student),
            patch.object(voice_server, "DEMO_PHONE", "+910000000000"),
            patch.object(voice_server, "_start_call", side_effect=answered_before_rest_response),
        ):
            response = self.unified.app.test_client().post("/api/manual-call")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(voice_server.sessions[sid]["status"], "active")
        self.assertEqual(voice_server.sessions[sid]["current_question"], voice_server.QUESTIONS[0])
        self.assertEqual(len(voice_server.sessions[sid]["transcript_events"]), 1)

    def test_dashboards_include_single_authoritative_renderer_and_overflow_fix(self):
        for template in (self.unified.ADMIN_DASHBOARD, self.unified.COUNSELOR_DASHBOARD):
            self.assertEqual(template.count('id="authoritative-dashboard-ui"'), 1)
            self.assertIn("overflow-x:hidden !important", template)
            self.assertIn("function effectiveChannelStatus", template)
            self.assertIn("window.startGuidedDemo = async", template)
            self.assertIn("function swapRiskCards", template)
            self.assertIn("/ 2000", template)
            self.assertIn("elapsedTurns", template)
            self.assertIn("runtimeToggleBound", template)
            self.assertIn("4 Models Ensembled", template)
            self.assertIn("professional-risk-workspace", template)
            self.assertIn("Reading earlier messages deliberately pauses", template)
            self.assertIn("student-summary-profile", template)
            self.assertIn("starting a student check-in", template)
            self.assertIn("Uploaded Dataset Training Evidence", template)
        self.assertIn("guided-demo-login-cursor", self.unified.LOGIN_HTML)
        self.assertIn("Math.min(window.innerWidth-50", self.unified.LOGIN_HTML)
        self.assertIn("dropout-signal-guided-cursor", self.unified.LOGIN_HTML)

    def test_export_requires_achal_then_matches_high_risk_row_count(self):
        import pandas as pd
        import app_overrides

        client = self.unified.app.test_client()
        empty = client.get("/api/operations/export.csv")
        self.assertEqual(empty.status_code, 400)
        self.assertIn("No completed analyzed call", empty.get_json()["error"])

        voice_server.analyzed_results.append({
            "student_id": "STU-ACHAL", "student_name": "Achal Sangami",
            "call_status": "completed", "summary": "Call identified coursework pressure.",
            "call_only_summary": "Call identified coursework pressure.",
            "dropout_intent": "HIGH", "ml_risk_score": .91,
        })
        voice_server.wa_sessions["+910000000004"] = {
            "messages": [{"role": "user", "content": "I accepted the tutor appointment."}],
            "profile": {"student_id": "STU-ACHAL", "student_name": "Achal Sangami", "primary_root_cause": "academic", "call_summary": "Call identified coursework pressure."},
        }
        cohort = pd.DataFrame([
            {"student_id": "H-1", "student_name": "One", "final_risk_tier": "HIGH", "ml_risk_score": .99, "top_factor_1": "Attendance", "final_action": "Attendance plan"},
            {"student_id": "H-2", "student_name": "Two", "final_risk_tier": "HIGH", "ml_risk_score": .92, "top_factor_1": "Coursework", "final_action": "Tutor"},
            {"student_id": "H-3", "student_name": "Three", "final_risk_tier": "HIGH", "ml_risk_score": .88, "top_factor_1": "Fees", "final_action": "Financial aid"},
            {"student_id": "L-1", "student_name": "Low", "final_risk_tier": "LOW", "ml_risk_score": .10},
        ])
        with patch.object(app_overrides, "active_records", return_value=cohort):
            response = client.get("/api/operations/export.csv")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["student_name"], "Achal Sangami")
        self.assertIn("WhatsApp", rows[0]["summary"])
        self.assertEqual(rows[0]["ai_summary"], rows[0]["summary"])
        self.assertEqual(len({row["summary"] for row in rows}), 3)
        self.assertTrue(all(row["ai_summary"] for row in rows))
        self.assertTrue(all(row["dropout_intent"] == "HIGH" for row in rows))


if __name__ == "__main__":
    unittest.main()
