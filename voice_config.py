"""
THE DROPOUT SIGNAL — Layer 2 Configuration
============================================
Update ALL values below before running voice_server.py

Setup:
  1. pip install -r requirements_layer2.txt
  2. Update credentials below
  3. Run: python voice_server.py
  4. In another terminal: ngrok http 5000
  5. Copy the ngrok HTTPS URL → paste into WEBHOOK_BASE_URL below
  6. Restart voice_server.py
  7. Open http://localhost:5000 → click "Start Calls"
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ─── Twilio Credentials ─────────────────────────────────────────────
# Get from: https://console.twilio.com/
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# ─── Webhook URL (ngrok) ────────────────────────────────────────────
# Run: ngrok http 5000 → copy the https://xxxx.ngrok-free.app URL
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")

# ─── Groq (for transcript analysis) ─────────────────────────────────
# Get from: https://console.groq.com/keys  (FREE tier available)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Groq retired llama-3.3-70b-versatile on 16 August 2026. This remains
# configurable, while deployments use its supported replacement by default.
LLM_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# ─── Voice Settings ─────────────────────────────────────────────────
# Keep the voice/language pair valid. The former Alice + en-IN combination
# can fail or sound fragmented because Alice is not an Indian-English voice.
# Every value remains configurable for another deployment.
TWILIO_VOICE = os.getenv("TWILIO_VOICE", "Polly.Aditi")
TWILIO_LANGUAGE = os.getenv("TWILIO_LANGUAGE", "en-IN")
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "en-IN")
# Let Twilio select and fail over between speech providers by default. The old
# phone_call model does not support en-IN, and explicitly selecting a model
# also forbids speechTimeout="auto".
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "").strip()
SPEECH_TIMEOUT_SECONDS = os.getenv("SPEECH_TIMEOUT_SECONDS", "auto").strip()

# ─── University Name (used in call greeting) ────────────────────────
UNIVERSITY_NAME = "Your University"

# ─── File Paths ─────────────────────────────────────────────────────
HIGH_RISK_CSV = "high_risk_students.csv"   # Input: exported from Gold table
OUTPUT_CSV    = "voice_feedback.csv"       # Output: upload to Databricks

# ─── WhatsApp Sandbox ────────────────────────────────────────────────
# Twilio WhatsApp Sandbox number (free, no approval needed)
# Join sandbox: send "join <two-words>" to this number on WhatsApp
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"

# ─── Demo Mode ──────────────────────────────────────────────────────
# For live demo at hackathon — calls YOUR phone with a fake student
DEMO_PHONE = os.getenv("DEMO_PHONE", "")               # Team member's phone number

# ─── Databricks Connection ───────────────────────────────────────────
DATABRICKS_HOST  = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
DATABRICKS_WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
DATABRICKS_CATALOG = "workspace"
DATABRICKS_SCHEMA  = "default"
