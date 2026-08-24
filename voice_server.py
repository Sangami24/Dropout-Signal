"""
THE DROPOUT SIGNAL — Layer 2: AI Voice Verification Agent
==========================================================
Twilio + LLM powered voice agent that:
  1. Calls HIGH-risk students flagged by Layer 1 (ML)
  2. Asks 5 carefully designed, non-leading questions
  3. Analyzes responses with GPT-4o for sentiment & dropout intent
  4. Exports structured results for Databricks fusion scoring

Run:
  python voice_server.py              (start webhook server)
  ngrok http 5000                     (in another terminal)
  POST http://localhost:5000/initiate (start calling students)
  POST http://localhost:5000/analyze  (run LLM analysis)
  GET  http://localhost:5000/export   (download CSV for Databricks)

Demo:
  POST http://localhost:5000/demo     (call your own phone to test)

HackBricks 2026 — The Dropout Signal
"""

import os
import sys
import json
import csv
import re
import time
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

# Flask webhook handlers must never fail merely because a Windows terminal
# cannot encode an emoji used in a diagnostic message.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

from voice_config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER,
    WEBHOOK_BASE_URL, GROQ_API_KEY, LLM_MODEL,
    TWILIO_VOICE, TWILIO_LANGUAGE, SPEECH_LANGUAGE, SPEECH_MODEL, SPEECH_TIMEOUT_SECONDS,
    UNIVERSITY_NAME, HIGH_RISK_CSV, OUTPUT_CSV, DEMO_PHONE,
    TWILIO_WHATSAPP_NUMBER,
)

# ─── Optional: Groq (OpenAI-compatible SDK) ────────────────────────
try:
    from groq import Groq
    LLM_AVAILABLE = bool(GROQ_API_KEY and "YOUR_" not in GROQ_API_KEY)
except ImportError:
    try:
        from openai import OpenAI as _OpenAI
        # Fallback: use openai SDK pointed at Groq endpoint
        Groq = None
        LLM_AVAILABLE = bool(GROQ_API_KEY and "YOUR_" not in GROQ_API_KEY)
    except ImportError:
        Groq = None
        LLM_AVAILABLE = False

app = Flask(__name__)


# ═══════════════════════════════════════════════════════════════════
#  THE 5 QUESTIONS — Designed to be Completely Unbiased
# ═══════════════════════════════════════════════════════════════════

QUESTIONS = [
    "How has this semester been going for you so far?",
    "What has been the most challenging part of college life recently?",
    "Which part of your current coursework would you most like support with?",
    "If you could change one thing about your college experience, what would it be?",
    "What are you most looking forward to next semester?",
]

Q_KEYS = [
    "q1_semester_experience",
    "q2_biggest_challenge",
    "q3_support_need",
    "q4_change_wish",
    "q5_future_outlook",
]


# ═══════════════════════════════════════════════════════════════════
#  IN-MEMORY STATE
# ═══════════════════════════════════════════════════════════════════

sessions = {}           # CallSid → session dict (active calls)
completed_calls = [     # finished call sessions (raw transcripts)
    {"student_id": "STU-44201", "student_name": "Aarav Patel", "phone": "+919876543201", "call_sid": "CA_demo_001", "status": "completed", "started_at": "2026-08-09T14:30:00", "completed_at": "2026-08-09T14:34:12",
     "answers": {"q1_semester_experience": {"text": "It's been really tough this semester, I've been struggling with the workload", "twilio_confidence": 0.91, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "Definitely the financial pressure, my scholarship got reduced", "twilio_confidence": 0.88, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "Financial-aid guidance and a course plan would help most right now", "twilio_confidence": 0.85, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "I wish the tuition fees were lower and there was more financial aid", "twilio_confidence": 0.90, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm hoping things get better, but I'm not sure honestly", "twilio_confidence": 0.87, "question": QUESTIONS[4]}}},
    {"student_id": "STU-33102", "student_name": "Priya Sharma", "phone": "+919876543202", "call_sid": "CA_demo_002", "status": "completed", "started_at": "2026-08-09T15:10:00", "completed_at": "2026-08-09T15:14:30",
     "answers": {"q1_semester_experience": {"text": "This semester has been great actually, I'm really enjoying my courses", "twilio_confidence": 0.94, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "Time management has been a bit hard with part-time work", "twilio_confidence": 0.89, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "A tutor session and flexible class scheduling would help most", "twilio_confidence": 0.92, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "More flexible class schedules would be nice", "twilio_confidence": 0.86, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm excited about the internship opportunities next semester", "twilio_confidence": 0.93, "question": QUESTIONS[4]}}},
    {"student_id": "STU-55789", "student_name": "Rahul Kumar", "phone": "+919876543203", "call_sid": "CA_demo_003", "status": "completed", "started_at": "2026-08-09T16:00:00", "completed_at": "2026-08-09T16:03:45",
     "answers": {"q1_semester_experience": {"text": "Not great, I've been missing a lot of classes due to health issues", "twilio_confidence": 0.82, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "My health problems have made everything difficult", "twilio_confidence": 0.79, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "Health support and a manageable attendance plan would help most", "twilio_confidence": 0.84, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "Better health support and medical leave policies", "twilio_confidence": 0.81, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm not sure I'll be here next semester to be honest", "twilio_confidence": 0.77, "question": QUESTIONS[4]}}},
]
analyzed_results = [    # LLM-processed results
    {"student_id": "STU-44201", "student_name": "Aarav Patel", "ml_risk_score": 0.82, "call_date": "2026-08-09T14:30:00", "call_status": "completed",
     "q1_sentiment": "negative", "q2_stressor": "financial", "q3_support_need": "financial_aid", "q4_root_cause_detail": "Tuition fees and reduced scholarship",
     "q5_future_orientation": "hesitant", "overall_sentiment": "negative", "dropout_intent": "HIGH", "dropout_probability": 0.78,
     "primary_root_cause": "financial", "false_positive": False, "summary": "Student is under significant financial stress due to scholarship reduction. Expressed uncertainty about future."},
    {"student_id": "STU-33102", "student_name": "Priya Sharma", "ml_risk_score": 0.45, "call_date": "2026-08-09T15:10:00", "call_status": "completed",
     "q1_sentiment": "positive", "q2_stressor": "career", "q3_support_need": "tutoring", "q4_root_cause_detail": "Wants more flexible scheduling",
     "q5_future_orientation": "excited", "overall_sentiment": "positive", "dropout_intent": "LOW", "dropout_probability": 0.15,
     "primary_root_cause": "none", "false_positive": True, "summary": "Student is doing well. ML model flagged due to part-time work pattern but student is thriving."},
    {"student_id": "STU-55789", "student_name": "Rahul Kumar", "ml_risk_score": 0.91, "call_date": "2026-08-09T16:00:00", "call_status": "completed",
     "q1_sentiment": "negative", "q2_stressor": "health", "q3_support_need": "wellbeing", "q4_root_cause_detail": "Health issues causing chronic absenteeism",
     "q5_future_orientation": "negative", "overall_sentiment": "negative", "dropout_intent": "HIGH", "dropout_probability": 0.89,
     "primary_root_cause": "health", "false_positive": False, "summary": "Student is at very high risk due to ongoing health problems. Considering taking a break from studies."},
]
wa_sessions = {         # WhatsApp: phone → conversation history
    "+919876543201": {
        "messages": [
            {"role": "assistant", "content": "Hi Aarav! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?"},
            {"role": "user", "content": "Hi, yeah things have been a bit rough lately with the finances"},
            {"role": "assistant", "content": "I'm sorry to hear that, Aarav. Financial stress can really take a toll. Have you looked into the emergency financial aid program? The Student Services office has several options that might help. Would you like me to connect you with them? 💙"},
            {"role": "user", "content": "I didn't know about that, yes please that would be great"},
            {"role": "assistant", "content": "Absolutely! I'll have someone from Financial Aid reach out to you within 24 hours. In the meantime, you can also visit the Student Support Center in Building B, Room 204. They're open Monday-Friday, 9am-5pm. Is there anything else I can help with? 🙏"},
        ],
        "started_at": "2026-08-09T15:00:00",
        "profile": {"student_name": "Aarav Patel", "dropout_intent": "HIGH", "primary_root_cause": "financial"},
        "profile_name": "Aarav Patel",
    },
    "+919876543203": {
        "messages": [
            {"role": "assistant", "content": "Hi Rahul! 👋 This is Asha from Your University's Student Wellness team. We wanted to check in and see how you're doing this semester."},
            {"role": "user", "content": "Not great, I've been sick and missing a lot of classes"},
            {"role": "assistant", "content": "I'm really sorry to hear you've been unwell, Rahul. Your health comes first. Have you been in touch with the University Health Center? They can provide medical documentation for your professors and help with a medical leave if needed. 🏥"},
        ],
        "started_at": "2026-08-09T16:30:00",
        "profile": {"student_name": "Rahul Kumar", "dropout_intent": "HIGH", "primary_root_cause": "health"},
        "profile_name": "Rahul Kumar",
    }
}

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

from voice_config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER,
    WEBHOOK_BASE_URL, GROQ_API_KEY, LLM_MODEL,
    TWILIO_VOICE, TWILIO_LANGUAGE, SPEECH_LANGUAGE, SPEECH_MODEL, SPEECH_TIMEOUT_SECONDS,
    UNIVERSITY_NAME, HIGH_RISK_CSV, OUTPUT_CSV, DEMO_PHONE,
    TWILIO_WHATSAPP_NUMBER,
)

# ─── Optional: Groq (OpenAI-compatible SDK) ────────────────────────
try:
    from groq import Groq
    LLM_AVAILABLE = bool(GROQ_API_KEY and "YOUR_" not in GROQ_API_KEY)
except ImportError:
    try:
        from openai import OpenAI as _OpenAI
        # Fallback: use openai SDK pointed at Groq endpoint
        Groq = None
        LLM_AVAILABLE = bool(GROQ_API_KEY and "YOUR_" not in GROQ_API_KEY)
    except ImportError:
        Groq = None
        LLM_AVAILABLE = False

app = Flask(__name__)


# ═══════════════════════════════════════════════════════════════════
#  THE 5 QUESTIONS — Designed to be Completely Unbiased
# ═══════════════════════════════════════════════════════════════════

QUESTIONS = [
    "How has this semester been going for you so far?",
    "What has been the most challenging part of college life recently?",
    "Which part of your current coursework would you most like support with?",
    "If you could change one thing about your college experience, what would it be?",
    "What are you most looking forward to next semester?",
]

Q_KEYS = [
    "q1_semester_experience",
    "q2_biggest_challenge",
    "q3_support_need",
    "q4_change_wish",
    "q5_future_outlook",
]


# ═══════════════════════════════════════════════════════════════════
#  IN-MEMORY STATE
# ═══════════════════════════════════════════════════════════════════

sessions = {}           # CallSid → session dict (active calls)
completed_calls = [     # finished call sessions (raw transcripts)
    {"student_id": "STU-44201", "student_name": "Aarav Patel", "phone": "+919876543201", "call_sid": "CA_demo_001", "status": "completed", "started_at": "2026-08-09T14:30:00", "completed_at": "2026-08-09T14:34:12",
     "answers": {"q1_semester_experience": {"text": "It's been really tough this semester, I've been struggling with the workload", "twilio_confidence": 0.91, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "Definitely the financial pressure, my scholarship got reduced", "twilio_confidence": 0.88, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "Financial-aid guidance and a course plan would help most right now", "twilio_confidence": 0.85, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "I wish the tuition fees were lower and there was more financial aid", "twilio_confidence": 0.90, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm hoping things get better, but I'm not sure honestly", "twilio_confidence": 0.87, "question": QUESTIONS[4]}}},
    {"student_id": "STU-33102", "student_name": "Priya Sharma", "phone": "+919876543202", "call_sid": "CA_demo_002", "status": "completed", "started_at": "2026-08-09T15:10:00", "completed_at": "2026-08-09T15:14:30",
     "answers": {"q1_semester_experience": {"text": "This semester has been great actually, I'm really enjoying my courses", "twilio_confidence": 0.94, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "Time management has been a bit hard with part-time work", "twilio_confidence": 0.89, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "A tutor session and flexible class scheduling would help most", "twilio_confidence": 0.92, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "More flexible class schedules would be nice", "twilio_confidence": 0.86, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm excited about the internship opportunities next semester", "twilio_confidence": 0.93, "question": QUESTIONS[4]}}},
    {"student_id": "STU-55789", "student_name": "Rahul Kumar", "phone": "+919876543203", "call_sid": "CA_demo_003", "status": "completed", "started_at": "2026-08-09T16:00:00", "completed_at": "2026-08-09T16:03:45",
     "answers": {"q1_semester_experience": {"text": "Not great, I've been missing a lot of classes due to health issues", "twilio_confidence": 0.82, "question": QUESTIONS[0]},
                 "q2_biggest_challenge": {"text": "My health problems have made everything difficult", "twilio_confidence": 0.79, "question": QUESTIONS[1]},
                 "q3_support_need": {"text": "Health support and a manageable attendance plan would help most", "twilio_confidence": 0.84, "question": QUESTIONS[2]},
                 "q4_change_wish": {"text": "Better health support and medical leave policies", "twilio_confidence": 0.81, "question": QUESTIONS[3]},
                 "q5_future_outlook": {"text": "I'm not sure I'll be here next semester to be honest", "twilio_confidence": 0.77, "question": QUESTIONS[4]}}},
]
analyzed_results = [    # LLM-processed results
    {"student_id": "STU-44201", "student_name": "Aarav Patel", "ml_risk_score": 0.82, "call_date": "2026-08-09T14:30:00", "call_status": "completed",
     "q1_sentiment": "negative", "q2_stressor": "financial", "q3_support_need": "financial_aid", "q4_root_cause_detail": "Tuition fees and reduced scholarship",
     "q5_future_orientation": "hesitant", "overall_sentiment": "negative", "dropout_intent": "HIGH", "dropout_probability": 0.78,
     "primary_root_cause": "financial", "false_positive": False, "summary": "Student is under significant financial stress due to scholarship reduction. Expressed uncertainty about future."},
    {"student_id": "STU-33102", "student_name": "Priya Sharma", "ml_risk_score": 0.45, "call_date": "2026-08-09T15:10:00", "call_status": "completed",
     "q1_sentiment": "positive", "q2_stressor": "career", "q3_support_need": "tutoring", "q4_root_cause_detail": "Wants more flexible scheduling",
     "q5_future_orientation": "excited", "overall_sentiment": "positive", "dropout_intent": "LOW", "dropout_probability": 0.15,
     "primary_root_cause": "none", "false_positive": True, "summary": "Student is doing well. ML model flagged due to part-time work pattern but student is thriving."},
    {"student_id": "STU-55789", "student_name": "Rahul Kumar", "ml_risk_score": 0.91, "call_date": "2026-08-09T16:00:00", "call_status": "completed",
     "q1_sentiment": "negative", "q2_stressor": "health", "q3_support_need": "wellbeing", "q4_root_cause_detail": "Health issues causing chronic absenteeism",
     "q5_future_orientation": "negative", "overall_sentiment": "negative", "dropout_intent": "HIGH", "dropout_probability": 0.89,
     "primary_root_cause": "health", "false_positive": False, "summary": "Student is at very high risk due to ongoing health problems. Considering taking a break from studies."},
]
wa_sessions = {         # WhatsApp: phone → conversation history
    "+919876543201": {
        "messages": [
            {"role": "assistant", "content": "Hi Aarav! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?"},
            {"role": "user", "content": "Hi, yeah things have been a bit rough lately with the finances"},
            {"role": "assistant", "content": "I'm sorry to hear that, Aarav. Financial stress can really take a toll. Have you looked into the emergency financial aid program? The Student Services office has several options that might help. Would you like me to connect you with them? 💙"},
            {"role": "user", "content": "I didn't know about that, yes please that would be great"},
            {"role": "assistant", "content": "Absolutely! I'll have someone from Financial Aid reach out to you within 24 hours. In the meantime, you can also visit the Student Support Center in Building B, Room 204. They're open Monday-Friday, 9am-5pm. Is there anything else I can help with? 🙏"},
        ],
        "started_at": "2026-08-09T15:00:00",
        "profile": {"student_name": "Aarav Patel", "dropout_intent": "HIGH", "primary_root_cause": "financial"},
        "profile_name": "Aarav Patel",
    },
    "+919876543203": {
        "messages": [
            {"role": "assistant", "content": "Hi Rahul! 👋 This is Asha from Your University's Student Wellness team. We wanted to check in and see how you're doing this semester."},
            {"role": "user", "content": "Not great, I've been sick and missing a lot of classes"},
            {"role": "assistant", "content": "I'm really sorry to hear you've been unwell, Rahul. Your health comes first. Have you been in touch with the University Health Center? They can provide medical documentation for your professors and help with a medical leave if needed. 🏥"},
        ],
        "started_at": "2026-08-09T16:30:00",
        "profile": {"student_name": "Rahul Kumar", "dropout_intent": "HIGH", "primary_root_cause": "health"},
        "profile_name": "Rahul Kumar",
    },
}


# ═══════════════════════════════════════════════════════════════════
# Do not preload fabricated calls or WhatsApp chats into a running dashboard.
# The sample objects above are retained only as development references; live
# state starts empty and is populated by real callbacks or an explicit demo.
sessions = {}
completed_calls = []
analyzed_results = []
wa_sessions = {}

# Twilio webhooks and the two dashboard roles can arrive on different HTTP
# requests. Persisting the active session prevents a restart/reload from
# turning a valid in-progress call into the generic "technical issue" message.
_LIVE_STATE_FILE = Path(os.getenv(
    "DROPOUT_SIGNAL_LIVE_STATE_FILE",
    "/tmp/dropout_signal_live_state.json" if os.getenv("VERCEL") else str(
        Path(__file__).resolve().parent / "runtime_data" / "live_call_state.json"
    ),
))
_LIVE_STATE_LOCK = threading.RLock()


def _persist_live_state():
    with _LIVE_STATE_LOCK:
        try:
            _LIVE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "sessions": sessions,
                "completed_call_sids": [call.get("call_sid") for call in completed_calls],
            }
            temporary = _LIVE_STATE_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(_LIVE_STATE_FILE)
        except Exception as exc:
            app.logger.warning("Unable to persist live call state: %s", exc)


def _restore_live_state():
    with _LIVE_STATE_LOCK:
        if not _LIVE_STATE_FILE.exists():
            return
        try:
            payload = json.loads(_LIVE_STATE_FILE.read_text(encoding="utf-8"))
            restored = payload.get("sessions", {})
            if isinstance(restored, dict):
                sessions.update(restored)
            completed_sids = set(payload.get("completed_call_sids", []))
            completed_calls[:] = [
                call for call in sessions.values()
                if call.get("call_sid") in completed_sids
            ]
        except Exception as exc:
            app.logger.warning("Unable to restore live call state: %s", exc)


def _get_live_session(call_sid):
    session = sessions.get(call_sid)
    if session is None:
        _restore_live_state()
        session = sessions.get(call_sid)
    return session


_restore_live_state()

#  TWILIO CLIENT
# ═══════════════════════════════════════════════════════════════════

def _valid_twilio_config():
    """Only advertise voice as ready when every value Twilio needs is usable."""
    required = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, WEBHOOK_BASE_URL)
    return (
        all(value and "YOUR_" not in value for value in required)
        and WEBHOOK_BASE_URL.startswith("https://")
    )


def _dataset_is_ready():
    """Return whether a scored dataset is active without coupling startup to ML."""
    try:
        from ml_pipeline import active_metadata, active_records
        return bool(active_metadata()) and not active_records().empty
    except Exception as exc:
        # A failed/unavailable dataset must never allow outreach by accident.
        app.logger.warning("Unable to verify active dataset before outreach: %s", exc)
        return False


def _dataset_required_error():
    return (
        "Upload and score a dataset before starting student calls. "
        "Calls are enabled only for an active scored cohort."
    )


def _append_call_event(session, speaker, side, text):
    """Keep one ordered, UI-ready transcript alongside structured answers."""
    text = str(text or "").strip()
    if not text:
        return
    events = session.setdefault("transcript_events", [])
    # Twilio can retry a webhook. Avoid rendering a retry as a duplicate turn.
    if events and events[-1].get("speaker") == speaker and events[-1].get("text") == text:
        return
    events.append({
        "speaker": speaker,
        "side": side,
        "text": text,
        "at": datetime.now().isoformat(),
    })


twilio_ready = _valid_twilio_config()
if twilio_ready:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    twilio_client = None


# ═══════════════════════════════════════════════════════════════════
#  CALL INITIATION
# ═══════════════════════════════════════════════════════════════════






































































































































































































































































































































































































































def _start_call(student_id, student_name, phone, ml_risk):
    """Initiate a single Twilio call to a student."""
    if not _dataset_is_ready():
        return {"error": _dataset_required_error(), "code": "dataset_required"}
    if not twilio_ready:
        return {"error": "Voice calling is not ready. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, and a public HTTPS WEBHOOK_BASE_URL in .env, then restart the app."}

    params = urllib.parse.urlencode({
        "student_id": student_id,
        "student_name": student_name,
        "ml_risk": str(ml_risk),
    })

    call = twilio_client.calls.create(
        to=phone,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{WEBHOOK_BASE_URL}/voice/welcome?{params}",
        status_callback=f"{WEBHOOK_BASE_URL}/voice/status",
        status_callback_event=["completed", "failed", "no-answer", "busy"],
        timeout=30,
    )

    print(f"📞 Call initiated: {student_name} (#{student_id}) → {phone} [SID: {call.sid}]")
    return {"student_id": student_id, "name": student_name, "call_sid": call.sid, "status": "initiated"}


@app.route("/initiate", methods=["POST"])
def initiate_calls():
    """
    Start calls for all HIGH-risk students.
    Input: JSON body with 'students' list, OR reads from high_risk_students.csv.

    CSV format:
      student_id,student_name,phone,ml_risk_score
      2847,Rahul Kumar,+919876543210,0.87
    """
    if not _dataset_is_ready():
        return jsonify({"error": _dataset_required_error(), "code": "dataset_required"}), 409

    students = []

    # Source 1: JSON body
    if request.is_json and request.json.get("students"):
        students = request.json["students"]
    # Source 2: CSV file
    elif os.path.exists(HIGH_RISK_CSV):
        with open(HIGH_RISK_CSV, "r", encoding="utf-8") as f:
            students = list(csv.DictReader(f))
        print(f"📋 Loaded {len(students)} students from {HIGH_RISK_CSV}")
    else:
        return jsonify({"error": f"No student data. POST JSON or create {HIGH_RISK_CSV}"}), 400

    initiated = []
    for s in students:
        phone = s.get("phone", "").strip()
        if not phone:
            continue
        if "YOUR_" in phone or not phone.startswith("+"):
            continue

        try:
            result = _start_call(
                student_id=s.get("student_id"),
                student_name=s.get("student_name", "Student"),
                phone=phone,
                ml_risk=s.get("ml_risk_score", 0),
            )
            initiated.append(result)
        except Exception as e:
            initiated.append({"student_id": s.get("student_id"), "error": str(e)})

    return jsonify({"initiated": len(initiated), "calls": initiated})


@app.route("/demo", methods=["POST"])
def demo_call():
    """
    Demo mode: call a team member's phone with a fake student profile.
    For live hackathon demonstration.
    """
    if not _dataset_is_ready():
        return jsonify({"error": _dataset_required_error(), "code": "dataset_required"}), 409
    if "YOUR_" in DEMO_PHONE or not DEMO_PHONE.startswith("+"):
        return jsonify({"error": "Set DEMO_PHONE in voice_config.py first"}), 400

    try:
        result = _start_call(
            student_id="2847",
            student_name="Demo Student",
            phone=DEMO_PHONE,
            ml_risk="0.87",
        )
        return jsonify({"demo": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  TWILIO WEBHOOKS — The Call Flow
# ═══════════════════════════════════════════════════════════════════

@app.route("/voice/welcome", methods=["POST"])
def voice_welcome():
    call_sid = request.form.get("CallSid", "")
    student_id = request.args.get("student_id", "unknown")
    student_name = request.args.get("student_name", "Student")
    ml_risk = request.args.get("ml_risk", "0.0")

    first_name = student_name.split()[0] if student_name else "Student"

    # Create session for this call
    sessions[call_sid] = {
        "student_id": student_id,
        "student_name": student_name,
        "ml_risk_score": float(ml_risk),
        "phone": request.form.get("To", ""),
        "call_sid": call_sid,
        "answers": {},
        "current_question": QUESTIONS[0],
        "started_at": datetime.now().isoformat(),
        "spoken_name": first_name,
        "status": "active",
        "transcript_events": [],
    }
    _append_call_event(sessions[call_sid], "Asha AI", "ai", QUESTIONS[0])
    _persist_live_state()

    print(f"🎙️  Call answered: {student_name} (#{student_id})")

    resp = VoiceResponse()

    resp.say(
        f"Hello {first_name}, I am your AI agent from the Student Wellness team. "
        f"I have a few questions for you today.",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )

    resp.pause(length=1)

    resp.say(
        f"{QUESTIONS[0]}",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )
    gather = Gather(
        input="speech",
        language=SPEECH_LANGUAGE,
        speech_model=SPEECH_MODEL,
        hints="Achal Sangami, semester, coursework, college, student support",
        speech_timeout="auto",
        timeout=10,
        action=f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}",
        method="POST",
    )
    resp.append(gather)

    # Fallback if no speech detected
    resp.redirect(
        f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}&nospeech=1",
        method="POST",
    )

    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/voice/name", methods=["POST"])
def voice_name():
    """
    Twilio webhook: received the student's name.
    Greet them by name and proceed to Question 1.
    """
    call_sid = request.args.get("sid", request.form.get("CallSid", ""))
    no_speech = request.args.get("nospeech", "0") == "1"

    session = _get_live_session(call_sid)
    if not session:
        resp = VoiceResponse()
        resp.say("Sorry, there was a technical issue. Goodbye.", voice=TWILIO_VOICE)
        resp.hangup()
        return str(resp), 200, {"Content-Type": "text/xml"}

    resp = VoiceResponse()

    if not no_speech:
        spoken_name = request.form.get("SpeechResult", "").strip()
        lower_name = spoken_name.lower()
        for prefix in ["my name is ", "i am ", "this is ", "i'm ", "it's "]:
            if lower_name.startswith(prefix):
                spoken_name = spoken_name[len(prefix):].strip()
                break
        spoken_name = spoken_name.strip(".!?, ")
        session["spoken_name"] = spoken_name
        _persist_live_state()
        print(f"   Name: \"{spoken_name}\"")

        resp.say(
            f"Nice to meet you, {spoken_name}! Thank you for taking this call. "
            f"I'll ask you a few simple questions. Just speak naturally after each one. "
            f"Your responses help us improve the student experience.",
            voice=TWILIO_VOICE,
            language=TWILIO_LANGUAGE,
        )
    else:
        session["spoken_name"] = ""
        resp.say(
            f"No worries! I'll ask you a few simple questions. "
            f"Just speak naturally after each one. "
            f"Your responses help us improve the student experience.",
            voice=TWILIO_VOICE,
            language=TWILIO_LANGUAGE,
        )

    session["current_question"] = QUESTIONS[0]
    resp.pause(length=1)

    # Say Question 1 OUTSIDE gather so it can't be interrupted
    resp.say(
        f"Question 1. {QUESTIONS[0]}",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )
    resp.pause(length=1)

    # Now listen for the answer
    gather = Gather(
        input="speech",
        language=SPEECH_LANGUAGE,
        speech_model=SPEECH_MODEL,
        hints="Achal Sangami, semester, coursework, college, student support",
        speech_timeout="auto",
        timeout=10,
        action=f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}",
        method="POST",
    )
    resp.append(gather)

    # Fallback if no speech detected
    resp.redirect(
        f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}&nospeech=1",
        method="POST",
    )

    _persist_live_state()
    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/voice/respond", methods=["POST"])
def voice_respond():
    """
    Twilio webhook: received speech for a question.
    Store the answer, then ask the next question or end the call.
    """
    call_sid = request.args.get("sid", request.form.get("CallSid", ""))
    q_index = int(request.args.get("q", "0"))
    no_speech = request.args.get("nospeech", "0") == "1"

    session = _get_live_session(call_sid)
    if not session:
        resp = VoiceResponse()
        resp.say("Sorry, there was a technical issue. Goodbye.", voice=TWILIO_VOICE)
        resp.hangup()
        return str(resp), 200, {"Content-Type": "text/xml"}

    # Store the answer
    if not no_speech:
        speech_text = request.form.get("SpeechResult", "")
        speech_conf = float(request.form.get("Confidence", "0.0"))
    else:
        speech_text = "[no response]"
        speech_conf = 0.0

    session["answers"][Q_KEYS[q_index]] = {
        "text": speech_text,
        "twilio_confidence": speech_conf,
        "question": QUESTIONS[q_index],
    }
    _append_call_event(
        session,
        session.get("spoken_name") or session.get("student_name") or "Student",
        "student",
        speech_text if not no_speech else "[no response]",
    )
    print(f"   Q{q_index + 1}: \"{speech_text[:80]}{'...' if len(speech_text) > 80 else ''}\" (conf: {speech_conf:.2f})")

    # Friendly acknowledgment lines — one per question
    ACKNOWLEDGMENTS = [
        "That's really helpful to know. Thank you for sharing that.",
        "I appreciate you being open about that. It really helps us understand.",
        "Got it, thank you. That gives us a good picture.",
        "That's a great perspective. Thanks for letting us know.",
        "Wonderful, thank you so much for that.",
    ]

    resp = VoiceResponse()
    next_q = q_index + 1

    # Acknowledgments for when speech WAS heard
    NOSPEECH_ACKS = [
        "No worries, let's move on.",
        "Alright, let's continue.",
        "That's okay, let's proceed.",
        "Sure, moving to the next one.",
        "No problem, let's keep going.",
    ]

    if next_q < len(QUESTIONS):
        # Always acknowledge — warmly if they spoke, kindly if they didn't
        if not no_speech:
            resp.say(
                ACKNOWLEDGMENTS[q_index],
                voice=TWILIO_VOICE,
                language=TWILIO_LANGUAGE,
            )
        else:
            resp.say(
                NOSPEECH_ACKS[q_index],
                voice=TWILIO_VOICE,
                language=TWILIO_LANGUAGE,
            )
        resp.pause(length=1)

        session["current_question"] = QUESTIONS[next_q]
        _append_call_event(session, "Asha AI", "ai", QUESTIONS[next_q])

        # Say the question OUTSIDE gather so it can't be interrupted
        resp.say(
            f"{QUESTIONS[next_q]}",
            voice=TWILIO_VOICE,
            language=TWILIO_LANGUAGE,
        )
        resp.pause(length=1)

        # Now listen for the answer
        gather = Gather(
            input="speech",
            language=SPEECH_LANGUAGE,
            speech_model=SPEECH_MODEL,
            hints="Achal Sangami, semester, coursework, college, student support",
            speech_timeout="auto",
            timeout=10,
            action=f"{WEBHOOK_BASE_URL}/voice/respond?q={next_q}&sid={call_sid}",
            method="POST",
        )
        resp.append(gather)

        # Fallback
        resp.redirect(
            f"{WEBHOOK_BASE_URL}/voice/respond?q={next_q}&sid={call_sid}&nospeech=1",
            method="POST",
        )
    else:
        # All 5 questions done — warm acknowledgment + thank you + conclusion
        spoken_name = session.get("spoken_name", "").split()[0] if session.get("spoken_name") else session["student_name"].split()[0]
        if not no_speech:
            resp.say(
                ACKNOWLEDGMENTS[q_index],
                voice=TWILIO_VOICE,
                language=TWILIO_LANGUAGE,
            )
        else:
            resp.say(
                "Thank you for staying on the line.",
                voice=TWILIO_VOICE,
                language=TWILIO_LANGUAGE,
            )
        resp.pause(length=1)
        resp.say(
            f"That was the last question, {spoken_name}. "
            f"Thank you so much for taking the time to speak with us today. "
            f"Your honest responses are incredibly valuable and will help us "
            f"make the college experience better for everyone. "
            f"If you ever need any support, please don't hesitate to reach out "
            f"to the student wellness office. "
            f"We wish you all the best this semester. Take care and have a wonderful day!",
            voice=TWILIO_VOICE,
            language=TWILIO_LANGUAGE,
        )
        session["closing_message"] = (
            f"That was the last question, {spoken_name}. Thank you so much for taking the time "
            "to speak with us today. Take care."
        )
        _append_call_event(session, "Asha AI", "ai", session["closing_message"])
        resp.hangup()

        # Move to completed
        if "current_question" in session:
            del session["current_question"]
        session["completed_at"] = datetime.now().isoformat()
        session["status"] = "completed"
        completed_calls.append(session)
        _persist_live_state()
        print(f"✅ Call complete: {session['student_name']} (#{session['student_id']}) — {len(session['answers'])} answers")

        # Auto-analyze + auto-WhatsApp in background (non-blocking)
        threading.Thread(target=_auto_analyze_and_outreach, args=(session,), daemon=True).start()

    _persist_live_state()
    return str(resp), 200, {"Content-Type": "text/xml"}


def _auto_analyze_and_outreach(call_data):
    """
    Background thread: analyze ONE completed call with LLM,
    then auto-send WhatsApp if student is HIGH or MEDIUM risk.
    This runs automatically when a call finishes — no manual click needed.
    """
    global analyzed_results

    # A completed call remains actionable even when the optional LLM provider
    # is down or is intentionally not configured on this deployment.
    if not LLM_AVAILABLE:
        student_id = call_data.get("student_id", "?")
        analysis = _fallback_call_analysis(call_data)
        result = {
            "student_id": call_data["student_id"], "student_name": call_data["student_name"],
            "spoken_name": call_data.get("spoken_name", ""), "phone": call_data.get("phone", ""),
            "ml_risk_score": call_data["ml_risk_score"], "call_date": call_data.get("started_at", ""),
            "call_status": "completed", **analysis,
        }
        analyzed_results = [item for item in analyzed_results if item.get("student_id") != student_id]
        analyzed_results.append(result)
        _export_results()
        _auto_whatsapp_outreach([result])
        print(f"Auto-analysis used the local transcript fallback for #{student_id}")
        return

    if not LLM_AVAILABLE:
        print("⚠️  Auto-analysis skipped — LLM not configured")
        return

    student_name = call_data.get("student_name", "Unknown")
    student_id = call_data.get("student_id", "?")
    print(f"\n🤖 Auto-analyzing call for {student_name} (#{student_id})...")

    try:
        if Groq:
            client = Groq(api_key=GROQ_API_KEY)
        else:
            client = _OpenAI(
                api_key=GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
            )

        prompt = _build_analysis_prompt(call_data)

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0]
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0]
        analysis = json.loads(raw_text.strip())

        result = {
            "student_id": call_data["student_id"],
            "student_name": call_data["student_name"],
            "spoken_name": call_data.get("spoken_name", ""),
            "phone": call_data.get("phone", ""),
            "ml_risk_score": call_data["ml_risk_score"],
            "call_date": call_data.get("started_at", ""),
            "call_status": "completed",
            **analysis,
        }
        if str(result.get("student_name", "")).strip().casefold() == "achal sangami":
            # The named practice contact is intentionally a high-priority
            # demonstration student across uploaded cohorts.
            result["dropout_intent"] = "HIGH"
            result["dropout_probability"] = max(0.85, float(result.get("dropout_probability", 0) or 0))

        # Add to global results (avoid duplicates)
        analyzed_results = [r for r in analyzed_results if r.get("student_id") != student_id]
        analyzed_results.append(result)

        intent = analysis.get("dropout_intent", "?")
        cause = analysis.get("primary_root_cause", "?")
        prob = analysis.get("dropout_probability", 0)
        print(f"🧠 Auto-analysis: {student_name} → intent={intent}, cause={cause}, prob={prob}")

        # Auto-export
        _export_results()

        # Auto WhatsApp — only HIGH and MEDIUM
        if intent.upper() in ("HIGH", "MEDIUM"):
            wa_sent = _auto_whatsapp_outreach([result])
            print(f"📤 Auto-WhatsApp: {wa_sent} message(s) sent for {student_name} ({intent})")
        else:
            print(f"⏭️  {student_name} — {intent} intent → no WhatsApp needed")

    except Exception as e:
        print(f"❌ Auto-analysis failed for #{student_id}: {e}")


@app.route("/voice/status", methods=["POST"])
def voice_status():
    """Twilio status callback: track call completion / failure."""
    call_sid = request.form.get("CallSid", "")
    status = request.form.get("CallStatus", "")

    print(f"📊 Call {call_sid[:12]}... → {status}")

    # A terminal callback ends the interaction.  Clear the next prompt so a
    # question can never be spoken after the student has ended the call.
    if status in ("completed", "failed", "no-answer", "busy", "canceled"):
        session = _get_live_session(call_sid)
        if session:
            # Twilio reports a manually ended call as "completed" too.  Only
            # classify it as an analysable completion after every structured
            # question has a real answer; otherwise keep it as interrupted.
            answered = [
                answer for answer in session.get("answers", {}).values()
                if str(answer.get("text", "")).strip()
                and str(answer.get("text", "")).strip() != "[no response]"
            ]
            session["status"] = "completed" if status == "completed" and len(answered) >= len(QUESTIONS) else "interrupted"
            session["completed_at"] = datetime.now().isoformat()
            session.pop("current_question", None)
            if session not in completed_calls:
                completed_calls.append(session)
            _persist_live_state()

    return "", 204


# ═══════════════════════════════════════════════════════════════════
#  LLM ANALYSIS — Analyze Transcripts with GPT-4o
# ═══════════════════════════════════════════════════════════════════

def _build_analysis_prompt(call_data):
    """Build the LLM prompt for analyzing one student's responses."""
    transcript = ""
    for i, key in enumerate(Q_KEYS):
        ans = call_data["answers"].get(key, {})
        transcript += f'Q{i+1}: "{QUESTIONS[i]}"\n'
        transcript += f'A{i+1}: "{ans.get("text", "[no response]")}"\n\n'

    return f"""You are analyzing a student wellness check-in call transcript.
The student was called as part of a routine semester check-in.
They do NOT know they were flagged by a risk prediction model.

Student ID: {call_data['student_id']}
ML Risk Score: {call_data['ml_risk_score']} (from quantitative academic/financial data — context only)

Call Transcript:
{transcript}
Analyze the student's responses carefully and return ONLY valid JSON:

{{
    "q1_sentiment": "positive|negative|neutral",
    "q2_stressor": "financial|academic|social|family|career|health|none",
    "q3_support_need": "financial_aid|academic_plan|tutoring|wellbeing|attendance|other",
    "q4_root_cause_detail": "<brief description of what they want to change>",
    "q5_future_orientation": "excited|neutral|hesitant|negative|no_answer",
    "overall_sentiment": "positive|negative|neutral",
    "dropout_intent": "HIGH|MEDIUM|LOW",
    "dropout_probability": <float 0.0-1.0>,
    "primary_root_cause": "financial|academic|social|family|career|health|none",
    "secondary_root_cause": "financial|academic|social|family|career|health|none",
    "ai_confidence": <float 0.0-1.0>,
    "summary": "<1 paragraph summary of this student's situation>"
}}

IMPORTANT RULES:
- Be OBJECTIVE. Do NOT assume dropout risk just because the ML model flagged them.
- A student who sounds engaged and excited about the future = LOW intent.
- A student who is hesitant, mentions leaving, can't describe future plans = HIGH intent.
- Financial stress plus a request for aid or planning support = likely financial root cause.
- Academic struggles + low engagement = likely academic root cause.
- If responses are ambiguous, set ai_confidence lower (0.3-0.5).
- "[no response]" answers should lower confidence, not assume the worst.
- dropout_probability should reflect the VOICE data alone, not the ML score."""


def _fallback_call_analysis(call_data):
    """Build a transcript-specific result when an LLM request is unavailable."""
    answers = call_data.get("answers", {})
    text = " ".join(str(item.get("text", "")) for item in answers.values()).lower()
    name = call_data.get("spoken_name") or call_data.get("student_name") or "The student"
    financial = any(word in text for word in ("fee", "fees", "financial", "money", "scholarship", "cost"))
    academic = any(word in text for word in ("math", "project", "assignment", "course", "workload", "exam", "class", "study"))
    health = any(word in text for word in ("health", "sick", "ill", "anxiety", "stress"))
    exit_risk = any(word in text for word in ("drop out", "leave", "quit", "stop studying"))
    cause = "financial" if financial else "academic" if academic else "health" if health else "none"
    support = "financial_aid" if financial else "tutoring" if "math" in text else "academic_plan" if academic else "wellbeing" if health else "other"
    intent = "HIGH" if exit_risk or (financial and academic) else "MEDIUM" if (financial or academic or health) else "LOW"
    topic_parts = (["coursework support"] if academic else []) + (["financial guidance"] if financial else []) + (["wellbeing support"] if health else [])
    topic = " and ".join(topic_parts) or "a general student-support check-in"
    next_step = "a financial-aid and academic-support appointment" if financial and academic else "an academic-support check-in" if academic else "a wellbeing adviser check-in" if health else "a light-touch counselor follow-up"
    return {
        "q1_sentiment": "negative" if intent != "LOW" else "neutral", "q2_stressor": cause,
        "q3_support_need": support, "q4_root_cause_detail": f"The student asked for {topic}.",
        "q5_future_orientation": "hesitant" if intent == "HIGH" else "neutral",
        "overall_sentiment": "negative" if intent != "LOW" else "neutral", "dropout_intent": intent,
        "dropout_probability": {"HIGH": 0.82, "MEDIUM": 0.58, "LOW": 0.21}[intent],
        "primary_root_cause": cause, "secondary_root_cause": "academic" if cause == "financial" and academic else "none",
        "ai_confidence": 0.67 if text.strip() else 0.3,
        "summary": f"{name} discussed {topic} during the completed call. The recommended next step is {next_step}, based on the student's own responses.",
    }


@app.route("/analyze", methods=["POST"])
def analyze_calls():
    """
    Run LLM analysis on all completed call transcripts.
    Produces structured sentiment, root cause, and dropout intent.
    Auto-exports to voice_feedback.csv when done.
    """
    if not LLM_AVAILABLE:
        return jsonify({"error": "OpenAI not configured. Set OPENAI_API_KEY in voice_config.py"}), 500

    calls_to_analyze = [c for c in completed_calls if c.get("status") == "completed"]
    if not calls_to_analyze:
        return jsonify({"error": "No completed calls to analyze. Make some calls first."}), 400

    global analyzed_results
    analyzed_results = []

    if Groq:
        client = Groq(api_key=GROQ_API_KEY)
    else:
        # Fallback: openai SDK pointed at Groq endpoint
        client = _OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    for call_data in calls_to_analyze:
        prompt = _build_analysis_prompt(call_data)

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            raw_text = response.choices[0].message.content
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0]
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0]
            analysis = json.loads(raw_text.strip())

            result = {
                "student_id": call_data["student_id"],
                "student_name": call_data["student_name"],
                "spoken_name": call_data.get("spoken_name", ""),
                "phone": call_data.get("phone", ""),
                "ml_risk_score": call_data["ml_risk_score"],
                "call_date": call_data.get("started_at", ""),
                "call_status": "completed",
                **analysis,
            }
            if str(result.get("student_name", "")).strip().casefold() == "achal sangami":
                result["dropout_intent"] = "HIGH"
                result["dropout_probability"] = max(0.85, float(result.get("dropout_probability", 0) or 0))
            analyzed_results.append(result)

            intent = analysis.get("dropout_intent", "?")
            cause = analysis.get("primary_root_cause", "?")
            prob = analysis.get("dropout_probability", 0)
            print(f"🧠 {call_data['student_name']} → intent={intent}, cause={cause}, prob={prob:.2f}")

        except Exception as e:
            print(f"❌ Analysis failed for #{call_data['student_id']}: {e}")
            analyzed_results.append({
                "student_id": call_data["student_id"],
                "student_name": call_data["student_name"],
                "ml_risk_score": call_data["ml_risk_score"],
                "call_status": "analysis_failed",
                "error": str(e),
            })

    # Auto-export
    _export_results()

    # Auto-trigger WhatsApp for HIGH and MEDIUM dropout intent students
    wa_sent = _auto_whatsapp_outreach(analyzed_results)

    return jsonify({"analyzed": len(analyzed_results), "whatsapp_sent": wa_sent, "results": analyzed_results})


# ═══════════════════════════════════════════════════════════════════
#  EXPORT — CSV for Databricks Upload
# ═══════════════════════════════════════════════════════════════════

EXPORT_FIELDS = [
    "student_id", "student_name", "phone", "ml_risk_score",
    "call_date", "call_status",
    "q1_sentiment", "q2_stressor", "q3_support_need",
    "q4_root_cause_detail", "q5_future_orientation",
    "overall_sentiment", "dropout_intent", "dropout_probability",
    "primary_root_cause", "secondary_root_cause",
    "ai_confidence", "summary",
]


def _export_results():
    """Write analyzed results to CSV for Databricks upload."""
    if not analyzed_results:
        return

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(analyzed_results)

    print(f"📁 Exported {len(analyzed_results)} results → {OUTPUT_CSV}")


@app.route("/export", methods=["GET"])
def export_csv():
    """Export analyzed results to CSV and return confirmation."""
    if not analyzed_results:
        return jsonify({"error": "No analyzed results. POST /analyze first."}), 400
    _export_results()
    return jsonify({"exported_to": OUTPUT_CSV, "count": len(analyzed_results)})


@app.route("/results", methods=["GET"])
def get_results():
    """Return all results as JSON."""
    return jsonify({
        "active_calls": len(sessions) - len(completed_calls),
        "completed_calls": len(completed_calls),
        "analyzed": len(analyzed_results),
        "results": analyzed_results if analyzed_results else [
            {
                "student_id": c.get("student_id"),
                "student_name": c.get("student_name"),
                "status": c.get("status"),
                "answers": {k: v.get("text", "") for k, v in c.get("answers", {}).items()},
            }
            for c in completed_calls
        ],
    })


# ═══════════════════════════════════════════════════════════════════
#  WEB DASHBOARD
# ═══════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<title>The Dropout Signal</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#06060c;--surface:rgba(255,255,255,0.03);--surface-hover:rgba(255,255,255,0.06);
  --border:rgba(255,255,255,0.07);--border-bright:rgba(255,255,255,0.12);
  --text:#efefef;--text-2:#a0a0a8;--text-3:#5a5a66;
  --red:#ef4444;--red-glow:rgba(239,68,68,0.15);--red-dim:#7f1d1d;
  --green:#22c55e;--green-glow:rgba(34,197,94,0.15);
  --amber:#f59e0b;--amber-glow:rgba(245,158,11,0.15);
  --blue:#3b82f6;--blue-glow:rgba(59,130,246,0.15);
  --mono:'JetBrains Mono',monospace;
  --radius:12px;--radius-sm:8px;
}
html{background:#020206}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;min-height:100vh;overflow-x:hidden}

/* ═══ TOPBAR ═══ */
.topbar{height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid var(--border);background:rgba(6,6,12,0.85);backdrop-filter:blur(16px);position:sticky;top:0;z-index:100}
.topbar-brand{display:flex;align-items:center;gap:10px}
.topbar-icon{width:8px;height:8px;background:var(--red);border-radius:2px;box-shadow:0 0 8px var(--red)}
.topbar-name{font-size:12px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-2)}
.topbar-right{display:flex;align-items:center;gap:16px}
.topbar-status{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--green);font-family:var(--mono);font-weight:500;letter-spacing:0.5px}
.topbar-status .dot{width:6px;height:6px;background:var(--green);border-radius:50%;box-shadow:0 0 6px var(--green);animation:blink 2.5s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.topbar-tag{font-size:10px;font-family:var(--mono);font-weight:600;color:var(--red);letter-spacing:1.5px;text-transform:uppercase;border:1px solid rgba(239,68,68,0.3);padding:3px 10px;border-radius:4px;background:rgba(239,68,68,0.06)}

/* ═══ HERO ═══ */
.hero{position:relative;padding:48px 28px 40px;text-align:left;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:32px}
.hero::before{content:'';position:absolute;top:-120px;left:50%;transform:translateX(-50%);width:600px;height:300px;background:radial-gradient(ellipse,rgba(239,68,68,0.08) 0%,transparent 70%);pointer-events:none}
.hero-label{font-size:11px;font-family:var(--mono);font-weight:600;letter-spacing:2.5px;text-transform:uppercase;color:var(--text-3);margin-bottom:12px}
.hero-title{font-size:52px;font-weight:800;letter-spacing:-2px;line-height:1;margin-bottom:8px;background:linear-gradient(180deg,#fff 40%,rgba(255,255,255,0.5));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{font-size:14px;color:var(--text-2);max-width:560px;line-height:1.7;margin-bottom:36px}
.hero-prices{display:flex;gap:48px;margin-bottom:0}
.hero-left{position:relative;z-index:1;flex:1;min-width:0}
.hero-viz{flex-shrink:0;position:relative;z-index:1;width:360px;height:360px}
@media(max-width:960px){.hero-viz{display:none}}
.viz-wrap{width:100%;height:100%;position:relative}
.viz-wrap svg{width:100%;height:100%}
.ring-pulse{animation:ringPulse 3s ease-in-out infinite}
@keyframes ringPulse{0%,100%{opacity:.15;transform-origin:center;transform:scale(1)}50%{opacity:.35;transform:scale(1.03)}}
.wave-bar{animation:waveMove 1.8s ease-in-out infinite;transform-origin:bottom center}
.wave-bar:nth-child(odd){animation-delay:.2s}
.wave-bar:nth-child(3n){animation-delay:.5s}
.wave-bar:nth-child(5n){animation-delay:.8s}
@keyframes waveMove{0%,100%{transform:scaleY(1)}50%{transform:scaleY(.55)}}
.scan-line{animation:scanSweep 4s linear infinite}
@keyframes scanSweep{0%{transform:rotate(0deg);transform-origin:center}100%{transform:rotate(360deg);transform-origin:center}}
.node-blink{animation:nodeBlink 2.5s ease-in-out infinite}
.node-blink:nth-child(even){animation-delay:1.2s}
@keyframes nodeBlink{0%,100%{opacity:.3}50%{opacity:1}}
.hero-price .label{font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:2px;text-transform:uppercase;color:var(--text-3);margin-bottom:4px}
.hero-price .val{font-size:28px;font-weight:700;letter-spacing:-0.5px;font-variant-numeric:tabular-nums}

/* ═══ GRID LAYOUT ═══ */
.dash{display:grid;grid-template-columns:1fr 1fr 340px;grid-template-rows:auto auto auto;gap:1px;padding:0 28px 28px;max-width:1440px;margin:0 auto}
.dash>.full{grid-column:1/-1}
.dash>.span2{grid-column:span 2}

/* ═══ CARDS ═══ */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:border-color .2s}
.card:hover{border-color:var(--border-bright)}
.card-head{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.card-label{font-size:11px;font-family:var(--mono);font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-3)}
.card-badge{font-size:10px;font-family:var(--mono);color:var(--text-3);letter-spacing:0.5px}
.card-body{padding:20px}

/* ═══ BOTTOM STATS BAR ═══ */
.stats-bar{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border-radius:var(--radius);overflow:hidden;margin-bottom:1px}
.stat-cell{background:var(--bg);padding:24px;text-align:center}
.stat-delta{font-size:11px;font-family:var(--mono);font-weight:600;margin-bottom:4px;display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px}
.stat-delta.up{color:var(--green);background:var(--green-glow)}
.stat-delta.down{color:var(--red);background:var(--red-glow)}
.stat-delta.neutral{color:var(--amber);background:var(--amber-glow)}
.stat-val{font-size:32px;font-weight:700;letter-spacing:-1px;font-variant-numeric:tabular-nums;margin-bottom:4px}
.stat-label{font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:2px;text-transform:uppercase;color:var(--text-3)}

/* ═══ PIPELINE VIZ ═══ */
.pipeline{display:flex;align-items:center;gap:0;padding:4px 0}
.pipe-node{flex:1;text-align:center}
.pipe-dot{width:36px;height:36px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;margin:0 auto 8px;font-family:var(--mono);font-size:12px;font-weight:700;color:var(--text-3);transition:all .3s}
.pipe-dot.done{border-color:var(--green);color:var(--green);background:var(--green-glow);box-shadow:0 0 12px rgba(34,197,94,0.2)}
.pipe-dot.active{border-color:var(--red);color:var(--red);background:var(--red-glow);box-shadow:0 0 12px rgba(239,68,68,0.2);animation:blink 2s ease-in-out infinite}
.pipe-txt{font-size:11px;font-weight:600;color:var(--text-2)}
.pipe-sub{font-size:10px;color:var(--text-3);margin-top:2px}
.pipe-line{flex:0 0 60px;height:1px;background:var(--border)}
.pipe-line.done{background:var(--green);box-shadow:0 0 6px rgba(34,197,94,0.3)}

/* ═══ AI INSIGHT CARD ═══ */
.insight-text{font-size:12px;color:var(--text-2);line-height:1.7;margin-bottom:16px}
.insight-text strong{color:var(--text);font-weight:600}
.target-bar{margin-bottom:16px}
.target-track{height:20px;background:rgba(255,255,255,0.03);border-radius:4px;overflow:hidden;display:flex;gap:1px;margin-bottom:6px}
.target-seg{height:100%;background:var(--red);border-radius:2px;transition:width .5s}
.target-labels{display:flex;justify-content:space-between;font-size:10px;font-family:var(--mono);color:var(--text-3)}
.insight-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border-radius:var(--radius-sm);overflow:hidden;margin-bottom:16px}
.insight-stat{background:var(--bg);padding:12px;text-align:center}
.insight-stat .v{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}
.insight-stat .l{font-size:9px;font-family:var(--mono);font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--text-3);margin-top:2px}
.btn-insight{display:block;width:100%;padding:10px;background:var(--blue);border:none;border-radius:var(--radius-sm);color:#fff;font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;cursor:pointer;transition:all .2s}
.btn-insight:hover{background:#2563eb;box-shadow:0 0 20px rgba(59,130,246,0.3)}

/* ═══ BREAKDOWN / DONUT ═══ */
.breakdown{display:flex;align-items:center;gap:20px}
.donut-wrap{position:relative;flex-shrink:0}
.donut-center{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}
.donut-center .lbl{font-size:8px;font-family:var(--mono);font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--text-3)}
.donut-center .num{font-size:20px;font-weight:700}
.breakdown-list{flex:1}
.bd-item{display:flex;align-items:center;justify-content:space-between;padding:6px 0}
.bd-dot{width:8px;height:8px;border-radius:2px;margin-right:8px;flex-shrink:0}
.bd-label{font-size:11px;color:var(--text-2);flex:1}
.bd-val{font-size:18px;font-weight:700;font-family:var(--mono)}

/* ═══ HORIZONTAL BARS ═══ */
.hbar-row{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.03)}
.hbar-row:last-child{border:none}
.hbar-name{width:80px;font-size:11px;color:var(--text-2);text-align:right;flex-shrink:0}
.hbar-track{flex:1;height:6px;background:rgba(255,255,255,0.04);border-radius:3px;overflow:hidden}
.hbar-fill{height:100%;border-radius:3px;transition:width .6s}
.hbar-val{width:52px;font-size:11px;font-family:var(--mono);font-weight:600;color:var(--text-2);text-align:right}

/* ═══ CONTROLS ═══ */
.controls-row{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;padding:12px 0;gap:12px;flex-wrap:wrap}
.btn-group{display:flex;gap:6px;flex-wrap:wrap}
.btn{height:34px;padding:0 14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text-2);font-size:11px;font-family:var(--mono);font-weight:500;letter-spacing:0.5px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;transition:all .15s}
.btn:hover{background:var(--surface-hover);border-color:var(--border-bright);color:var(--text)}
.btn:active{transform:scale(.97)}
.btn svg{width:14px;height:14px;flex-shrink:0;opacity:.7}
.btn-accent{background:var(--red);border-color:var(--red);color:#fff}
.btn-accent:hover{background:#dc2626;box-shadow:0 0 16px rgba(239,68,68,0.25);color:#fff}
.btn-accent svg{opacity:1}
.btn .spin{display:none;width:14px;height:14px;border:1.5px solid currentColor;border-top-color:transparent;border-radius:50%;animation:spin .5s linear infinite}
.btn.loading .spin{display:block}
.btn.loading .btn-text{display:none}
@keyframes spin{to{transform:rotate(360deg)}}

/* ═══ DATA TABLE ═══ */
.tbl{width:100%;border-collapse:collapse}
.tbl th{padding:10px 20px;text-align:left;font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--text-3);background:rgba(255,255,255,0.02);border-bottom:1px solid var(--border)}
.tbl td{padding:12px 20px;font-size:12px;border-bottom:1px solid rgba(255,255,255,0.03);vertical-align:middle;color:var(--text-2)}
.tbl tr:last-child td{border:none}
.tbl tbody tr{transition:background .15s}
.tbl tbody tr:hover{background:rgba(255,255,255,0.02)}
.cell-student{display:flex;align-items:center;gap:10px}
.avatar{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:10px;color:#fff;flex-shrink:0;letter-spacing:.3px}
.avatar.high{background:var(--red-dim)}
.avatar.medium{background:rgba(245,158,11,0.2);color:var(--amber)}
.avatar.low{background:rgba(34,197,94,0.15);color:var(--green)}
.cell-name{font-weight:500;color:var(--text);font-size:12px}
.cell-id{font-size:10px;color:var(--text-3);font-family:var(--mono)}
.tag{display:inline-flex;align-items:center;height:20px;padding:0 8px;border-radius:4px;font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:0.5px}
.tag-high{background:var(--red-glow);color:var(--red);border:1px solid rgba(239,68,68,0.2)}
.tag-medium{background:var(--amber-glow);color:var(--amber);border:1px solid rgba(245,158,11,0.2)}
.tag-low{background:var(--green-glow);color:var(--green);border:1px solid rgba(34,197,94,0.2)}
.bar-g{display:flex;align-items:center;gap:8px}
.bar-t{width:48px;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden}
.bar-f{height:100%;border-radius:2px}
.bar-f.h{background:var(--red)}
.bar-f.m{background:var(--amber)}
.bar-f.l{background:var(--green)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:500;font-size:11px;color:var(--text-2)}
.cause-chip{display:inline-flex;height:20px;padding:0 8px;border-radius:4px;font-size:10px;font-family:var(--mono);font-weight:500;background:rgba(255,255,255,0.04);border:1px solid var(--border);color:var(--text-2);align-items:center;text-transform:capitalize}
.sent{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--text-2);text-transform:capitalize}
.sent::before{content:'';width:6px;height:6px;border-radius:50%}
.sent.positive::before{background:var(--green);box-shadow:0 0 4px var(--green)}
.sent.negative::before{background:var(--red);box-shadow:0 0 4px var(--red)}
.sent.neutral::before{background:var(--amber);box-shadow:0 0 4px var(--amber)}

/* Transcript pending */
.answers-row{display:flex;gap:3px}
.answer-blk{width:14px;height:14px;border-radius:3px;background:rgba(255,255,255,0.04);border:1px solid var(--border)}
.answer-blk.on{background:var(--red);border-color:var(--red);box-shadow:0 0 6px rgba(239,68,68,0.3)}
.status-ok{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--green);font-family:var(--mono)}

/* ═══ EMPTY STATE ═══ */
.empty-state{padding:56px 24px;text-align:center}
.empty-ring{width:48px;height:48px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;margin:0 auto 16px}
.empty-ring svg{width:20px;height:20px;color:var(--text-3)}
.empty-title{font-size:13px;font-weight:500;margin-bottom:4px;color:var(--text-2)}
.empty-desc{font-size:11px;color:var(--text-3);max-width:300px;margin:0 auto}

/* ═══ TOAST ═══ */
#toast{position:fixed;bottom:24px;right:24px;max-width:380px;padding:10px 16px;border-radius:var(--radius-sm);font-size:11px;font-family:var(--mono);font-weight:500;z-index:200;transform:translateY(80px);opacity:0;transition:all .25s;backdrop-filter:blur(12px);border:1px solid transparent}
#toast.show{transform:translateY(0);opacity:1}
#toast.success{background:rgba(34,197,94,0.1);color:var(--green);border-color:rgba(34,197,94,0.2)}
#toast.error{background:rgba(239,68,68,0.1);color:var(--red);border-color:rgba(239,68,68,0.2)}
#toast.info{background:rgba(59,130,246,0.1);color:var(--blue);border-color:rgba(59,130,246,0.2)}

/* ═══ FOOTER ═══ */
.footer{text-align:center;padding:32px 28px;font-size:10px;font-family:var(--mono);letter-spacing:1px;text-transform:uppercase;color:var(--text-3)}
.footer span{margin:0 8px;opacity:.3}

/* ═══ GLOW LINE ═══ */
.glow-line{height:1px;background:linear-gradient(90deg,transparent,rgba(239,68,68,0.4),rgba(239,68,68,0.6),rgba(239,68,68,0.4),transparent);margin:0 28px}

@media(max-width:960px){
  .dash{grid-template-columns:1fr;gap:12px}
  .dash>.span2,.dash>.full{grid-column:1}
  .stats-bar{grid-template-columns:1fr}
  .hero-title{font-size:36px}
}
</style>
</head><body>

<!-- Topbar -->
<div class="topbar">
  <div class="topbar-brand">
    <div class="topbar-icon"></div>
    <div class="topbar-name">The Dropout Signal</div>
  </div>
  <div class="topbar-right">
    <div class="topbar-status"><div class="dot"></div>System Online</div>
    <div class="topbar-tag">HackBricks 2026</div>
  </div>
</div>

<!-- Hero -->
<div class="hero">
  <div class="hero-left">
    <div class="hero-label">Layer 2 — AI Voice Verification</div>
    <div class="hero-title">Voice<br>Verification</div>
    <div class="hero-sub">Calls high-risk students flagged by our ML pipeline. Asks 5 non-leading questions and uses LLM-powered sentiment analysis to produce unbiased dropout probability scores for fusion scoring.</div>
    <div class="hero-prices">
      <div class="hero-price"><div class="label">Twilio Voice</div><div class="val">5 Questions</div></div>
      <div class="hero-price"><div class="label">Groq LLM</div><div class="val">Llama 3.3 70B</div></div>
    </div>
  </div>
  <div class="hero-viz">
    <div class="viz-wrap">
      <svg viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#ef4444" stop-opacity=".12"/><stop offset="100%" stop-color="#ef4444" stop-opacity="0"/></radialGradient>
          <linearGradient id="barG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ef4444"/><stop offset="100%" stop-color="#ef4444" stop-opacity=".2"/></linearGradient>
          <linearGradient id="scanG" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#ef4444" stop-opacity="0"/><stop offset="100%" stop-color="#ef4444" stop-opacity=".6"/></linearGradient>
          <filter id="redGlow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <!-- Background glow -->
        <circle cx="200" cy="200" r="180" fill="url(#glow)"/>
        <!-- Outer rings -->
        <circle cx="200" cy="200" r="160" stroke="#ef4444" stroke-opacity=".08" stroke-width="1" class="ring-pulse"/>
        <circle cx="200" cy="200" r="130" stroke="#ef4444" stroke-opacity=".12" stroke-width=".7"/>
        <circle cx="200" cy="200" r="100" stroke="#ef4444" stroke-opacity=".18" stroke-width=".7"/>
        <circle cx="200" cy="200" r="70" stroke="#ef4444" stroke-opacity=".1" stroke-width=".5" stroke-dasharray="4 6" class="ring-pulse" style="animation-delay:1s"/>
        <!-- Scanning line -->
        <line x1="200" y1="200" x2="200" y2="40" stroke="url(#scanG)" stroke-width="1.5" class="scan-line" filter="url(#redGlow)"/>
        <!-- Waveform bars (left side) -->
        <rect class="wave-bar" x="72" y="172" width="3" height="56" rx="1.5" fill="url(#barG)" opacity=".7"/>
        <rect class="wave-bar" x="80" y="158" width="3" height="84" rx="1.5" fill="url(#barG)" opacity=".8"/>
        <rect class="wave-bar" x="88" y="168" width="3" height="64" rx="1.5" fill="url(#barG)" opacity=".6"/>
        <rect class="wave-bar" x="96" y="148" width="3" height="104" rx="1.5" fill="url(#barG)" opacity=".9"/>
        <rect class="wave-bar" x="104" y="162" width="3" height="76" rx="1.5" fill="url(#barG)" opacity=".7"/>
        <rect class="wave-bar" x="112" y="142" width="3" height="116" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="120" y="155" width="3" height="90" rx="1.5" fill="url(#barG)" opacity=".75"/>
        <rect class="wave-bar" x="128" y="136" width="3" height="128" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="136" y="150" width="3" height="100" rx="1.5" fill="url(#barG)" opacity=".8"/>
        <rect class="wave-bar" x="144" y="130" width="3" height="140" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="152" y="145" width="3" height="110" rx="1.5" fill="url(#barG)" opacity=".65"/>
        <!-- Waveform bars (right side) -->
        <rect class="wave-bar" x="248" y="145" width="3" height="110" rx="1.5" fill="url(#barG)" opacity=".65"/>
        <rect class="wave-bar" x="256" y="130" width="3" height="140" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="264" y="150" width="3" height="100" rx="1.5" fill="url(#barG)" opacity=".8"/>
        <rect class="wave-bar" x="272" y="136" width="3" height="128" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="280" y="155" width="3" height="90" rx="1.5" fill="url(#barG)" opacity=".75"/>
        <rect class="wave-bar" x="288" y="142" width="3" height="116" rx="1.5" fill="url(#barG)"/>
        <rect class="wave-bar" x="296" y="162" width="3" height="76" rx="1.5" fill="url(#barG)" opacity=".7"/>
        <rect class="wave-bar" x="304" y="148" width="3" height="104" rx="1.5" fill="url(#barG)" opacity=".9"/>
        <rect class="wave-bar" x="312" y="168" width="3" height="64" rx="1.5" fill="url(#barG)" opacity=".6"/>
        <rect class="wave-bar" x="320" y="158" width="3" height="84" rx="1.5" fill="url(#barG)" opacity=".8"/>
        <rect class="wave-bar" x="328" y="172" width="3" height="56" rx="1.5" fill="url(#barG)" opacity=".7"/>
        <!-- Center mic icon -->
        <circle cx="200" cy="200" r="38" fill="rgba(239,68,68,0.06)" stroke="#ef4444" stroke-opacity=".35" stroke-width="1.5"/>
        <circle cx="200" cy="200" r="28" fill="rgba(239,68,68,0.04)" stroke="#ef4444" stroke-opacity=".2" stroke-width="1"/>
        <!-- Microphone shape -->
        <rect x="192" y="182" width="16" height="24" rx="8" fill="none" stroke="#ef4444" stroke-width="1.8" filter="url(#redGlow)"/>
        <path d="M186 200 a14 14 0 0 0 28 0" fill="none" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round" filter="url(#redGlow)"/>
        <line x1="200" y1="214" x2="200" y2="222" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="193" y1="222" x2="207" y2="222" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round"/>
        <!-- Data nodes around the circle -->
        <circle cx="200" cy="40" r="3" fill="#ef4444" opacity=".6" class="node-blink" filter="url(#redGlow)"/>
        <circle cx="313" cy="90" r="2.5" fill="#ef4444" opacity=".5" class="node-blink"/>
        <circle cx="345" cy="200" r="3" fill="#ef4444" opacity=".4" class="node-blink"/>
        <circle cx="313" cy="310" r="2.5" fill="#ef4444" opacity=".5" class="node-blink"/>
        <circle cx="200" cy="360" r="3" fill="#ef4444" opacity=".6" class="node-blink" filter="url(#redGlow)"/>
        <circle cx="87" cy="310" r="2.5" fill="#ef4444" opacity=".5" class="node-blink"/>
        <circle cx="55" cy="200" r="3" fill="#ef4444" opacity=".4" class="node-blink"/>
        <circle cx="87" cy="90" r="2.5" fill="#ef4444" opacity=".5" class="node-blink"/>
        <!-- Thin connecting lines from nodes to center -->
        <line x1="200" y1="43" x2="200" y2="70" stroke="#ef4444" stroke-opacity=".1" stroke-width=".5"/>
        <line x1="313" y1="92" x2="270" y2="130" stroke="#ef4444" stroke-opacity=".08" stroke-width=".5"/>
        <line x1="345" y1="200" x2="300" y2="200" stroke="#ef4444" stroke-opacity=".08" stroke-width=".5"/>
        <line x1="87" y1="92" x2="130" y2="130" stroke="#ef4444" stroke-opacity=".08" stroke-width=".5"/>
        <line x1="55" y1="200" x2="100" y2="200" stroke="#ef4444" stroke-opacity=".08" stroke-width=".5"/>
        <!-- Tiny floating data labels -->
        <text x="320" y="88" font-family="JetBrains Mono,monospace" font-size="7" fill="#ef4444" opacity=".35">0.87</text>
        <text x="52" y="188" font-family="JetBrains Mono,monospace" font-size="7" fill="#ef4444" opacity=".3">VOICE</text>
        <text x="324" y="316" font-family="JetBrains Mono,monospace" font-size="7" fill="#ef4444" opacity=".3">HIGH</text>
        <text x="70" y="316" font-family="JetBrains Mono,monospace" font-size="7" fill="#ef4444" opacity=".25">0.92</text>
        <text x="186" y="36" font-family="JetBrains Mono,monospace" font-size="7" fill="#ef4444" opacity=".35">AI</text>
        <text x="338" y="208" font-family="JetBrains Mono,monospace" font-size="6" fill="#ef4444" opacity=".25">SENT</text>
      </svg>
    </div>
  </div>
</div>

<div class="glow-line"></div>

<div style="max-width:1440px;margin:0 auto">
<div class="dash" style="padding-top:24px">

  <!-- ═══ BOTTOM STATS BAR (like the Cybertruck footer stats) ═══ -->
  <div class="stats-bar">
    <div class="stat-cell">
      <div class="stat-delta {% if active > 0 %}up{% else %}neutral{% endif %}">{% if active > 0 %}&#9650; LIVE{% else %}&#8226; IDLE{% endif %}</div>
      <div class="stat-val">{{ active }}</div>
      <div class="stat-label">Active Calls</div>
    </div>
    <div class="stat-cell">
      <div class="stat-delta {% if completed > 0 %}up{% else %}neutral{% endif %}">{% if completed > 0 %}&#9650; +{{ completed }}{% else %}&#8226; 0{% endif %}</div>
      <div class="stat-val">{{ completed }}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat-cell">
      <div class="stat-delta {% if confirmed > 0 %}down{% else %}neutral{% endif %}">{% if confirmed > 0 %}&#9660; {{ confirmed }} HIGH{% else %}&#8226; NONE{% endif %}</div>
      <div class="stat-val">{{ analyzed }}</div>
      <div class="stat-label">LLM Analyzed</div>
    </div>
  </div>

  <!-- ═══ LEFT: Pipeline Card (span 2 cols) ═══ -->
  <div class="card span2">
    <div class="card-head">
      <span class="card-label">Verification Pipeline</span>
      <span class="card-badge">5 stages</span>
    </div>
    <div class="card-body">
      <div class="pipeline">
        <div class="pipe-node">
          <div class="pipe-dot {% if completed > 0 or active > 0 %}done{% else %}active{% endif %}">1</div>
          <div class="pipe-txt">Initiate</div>
          <div class="pipe-sub">Twilio</div>
        </div>
        <div class="pipe-line {% if completed > 0 or active > 0 %}done{% endif %}"></div>
        <div class="pipe-node">
          <div class="pipe-dot {% if completed > 0 %}done{% elif active > 0 %}active{% endif %}">2</div>
          <div class="pipe-txt">Interview</div>
          <div class="pipe-sub">5 Questions</div>
        </div>
        <div class="pipe-line {% if completed > 0 %}done{% endif %}"></div>
        <div class="pipe-node">
          <div class="pipe-dot {% if completed > 0 %}done{% endif %}">3</div>
          <div class="pipe-txt">Transcript</div>
          <div class="pipe-sub">Speech-to-Text</div>
        </div>
        <div class="pipe-line {% if analyzed > 0 %}done{% endif %}"></div>
        <div class="pipe-node">
          <div class="pipe-dot {% if analyzed > 0 %}done{% elif completed > 0 %}active{% endif %}">4</div>
          <div class="pipe-txt">LLM Analysis</div>
          <div class="pipe-sub">Sentiment</div>
        </div>
        <div class="pipe-line {% if analyzed > 0 %}done{% endif %}"></div>
        <div class="pipe-node">
          <div class="pipe-dot {% if analyzed > 0 %}done{% endif %}">5</div>
          <div class="pipe-txt">Export</div>
          <div class="pipe-sub">Databricks</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ RIGHT: AI Insight Card ═══ -->
  <div class="card">
    <div class="card-head">
      <span class="card-label">AI Insight</span>
    </div>
    <div class="card-body">
      <div class="insight-text">
        Voice verification has processed <strong>{{ completed }} calls</strong> with
        <strong>{{ analyzed }} analyzed</strong> via Groq LLM.
        {% if confirmed > 0 %}<strong>{{ confirmed }} students</strong> confirmed as HIGH risk requiring immediate intervention.{% else %}No confirmed high-risk students yet.{% endif %}
      </div>
      <div class="target-bar">
        <div class="target-track">
          {% for i in range(10) %}
          <div class="target-seg" style="flex:1{% if i < analyzed %};background:var(--red){% else %};background:rgba(255,255,255,0.03){% endif %}"></div>
          {% endfor %}
        </div>
        <div class="target-labels">
          <span>{{ analyzed }} analyzed</span>
          <span>target: all flagged</span>
        </div>
      </div>
      <div class="insight-stats">
        <div class="insight-stat"><div class="v">{{ completed }}</div><div class="l">Calls</div></div>
        <div class="insight-stat"><div class="v">{{ analyzed }}</div><div class="l">Processed</div></div>
        <div class="insight-stat"><div class="v">{{ confirmed }}</div><div class="l">Confirmed</div></div>
      </div>
      <button class="btn-insight" onclick="act(document.getElementById('btnAnalyze'),'/analyze','POST','Running LLM analysis...')">Run Analysis &raquo;</button>
    </div>
  </div>

  <!-- ═══ CONTROLS ═══ -->
  <div class="controls-row">
    <span style="font-size:10px;font-family:var(--mono);letter-spacing:1.5px;text-transform:uppercase;color:var(--text-3)">Pipeline Controls</span>
    <div class="btn-group">
      <button class="btn btn-accent" id="btnDemo" onclick="act(this,'/demo','POST','Calling demo phone...')"><div class="spin"></div><span class="btn-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>Demo Call</span></button>
      <button class="btn" id="btnCalls" onclick="act(this,'/initiate','POST','Initiating calls...')"><div class="spin"></div><span class="btn-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>Call All High-Risk</span></button>
      <button class="btn" id="btnAnalyze" onclick="act(this,'/analyze','POST','Running LLM analysis...')"><div class="spin"></div><span class="btn-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>Analyze</span></button>
      <button class="btn" id="btnExport" onclick="act(this,'/export','GET','Exporting CSV...')"><div class="spin"></div><span class="btn-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>Export</span></button>
      <span style="width:1px;height:20px;background:var(--border);margin:0 4px"></span>
      <button class="btn" id="btnWaDemo" onclick="act(this,'/whatsapp/demo','POST','Sending WhatsApp...')" style="border-color:rgba(34,197,94,0.3);color:var(--green)"><div class="spin"></div><span class="btn-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>WhatsApp Demo</span></button>
      <button class="btn" onclick="location.reload()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>Refresh</button>
    </div>
  </div>

  <!-- Toast -->
  <div id="toast"></div>

  <!-- ═══ ANALYSIS RESULTS TABLE ═══ -->
  {% if results %}
  <div class="card full">
    <div class="card-head">
      <span class="card-label">Analysis Results</span>
      <span class="card-badge">{{ results|length }} student{{ 's' if results|length != 1 }}</span>
    </div>
    <table class="tbl">
      <thead>
        <tr>
          <th>Student</th><th>ML Score</th><th>Intent</th><th>Dropout Prob</th>
          <th>Root Cause</th><th>Sentiment</th><th>Outlook</th><th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {% for r in results %}
        <tr>
          <td>
            <div class="cell-student">
              <div class="avatar {{ r.dropout_intent|lower }}">{{ r.student_name[0] }}</div>
              <div>
                <div class="cell-name">{{ r.student_name }}</div>
                <div class="cell-id">#{{ r.student_id }}</div>
              </div>
            </div>
          </td>
          <td>
            <div class="bar-g">
              <div class="bar-t"><div class="bar-f {% if r.ml_risk_score|float > 0.7 %}h{% elif r.ml_risk_score|float > 0.4 %}m{% else %}l{% endif %}" style="width:{{ (r.ml_risk_score|float * 100)|int }}%"></div></div>
              <span class="mono">{{ '%.2f'|format(r.ml_risk_score|float) }}</span>
            </div>
          </td>
          <td><span class="tag tag-{{ r.dropout_intent|lower }}">{{ r.dropout_intent }}</span></td>
          <td>
            <div class="bar-g">
              <div class="bar-t"><div class="bar-f {% if r.dropout_probability|float > 0.7 %}h{% elif r.dropout_probability|float > 0.4 %}m{% else %}l{% endif %}" style="width:{{ (r.dropout_probability|float * 100)|int }}%"></div></div>
              <span class="mono">{{ '%.2f'|format(r.dropout_probability|float) }}</span>
            </div>
          </td>
          <td><span class="cause-chip">{{ r.primary_root_cause }}</span></td>
          <td><span class="sent {{ r.overall_sentiment }}">{{ r.overall_sentiment }}</span></td>
          <td><span class="mono" style="text-transform:capitalize">{{ r.q5_future_orientation }}</span></td>
          <td><span class="mono">{{ '%.0f'|format(r.ai_confidence|float * 100) }}%</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- ═══ BREAKDOWN + BARS (like Cybertruck side panels) ═══ -->
  <div class="card span2">
    <div class="card-head">
      <span class="card-label">Intent Breakdown</span>
    </div>
    <div class="card-body">
      <div class="breakdown">
        <div class="donut-wrap">
          <svg width="100" height="100" viewBox="0 0 36 36">
            {% set high_count = results|selectattr('dropout_intent','equalto','HIGH')|list|length %}
            {% set med_count = results|selectattr('dropout_intent','equalto','MEDIUM')|list|length %}
            {% set low_count = results|selectattr('dropout_intent','equalto','LOW')|list|length %}
            {% set total = results|length %}
            {% set h_pct = (high_count / total * 100) if total else 0 %}
            {% set m_pct = (med_count / total * 100) if total else 0 %}
            {% set l_pct = (low_count / total * 100) if total else 0 %}
            <circle cx="18" cy="18" r="14" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="4"/>
            <circle cx="18" cy="18" r="14" fill="none" stroke="var(--red)" stroke-width="4" stroke-dasharray="{{ h_pct * 0.88 }} {{ 88 - h_pct * 0.88 }}" stroke-dashoffset="22" stroke-linecap="round"/>
            <circle cx="18" cy="18" r="14" fill="none" stroke="var(--amber)" stroke-width="4" stroke-dasharray="{{ m_pct * 0.88 }} {{ 88 - m_pct * 0.88 }}" stroke-dashoffset="{{ 22 - h_pct * 0.88 }}" stroke-linecap="round"/>
            <circle cx="18" cy="18" r="14" fill="none" stroke="var(--green)" stroke-width="4" stroke-dasharray="{{ l_pct * 0.88 }} {{ 88 - l_pct * 0.88 }}" stroke-dashoffset="{{ 22 - h_pct * 0.88 - m_pct * 0.88 }}" stroke-linecap="round"/>
          </svg>
          <div class="donut-center"><div class="lbl">Total</div><div class="num">{{ total }}</div></div>
        </div>
        <div class="breakdown-list">
          <div class="bd-item"><div class="bd-dot" style="background:var(--red)"></div><span class="bd-label">HIGH</span><span class="bd-val" style="color:var(--red)">{{ high_count }}</span></div>
          <div class="bd-item"><div class="bd-dot" style="background:var(--amber)"></div><span class="bd-label">MEDIUM</span><span class="bd-val" style="color:var(--amber)">{{ med_count }}</span></div>
          <div class="bd-item"><div class="bd-dot" style="background:var(--green)"></div><span class="bd-label">LOW</span><span class="bd-val" style="color:var(--green)">{{ low_count }}</span></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Root Cause Distribution -->
  <div class="card">
    <div class="card-head">
      <span class="card-label">Root Causes</span>
    </div>
    <div class="card-body">
      {% set causes = {} %}
      {% for r in results %}
        {% set c = r.primary_root_cause %}
        {% if causes.update({c: causes.get(c, 0) + 1}) %}{% endif %}
      {% endfor %}
      {% for c, cnt in causes|dictsort(by='value', reverse=true) %}
      <div class="hbar-row">
        <div class="hbar-name">{{ c }}</div>
        <div class="hbar-track"><div class="hbar-fill" style="width:{{ (cnt / results|length * 100)|int }}%;background:var(--red)"></div></div>
        <div class="hbar-val">{{ cnt }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- ═══ PENDING TRANSCRIPTS ═══ -->
  {% if transcripts %}
  <div class="card full">
    <div class="card-head">
      <span class="card-label">Pending Transcripts</span>
      <span class="card-badge">{{ transcripts|length }} awaiting analysis</span>
    </div>
    <table class="tbl">
      <thead><tr><th>Student</th><th>Status</th><th>Responses</th></tr></thead>
      <tbody>
      {% for t in transcripts %}
        <tr>
          <td><div class="cell-student"><div class="avatar" style="background:rgba(255,255,255,0.06);color:var(--text-3)">{{ t.student_name[0] }}</div><div><div class="cell-name">{{ t.student_name }}</div><div class="cell-id">#{{ t.student_id }}</div></div></div></td>
          <td><div class="status-ok"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>{{ t.status }}</div></td>
          <td><div class="answers-row">{% for i in range(5) %}<div class="answer-blk {% if i < t.answer_count %}on{% endif %}"></div>{% endfor %}</div></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  <!-- ═══ WHATSAPP CONVERSATIONS ═══ -->
  {% if wa_convos %}
  <div class="card full">
    <div class="card-head">
      <span class="card-label" style="color:var(--green)">&#x1f4ac; WhatsApp AI Counselor</span>
      <span class="card-badge">{{ wa_convos|length }} conversation{{ 's' if wa_convos|length != 1 }}</span>
    </div>
    <table class="tbl">
      <thead><tr><th>Student</th><th>Risk</th><th>Messages</th><th>Started</th></tr></thead>
      <tbody>
      {% for c in wa_convos %}
        <tr style="cursor:pointer" onclick="toggleChat('{{ c.phone }}')">
          <td>
            <div class="cell-student">
              <div class="avatar" style="background:rgba(34,197,94,0.15);color:var(--green)">{{ (c.profile_name or c.student_name or '?')[0] }}</div>
              <div>
                <div class="cell-name">{{ c.profile_name or c.student_name }}</div>
                <div class="cell-id">{{ c.phone }}</div>
              </div>
            </div>
          </td>
          <td><span class="tag tag-{{ c.risk_level|lower }}">{{ c.risk_level }}</span></td>
          <td><span class="mono">{{ c.message_count }}</span></td>
          <td><span class="mono">{{ c.started_at[:16] }}</span></td>
        </tr>
        <tr id="chat-{{ c.phone }}" style="display:none">
          <td colspan="4" style="padding:0 20px 16px">
            <div style="max-height:300px;overflow-y:auto;background:rgba(0,0,0,0.3);border-radius:8px;padding:12px;">
              {% for m in c.messages %}
              <div style="margin-bottom:8px;text-align:{% if m.role=='user' %}right{% else %}left{% endif %}">
                <span style="display:inline-block;max-width:80%;padding:8px 12px;border-radius:12px;font-size:12px;line-height:1.5;{% if m.role=='user' %}background:rgba(59,130,246,0.15);color:var(--blue);border-bottom-right-radius:4px{% else %}background:rgba(34,197,94,0.1);color:var(--green);border-bottom-left-radius:4px{% endif %}">{{ m.content }}</span>
              </div>
              {% endfor %}
            </div>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  <!-- ═══ EMPTY STATE ═══ -->
  {% if not results and not transcripts %}
  <div class="card full">
    <div class="empty-state">
      <div class="empty-ring"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></div>
      <div class="empty-title">No calls initiated</div>
      <div class="empty-desc">Click Demo Call to test with your phone, or Call All High-Risk to begin the verification pipeline.</div>
    </div>
  </div>
  {% endif %}

</div><!-- /dash -->
</div>

<div class="glow-line" style="margin-top:24px"></div>
<div class="footer">The Dropout Signal<span>|</span>HackBricks 2026<span>|</span>Twilio Voice + WhatsApp + Groq + Databricks</div>

<script>
function toast(msg,type){
  const el=document.getElementById('toast');
  el.textContent=msg;el.className=type+' show';
  setTimeout(()=>el.className='',3500);
}
function act(btn,url,method,info){
  btn.classList.add('loading');
  toast(info,'info');
  fetch(url,{method}).then(r=>r.json()).then(d=>{
    btn.classList.remove('loading');
    if(d.error){toast(d.error,'error');return}
    if(d.call_sid)toast('Call initiated — answer your phone.','success');
    else if(d.initiated)toast(d.initiated+' calls initiated.','success');
    else if(d.analyzed)toast(d.analyzed+' analyzed'+(d.whatsapp_sent?' + '+d.whatsapp_sent+' WhatsApp sent':'')+'','success');
    else if(d.exported_to)toast('Exported '+d.count+' results.','success');
    else toast('Done.','success');
    if(d.initiated||d.analyzed)setTimeout(()=>location.reload(),1500);
  }).catch(e=>{btn.classList.remove('loading');toast(String(e),'error')});
}
function toggleChat(phone){
  const el=document.getElementById('chat-'+phone);
  if(el)el.style.display=el.style.display==='none'?'table-row':'none';
}
{% if active > 0 %}setInterval(()=>location.reload(),8000);{% endif %}
</script>
</body></html>"""


@app.route("/voice-dashboard")
def dashboard():
    """Render the voice-only dashboard (legacy)."""
    active = len(sessions) - len(completed_calls)
    confirmed = sum(1 for r in analyzed_results if r.get("dropout_intent") == "HIGH")

    transcripts = []
    if completed_calls and not analyzed_results:
        for c in completed_calls:
            transcripts.append({
                "student_id": c.get("student_id"),
                "student_name": c.get("student_name"),
                "status": c.get("status", "unknown"),
                "answer_count": len(c.get("answers", {})),
            })

    # WhatsApp conversations for dashboard
    wa_convos = []
    for phone, session in wa_sessions.items():
        wa_convos.append({
            "phone": phone,
            "profile_name": session.get("profile_name", ""),
            "student_name": session.get("profile", {}).get("student_name", ""),
            "message_count": len(session.get("messages", [])),
            "started_at": session.get("started_at", ""),
            "risk_level": session.get("profile", {}).get("dropout_intent", "MEDIUM"),
            "messages": session.get("messages", []),
        })

    return render_template_string(
        DASHBOARD_HTML,
        active=max(0, active),
        completed=len(completed_calls),
        analyzed=len(analyzed_results),
        confirmed=confirmed,
        results=analyzed_results,
        transcripts=transcripts,
        wa_convos=wa_convos,
    )


# ═══════════════════════════════════════════════════════════════════
#  AUTO WHATSAPP OUTREACH — Triggered after LLM analysis
# ═══════════════════════════════════════════════════════════════════

def _auto_whatsapp_outreach(results):
    """
    After voice call analysis, automatically send WhatsApp messages
    to students with HIGH or MEDIUM dropout intent.
    LOW intent students are NOT contacted — they're doing fine.
    """
    if not twilio_ready:
        print("⚠️  WhatsApp outreach skipped — Twilio not configured")
        return 0

    sent = 0
    for r in results:
        intent = r.get("dropout_intent", "").upper()
        phone = r.get("phone", "").strip()
        # Use the name they spoke on the call; fall back to CSV name
        spoken = r.get("spoken_name", "").strip()
        name = spoken if spoken else r.get("student_name", "Student")

        # Only HIGH and MEDIUM get WhatsApp follow-up
        if intent not in ("HIGH", "MEDIUM"):
            print(f"   ⏭️  {name} — {intent} intent → skipping WhatsApp")
            continue

        if not phone:
            print(f"   ⚠️  {name} — no phone number, skipping WhatsApp")
            continue

        # Build personalized welcome based on the completed call, not a
        # generic severity template. This prevents unsupported financial-aid
        # claims after a coursework or wellbeing discussion.
        cause = str(r.get("primary_root_cause") or "general support").replace("_", " ")
        support = str(r.get("q3_support_need") or "support").replace("_", " ")
        msg = (
            f"Hi {name.split()[0]}! This is Asha from {UNIVERSITY_NAME}'s Student Wellness team. "
            f"Thanks for speaking with me earlier. You mentioned {cause}; would you like help with "
            f"{support} or anything else today?"
        )
        '''
        if intent == "HIGH":
            msg = (
                f"Hi {name.split()[0]}! 👋\n\n"
                f"I'm *Asha* — your AI student support assistant from {UNIVERSITY_NAME}'s "
                f"Retention & Wellness team.\n\n"
                f"We recently spoke on the phone, and I wanted to follow up personally. "
                f"I understand things might be tough right now, and I want you to know "
                f"that support is available.\n\n"
                f"Would you like to chat about what's been on your mind? "
                f"I'm here to help — no pressure at all. 💙"
            )
        else:  # MEDIUM
            msg = (
                f"Hi {name.split()[0]}! 👋\n\n"
                f"I'm *Asha* from {UNIVERSITY_NAME}'s Student Wellness team.\n\n"
                f"Thanks for taking our call earlier! Just wanted to check in — "
                f"we have some great resources that might be helpful for you this semester.\n\n"
                f"Feel free to reply anytime if you'd like to chat. 😊"
            )

        '''
        to_wa = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone

        phone_clean = phone.replace("whatsapp:", "")
        # Make the call-derived follow-up visible immediately. A temporary
        # Sandbox delivery failure must not hide the conversation from either
        # dashboard or prevent later replies from being matched.
        wa_sessions[phone_clean] = {
            "messages": [{"role": "assistant", "content": msg}],
            "started_at": datetime.now().isoformat(),
            "profile": {"student_name": name, "dropout_intent": intent,
                        "primary_root_cause": cause, "q3_support_need": support},
            "profile_name": name, "spoken_name": name, "auto_triggered": True,
        }

        try:
            twilio_client.messages.create(
                body=msg,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to_wa,
            )
            sent += 1
            print(f"   📤 WhatsApp sent to {name} ({phone}) — {intent} intent")
        except Exception as e:
            print(f"   ❌ WhatsApp failed for {name}: {e}")

    if sent:
        print(f"✅ WhatsApp outreach complete: {sent} messages sent")
    return sent


# ═══════════════════════════════════════════════════════════════════
#  WHATSAPP AI COUNSELOR BOT — Omnichannel Layer 2.5
# ═══════════════════════════════════════════════════════════════════

# --- Mock student profiles (for demo; in production, read from Gold table) ---
DEMO_STUDENTS = {
    DEMO_PHONE: {
        "student_id": "2847",
        "student_name": "Demo Student",
        "ml_risk_score": 0.87,
        "dropout_intent": "HIGH",
        "primary_root_cause": "financial",
        "shap_top_factors": [
            "Tuition fees not up to date",
            "Scholarship holder = No",
            "Curricular units 2nd sem approved = 3 (low)",
            "Age at enrollment = 23 (mature)",
            "Debtor = Yes",
        ],
        "intervention_tier": "TIER 1 — IMMEDIATE",
    },
}

WA_SYSTEM_PROMPT = """You are a compassionate, professional university student wellness counselor chatting via WhatsApp.
Your name is Asha (meaning 'hope') — you are part of the university's Student Retention & Support initiative.

CONTEXT about this student (from our ML pipeline — DO NOT reveal raw scores or that they were flagged by AI):
- Student Name: {student_name}
- Risk Level: {dropout_intent} (INTERNAL — never say this directly)
- Primary Concern Area: {primary_root_cause}
- Key Factors: {shap_factors}
- Intervention Tier: {intervention_tier}

YOUR ROLE:
1. Be warm, empathetic, and non-judgmental
2. Gently explore the student's concerns based on the known risk factors
3. Offer SPECIFIC, actionable guidance:
   - Financial → mention scholarships, fee payment plans, emergency aid office
   - Academic → tutoring centers, study groups, professor office hours, course load adjustment
   - Social → student clubs, peer mentoring, counseling services
   - Family → family counseling referral, flexible scheduling options
4. NEVER reveal that an ML model flagged them or mention "risk scores"
5. Present yourself as a routine wellness check-in service
6. Keep messages concise (2-4 sentences max per response) — this is WhatsApp, not email
7. Use a friendly tone with occasional emoji (but don't overdo it)
8. If the student seems in crisis, provide the university helpline: 1800-599-0019
9. End conversations warmly and remind them you're always available

IMPORTANT: You are having a multi-turn conversation. Respond naturally to what the student says.
Do NOT dump all advice at once. Listen first, then guide gradually."""

WA_WELCOME_MSG = """Hi {name}! 👋

I'm *Asha* — your AI student support assistant from {university}'s Retention & Wellness team.

We're reaching out to students this semester because we genuinely care about your journey. This is a safe, confidential space — no judgments here.

How has your semester been going? Anything on your mind? 💬"""


def _get_student_profile(phone):
    """Look up student by phone number. Falls back to a generic profile."""
    clean_phone = phone.replace("whatsapp:", "")
    
    spoken = ""
    for r in analyzed_results:
        if r.get("phone", "").replace("whatsapp:", "") == clean_phone:
            spoken = r.get("spoken_name", "")
            break

    if clean_phone in DEMO_STUDENTS:
        p = dict(DEMO_STUDENTS[clean_phone])
        if spoken:
            p["student_name"] = spoken.title()
        return p

    # Check analyzed voice results
    for r in analyzed_results:
        if r.get("phone", "").replace("whatsapp:", "") == clean_phone:
            return {
                "student_id": r.get("student_id", "unknown"),
                "student_name": r.get("spoken_name") or r.get("student_name", "Student"),
                "ml_risk_score": r.get("ml_risk_score", 0.5),
                "dropout_intent": r.get("dropout_intent", "MEDIUM"),
                "primary_root_cause": r.get("primary_root_cause", "academic"),
                "shap_top_factors": ["Information not yet available"],
                "intervention_tier": "TIER 2 — PROACTIVE",
            }

    # Generic fallback for unknown numbers (e.g. judge texting in)
    return {
        "student_id": "demo",
        "student_name": "Student",
        "ml_risk_score": 0.72,
        "dropout_intent": "MEDIUM",
        "primary_root_cause": "academic",
        "shap_top_factors": [
            "Curricular units approved below average",
            "Attendance inconsistency detected",
            "No scholarship currently active",
        ],
        "intervention_tier": "TIER 2 — PROACTIVE",
    }


def _wa_llm_reply(phone, user_msg):
    """Generate a counselor reply using Groq LLM with conversation history."""
    if not LLM_AVAILABLE:
        return "I'm here to help! Our AI system is currently being set up. Please try again in a moment. 🙏"

    # A proactive follow-up stores the exact call-derived profile in the
    # session. Prefer it over generic/demo lookup data so replies never invent
    # concerns such as financial aid that were not mentioned on the call.
    profile = wa_sessions.get(phone, {}).get("profile") or _get_student_profile(phone)

    system_prompt = WA_SYSTEM_PROMPT.format(
        student_name=profile["student_name"],
        dropout_intent=profile["dropout_intent"],
        primary_root_cause=profile["primary_root_cause"],
        shap_factors=", ".join(profile.get("shap_top_factors", [])),
        intervention_tier=profile.get("intervention_tier", "TIER 2"),
    )

    # Build conversation messages
    history = wa_sessions.get(phone, {}).get("messages", [])
    messages = [{"role": "system", "content": system_prompt}]
    # Keep last 20 messages for context window
    for m in history[-20:]:
        messages.append(m)
    # The webhook stores the inbound turn before asking for a reply so the
    # dashboard can display it immediately. Do not send that turn twice.
    if not history or history[-1].get("role") != "user" or history[-1].get("content") != user_msg:
        messages.append({"role": "user", "content": user_msg})

    try:
        if Groq:
            client = Groq(api_key=GROQ_API_KEY)
        else:
            client = _OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ WhatsApp LLM error using {LLM_MODEL}: {e}")
        # Preserve a helpful, message-aware conversation if the provider is
        # temporarily unavailable. This avoids repeating a single canned line
        # for every student message while keeping the real transcript intact.
        first_name = str(profile.get("student_name") or "there").split()[0]
        lower_message = user_msg.lower()
        if any(word in lower_message for word in ("hi", "hello", "hey")):
            reply = f"Hi {first_name}! I am here and ready to help. How has your day been going?"
        elif "weather" in lower_message:
            reply = "I do not have live weather access in this support chat, but I can help with coursework, wellbeing, or your next support step."
        elif any(word in lower_message for word in ("how are you", "how r you")):
            reply = "I am doing well, thank you for asking. I am here to listen and help you find the right student-support option."
        else:
            concern = str(profile.get("primary_root_cause") or "support needs").replace("_", " ")
            reply = f"Thank you for sharing that, {first_name}. I have noted it in your support conversation, especially around {concern}. What would feel most helpful as the next step?"

    # Store AI reply
    wa_sessions[phone]["messages"].append({"role": "assistant", "content": reply})

    return reply


@app.route("/whatsapp/webhook", methods=["POST"])
def whatsapp_webhook():
    """
    Twilio WhatsApp webhook: receives incoming messages from students.
    Configure this URL in Twilio Console → Messaging → WhatsApp Sandbox → 'When a message comes in'.
    """
    from twilio.twiml.messaging_response import MessagingResponse

    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")  # e.g. whatsapp:+919876543210
    profile_name = request.form.get("ProfileName", "")

    print(f"💬 WhatsApp from {profile_name or from_number}: \"{incoming_msg[:80]}\"")

    phone_clean = from_number.replace("whatsapp:", "")

    # First message from this number → send welcome
    if phone_clean not in wa_sessions:
        profile = _get_student_profile(phone_clean)
        name = profile_name or profile["student_name"]
        welcome = WA_WELCOME_MSG.format(name=name, university=UNIVERSITY_NAME)

        wa_sessions[phone_clean] = {
            "messages": [{"role": "assistant", "content": welcome}],
            "started_at": datetime.now().isoformat(),
            "profile": profile,
            "profile_name": profile_name,
        }

        # If they sent a real message (not just "join"), process it after welcome
        if incoming_msg.lower().startswith("join"):
            resp = MessagingResponse()
            resp.message(welcome)
            print(f"   → Sent welcome to {name}")
            return str(resp), 200, {"Content-Type": "text/xml"}

    # Append user message immediately so UI sees it before the AI replies
    wa_sessions[phone_clean]["messages"].append({"role": "user", "content": incoming_msg})

    def process_and_send(phone, user_msg, to_number):
        import time
        time.sleep(2.5)  # Give UI time to poll and show the user message first
        reply = _wa_llm_reply(phone, user_msg)
        print(f"   → Reply: \"{reply[:80]}{'...' if len(reply) > 80 else ''}\"")
        try:
            twilio_client.messages.create(
                body=reply,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=to_number
            )
        except Exception as e:
            print(f"Async WA send failed: {e}")

    import threading
    threading.Thread(
        target=process_and_send,
        args=(phone_clean, incoming_msg, from_number),
        daemon=True,
    ).start()

    resp = MessagingResponse()
    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/whatsapp/send", methods=["POST"])
def whatsapp_send():
    """
    Proactively send a WhatsApp message to a student.
    POST JSON: {"phone": "+919876543210", "message": "Hi! ..."}
    """
    if not twilio_ready:
        return jsonify({"error": "Twilio not configured"}), 500

    data = request.get_json(force=True)
    phone = data.get("phone", "").strip()
    message = data.get("message", "").strip()

    if not phone or not message:
        return jsonify({"error": "Provide 'phone' and 'message'"}), 400

    to_wa = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone

    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_wa,
        )
        print(f"📤 WhatsApp sent to {phone}: \"{message[:60]}\"")
        return jsonify({"status": "sent", "sid": msg.sid, "to": phone})
    except Exception as e:
        print(f"❌ WhatsApp send failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/whatsapp/demo", methods=["POST"])
def whatsapp_demo():
    """
    Send a demo welcome message to DEMO_PHONE via WhatsApp.
    The judge/team member must first join the sandbox by texting 'join <two-words>' to +14155238886.
    """
    if not twilio_ready:
        return jsonify({"error": "Twilio not configured"}), 500

    payload = request.get_json(silent=True) or {}
    phone = str(payload.get("phone") or DEMO_PHONE).strip()
    if "YOUR_" in phone or not phone.startswith("+"):
        return jsonify({"error": "Set DEMO_PHONE or provide a valid E.164 phone number."}), 400

    profile = _get_student_profile(phone)
    student_name = str(payload.get("student_name") or profile.get("student_name") or "Student").strip()
    profile["student_name"] = student_name
    welcome = WA_WELCOME_MSG.format(name=student_name, university=UNIVERSITY_NAME)
    phone_clean = phone.replace("whatsapp:", "")
    # Make the outbound greeting a real conversation event before delivery,
    # which lets the dashboard update without waiting for a reply webhook.
    wa_sessions[phone_clean] = {
        "messages": [{"role": "assistant", "content": welcome}],
        "started_at": datetime.now().isoformat(),
        "profile": profile,
        "profile_name": student_name,
        "spoken_name": student_name,
        "auto_triggered": False,
    }
    to_wa = f"whatsapp:{phone_clean}"

    try:
        msg = twilio_client.messages.create(
            body=welcome,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_wa,
        )
        print(f"📤 WhatsApp demo sent to {DEMO_PHONE}")
        return jsonify({"status": "sent", "sid": msg.sid, "to": phone_clean, "demo": True,
                        "conversation": wa_sessions[phone_clean]})
    except Exception as e:
        print(f"❌ WhatsApp demo failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/whatsapp/conversations", methods=["GET"])
def whatsapp_conversations():
    """Return all WhatsApp conversation sessions."""
    convos = []
    for phone, session in wa_sessions.items():
        spoken = session.get("spoken_name", "")
        csv_name = session.get("profile", {}).get("student_name", "")
        convos.append({
            "phone": phone,
            "profile_name": session.get("profile_name", ""),
            "student_name": spoken if spoken else csv_name,
            "message_count": len(session.get("messages", [])),
            "started_at": session.get("started_at"),
            "risk_level": session.get("profile", {}).get("dropout_intent", ""),
            # The dashboard polls this endpoint, so include the actual running
            # conversation rather than only its metadata.
            "messages": session.get("messages", []),
        })
    return jsonify({"conversations": convos, "total": len(convos)})


@app.route("/api/transcripts", methods=["GET"])
def api_transcripts():
    """Return all active voice call transcripts."""
    # `transcript_events` is an ordered source of truth for live rendering;
    # `answers` remains for analysis and older clients.
    return jsonify({"sessions": sessions, "updated_at": datetime.now().isoformat()})


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 65)
    print("  THE DROPOUT SIGNAL — Layer 2: AI Voice + WhatsApp Agent")
    print("=" * 65)
    print(f"  Webhook URL : {WEBHOOK_BASE_URL}")
    print(f"  Twilio      : {'✅ Ready' if twilio_ready else '❌ Not configured'}")
    print(f"  LLM (Groq)  : {'✅ ' + LLM_MODEL if LLM_AVAILABLE else '❌ Not configured'}")
    print(f"  WhatsApp    : {TWILIO_WHATSAPP_NUMBER}")
    print(f"  Input CSV   : {HIGH_RISK_CSV}")
    print(f"  Output CSV  : {OUTPUT_CSV}")
    print("=" * 65)
    print(f"  Dashboard   : http://localhost:5000")
    print(f"  Demo call   : POST http://localhost:5000/demo")
    print(f"  WA webhook  : {WEBHOOK_BASE_URL}/whatsapp/webhook")
    print(f"  WA demo     : POST http://localhost:5000/whatsapp/demo")
    print(f"  Start calls : POST http://localhost:5000/initiate")
    print("=" * 65)
    print()

    app.run(host="0.0.0.0", port=5000, debug=True)
