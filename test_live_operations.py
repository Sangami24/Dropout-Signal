import copy
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

    def test_gather_uses_live_partial_results_and_supported_auto_model(self):
        xml = str(voice_server._speech_gather(0, "CA-test"))
        self.assertIn("partialResultCallback=", xml)
        self.assertIn("/voice/partial", xml)
        self.assertIn('language="en-IN"', xml)
        self.assertIn('speechTimeout="auto"', xml)
        self.assertNotIn("speechModel=", xml)

    def test_partial_speech_is_replaced_by_final_answer(self):
        session = self._session()
        client = voice_server.app.test_client()
        response = client.post(
            "/voice/partial?q=0&sid=CA-test",
            data={"CallSid": "CA-test", "UnstableSpeechResult": "I am finding this semester hard"},
        )
        self.assertEqual(response.status_code, 204)
        self.assertTrue(session["transcript_events"][-1]["partial"])

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


class UnifiedDashboardTests(VoiceTranscriptTests):
    @classmethod
    def setUpClass(cls):
        import app

        cls.unified = app

    def test_reset_clears_and_persists_live_operations(self):
        self._session("CA-reset")
        voice_server.wa_sessions["+910000000000"] = {"messages": [{"role": "assistant", "content": "Hi"}]}
        response = self.unified.app.test_client().post("/api/reset")
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


if __name__ == "__main__":
    unittest.main()
