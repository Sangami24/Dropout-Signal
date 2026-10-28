"""
FloraMind — Live Demo Orchestrator
=====================================
Run this ONCE in front of the judges. It shows a dramatic 3-minute
real-time escalation from NORMAL → WARNING → CRITICAL, uploads
each reading to Databricks, and ends with a Twilio phone call
to the farmer.

    ┌──────────────────────────────────────────────────────┐
    │  Phase 1 (0:00 – 0:40)   NORMAL     — Plant is fine │
    │  Phase 2 (0:40 – 1:40)   WARNING    — Stress rising │
    │  Phase 3 (1:40 – 2:30)   CRITICAL   — Drought!      │
    │  Phase 4 (2:30 – 3:00)   📞 CALL    — Farmer alerted│
    └──────────────────────────────────────────────────────┘

Usage:
    python demo_live.py                 # full demo (uploads + call)
    python demo_live.py --dry-run       # terminal animation only, no uploads/call
    python demo_live.py --skip-call     # upload to Databricks but skip phone call
    python demo_live.py --fast          # 90-second version (shorter pauses)

Env vars required:
    DATABRICKS_HOST, DATABRICKS_TOKEN,
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, FARMER_PHONE_NUMBER
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

# Fix Windows console encoding for Unicode/emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.system("")  # enable ANSI escape codes on Windows

import requests
from twilio.rest import Client

# ══════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════

DATABRICKS_HOST  = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
UC_VOLUME_PATH   = os.environ.get(
    "UC_VOLUME_PATH", "/Volumes/workspace/default/floramind_raw/iot_stream"
)

TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
FARMER_PHONE_NUMBER = os.environ.get("FARMER_PHONE_NUMBER", "")

# Plant we're "monitoring" — a tomato on the table
SENSOR_ID    = "MIC-001"
SECTOR       = "A1"
SPECIES      = "solanum_lycopersicum"
SPECIES_NAME = "Tomato"


# ══════════════════════════════════════════════════════════════════════
# DEMO PHASES — biologically calibrated to Khait et al. 2023
# ══════════════════════════════════════════════════════════════════════

def generate_phases(fast: bool = False):
    """
    Return a list of readings that escalate from NORMAL → WARNING → CRITICAL.
    Each reading dict contains sensor values + a phase label.
    """
    tick = 3 if fast else 5  # seconds between readings

    readings = []

    # ── Phase 1: NORMAL (healthy plant, high moisture) ───────────────
    phase1_count = 6 if fast else 8
    for i in range(phase1_count):
        moisture = round(random.uniform(58, 72), 1)
        amplitude = round(random.uniform(0.01, 0.08), 4)
        frequency = round(random.uniform(20, 30), 1)  # low background noise
        duration = round(random.uniform(0.05, 0.15), 3)
        clicks = random.randint(0, 3)
        readings.append({
            "phase": "NORMAL",
            "moisture": moisture,
            "amplitude": amplitude,
            "frequency": frequency,
            "duration": duration,
            "clicks": clicks,
            "tick": tick,
        })

    # ── Phase 2: WARNING (moisture dropping, clicks increasing) ──────
    phase2_count = 10 if fast else 12
    for i in range(phase2_count):
        progress = i / phase2_count  # 0.0 → 1.0
        moisture = round(55 - progress * 30 + random.uniform(-2, 2), 1)
        moisture = max(moisture, 18)
        amplitude = round(0.1 + progress * 0.45 + random.uniform(-0.03, 0.03), 4)
        frequency = round(35 + progress * 25 + random.uniform(-3, 3), 1)
        duration = round(0.15 + progress * 0.3 + random.uniform(-0.02, 0.02), 3)
        clicks = random.randint(5 + int(progress * 15), 10 + int(progress * 25))
        readings.append({
            "phase": "WARNING",
            "moisture": moisture,
            "amplitude": amplitude,
            "frequency": frequency,
            "duration": duration,
            "clicks": clicks,
            "tick": tick,
        })

    # ── Phase 3: CRITICAL (severe drought, loud screaming) ───────────
    phase3_count = 8 if fast else 10
    for i in range(phase3_count):
        progress = i / phase3_count
        moisture = round(15 - progress * 10 + random.uniform(-1, 1), 1)
        moisture = max(moisture, 3.0)
        amplitude = round(0.7 + progress * 0.25 + random.uniform(-0.02, 0.02), 4)
        frequency = round(55 + progress * 15 + random.uniform(-2, 2), 1)
        duration = round(0.4 + progress * 0.2 + random.uniform(-0.02, 0.02), 3)
        clicks = random.randint(25 + int(progress * 15), 35 + int(progress * 15))
        readings.append({
            "phase": "CRITICAL",
            "moisture": moisture,
            "amplitude": amplitude,
            "frequency": frequency,
            "duration": duration,
            "clicks": clicks,
            "tick": tick,
        })

    return readings


# ══════════════════════════════════════════════════════════════════════
# DATABRICKS UPLOAD
# ══════════════════════════════════════════════════════════════════════

def upload_reading(session: requests.Session, reading: dict) -> bool:
    """Upload a single reading to Databricks Unity Catalog Volume."""
    payload = {
        "batch_id": str(uuid.uuid4()),
        "edge_ts": datetime.now(timezone.utc).isoformat(),
        "device_count": 1,
        "readings": [{
            "sensor_id": SENSOR_ID,
            "capture_ts": datetime.now(timezone.utc).isoformat(),
            "peak_frequency_hz": reading["frequency"] * 1000,  # kHz → Hz
            "duration_sec": reading["duration"],
            "amplitude": reading["amplitude"],
            "plant_species": SPECIES,
            "soil_moisture_pct": reading["moisture"],
            "sector": SECTOR,
            "stress_label": reading["phase"],
        }],
    }

    batch_id = payload["batch_id"]
    file_path = f"{UC_VOLUME_PATH.strip('/')}/{batch_id}.json"
    url = f"{DATABRICKS_HOST.rstrip('/')}/api/2.0/fs/files/{file_path}"

    try:
        resp = session.put(
            url,
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {DATABRICKS_TOKEN}",
                "Content-Type": "application/octet-stream",
            },
            timeout=15,
        )
        return resp.status_code in range(200, 300)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# TWILIO EMERGENCY CALL
# ══════════════════════════════════════════════════════════════════════

def trigger_emergency_call(last_reading: dict) -> bool:
    """Place a Twilio voice call with the final CRITICAL alert."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, FARMER_PHONE_NUMBER]):
        print("  ⚠  Twilio not configured — skipping phone call")
        return False

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Pause length="1"/>
  <Say voice="Polly.Aditi" language="en-IN">
    FloraMind Emergency Alert.
  </Say>
  <Pause length="1"/>
  <Say voice="Polly.Aditi" language="en-IN">
    CRITICAL drought stress detected on your {SPECIES_NAME} crop.
    Sensor {SENSOR_ID} in Sector {SECTOR}.
    Soil moisture has dropped to {last_reading['moisture']} percent.
    Acoustic amplitude is {last_reading['amplitude']}, indicating severe xylem cavitation.
    Your plant is screaming for water.
    Please irrigate Sector {SECTOR} immediately.
  </Say>
  <Pause length="1"/>
  <Say voice="Polly.Aditi" language="en-IN">
    This was a FloraMind automated emergency alert. Stay safe.
  </Say>
</Response>"""

    call = client.calls.create(
        to=FARMER_PHONE_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        twiml=twiml,
    )
    return True


# ══════════════════════════════════════════════════════════════════════
# TERMINAL UI — the show for the judges
# ══════════════════════════════════════════════════════════════════════

PHASE_COLORS = {
    "NORMAL":   "\033[92m",  # green
    "WARNING":  "\033[93m",  # yellow
    "CRITICAL": "\033[91m",  # red
}
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    """Print the FloraMind banner."""
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🌱  F L O R A M I N D  —  Live Sensor Feed                    ║
║       Ultrasonic Plant Stress Monitoring System                  ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Sensor: {SENSOR_ID}  │  Sector: {SECTOR}  │  Crop: {SPECIES_NAME:<11}  │  Live  ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
""")


def moisture_bar(pct: float) -> str:
    """Render a visual moisture bar."""
    bar_len = 30
    filled = int(pct / 100 * bar_len)
    filled = max(0, min(filled, bar_len))
    if pct > 50:
        color = "\033[94m"  # blue
    elif pct > 25:
        color = "\033[93m"  # yellow
    else:
        color = "\033[91m"  # red
    bar = f"{color}{'█' * filled}{DIM}{'░' * (bar_len - filled)}{RESET}"
    return bar


def amplitude_viz(amp: float) -> str:
    """Render an amplitude waveform."""
    bars = "▁▂▃▄▅▆▇█"
    level = min(int(amp / 1.0 * len(bars)), len(bars) - 1)
    level = max(0, level)
    wave = ""
    for _ in range(20):
        idx = min(max(0, level + random.randint(-1, 1)), len(bars) - 1)
        wave += bars[idx]
    return wave


def print_reading(idx: int, total: int, reading: dict, uploaded: bool, elapsed: float):
    """Print a single reading with live UI."""
    phase = reading["phase"]
    color = PHASE_COLORS[phase]

    status_icon = {
        "NORMAL": "🟢",
        "WARNING": "🟡",
        "CRITICAL": "🔴",
    }[phase]

    upload_status = "☁️  → Databricks" if uploaded else "💾 Local only"

    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60

    print(f"  {DIM}Reading {idx + 1}/{total}  │  Time: {minutes}:{seconds:02d}{RESET}")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  {BOLD}Status:{RESET}    {color}{status_icon} {phase}{RESET}")
    print(f"  {BOLD}Moisture:{RESET}  {moisture_bar(reading['moisture'])} {reading['moisture']}%")
    print(f"  {BOLD}Amplitude:{RESET} {color}{amplitude_viz(reading['amplitude'])}{RESET} {reading['amplitude']}")
    print(f"  {BOLD}Frequency:{RESET} {reading['frequency']} kHz")
    print(f"  {BOLD}Duration:{RESET}  {reading['duration']} sec")
    print(f"  {BOLD}Clicks/m:{RESET}  {'🔊' * min(reading['clicks'] // 5, 10)} ({reading['clicks']})")
    print(f"  {BOLD}Upload:{RESET}    {upload_status}")
    print()


def print_phase_transition(old_phase: str, new_phase: str):
    """Show a dramatic phase transition banner."""
    color = PHASE_COLORS[new_phase]
    if new_phase == "WARNING":
        print(f"""
{color}{BOLD}  ╔════════════════════════════════════════════════════════╗
  ║   ⚠️   STRESS DETECTED — Moisture Dropping Rapidly    ║
  ║        Plant acoustic emissions are INCREASING         ║
  ╚════════════════════════════════════════════════════════╝{RESET}
""")
    elif new_phase == "CRITICAL":
        print(f"""
{color}{BOLD}  ╔════════════════════════════════════════════════════════╗
  ║   🚨  CRITICAL DROUGHT STRESS — PLANT IS SCREAMING    ║
  ║       Xylem cavitation detected! Immediate action!     ║
  ╚════════════════════════════════════════════════════════╝{RESET}
""")
    time.sleep(2)


def print_call_sequence():
    """Dramatic phone call animation."""
    print(f"""
{BOLD}\033[91m  ╔════════════════════════════════════════════════════════╗
  ║                                                        ║
  ║   📞  TRIGGERING EMERGENCY ALERT TO FARMER...          ║
  ║                                                        ║
  ╚════════════════════════════════════════════════════════╝{RESET}
""")
    frames = ["📞 Connecting", "📞 Connecting.", "📞 Connecting..", "📞 Connecting..."]
    for i in range(8):
        print(f"\r  {frames[i % len(frames)]}   ", end="", flush=True)
        time.sleep(0.5)
    print()
    print(f"""
{BOLD}\033[92m  ╔════════════════════════════════════════════════════════╗
  ║                                                        ║
  ║   ✅  CALL PLACED — Farmer's phone is ringing!         ║
  ║       "Your tomato crop needs water immediately"       ║
  ║                                                        ║
  ╚════════════════════════════════════════════════════════╝{RESET}
""")


def print_summary(readings: list[dict], uploaded_count: int, elapsed: float):
    """Final summary after demo."""
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60

    normal_count = sum(1 for r in readings if r["phase"] == "NORMAL")
    warning_count = sum(1 for r in readings if r["phase"] == "WARNING")
    critical_count = sum(1 for r in readings if r["phase"] == "CRITICAL")

    first_moisture = readings[0]["moisture"]
    last_moisture = readings[-1]["moisture"]

    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════════════╗
║                    DEMO COMPLETE — SUMMARY                       ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Duration:        {minutes}:{seconds:02d}                                          ║
║  Total Readings:  {len(readings):<5}                                        ║
║  Uploaded:        {uploaded_count:<5} to Databricks                          ║
║                                                                  ║
║  🟢 NORMAL:    {normal_count:<4} readings  │  Moisture: {first_moisture:.0f}% → stable        ║
║  🟡 WARNING:   {warning_count:<4} readings  │  Moisture dropping rapidly         ║
║  🔴 CRITICAL:  {critical_count:<4} readings  │  Moisture: {last_moisture:.0f}% — plant screaming  ║
║                                                                  ║
║  Pipeline: IoT Sensor → Databricks → ML Model → Phone Call      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
""")


# ══════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FloraMind Live Demo Orchestrator")
    parser.add_argument("--dry-run", action="store_true",
                        help="Terminal animation only — no uploads, no call")
    parser.add_argument("--skip-call", action="store_true",
                        help="Upload to Databricks but skip the phone call")
    parser.add_argument("--fast", action="store_true",
                        help="90-second version (shorter pauses)")
    args = parser.parse_args()

    readings = generate_phases(fast=args.fast)

    # Build HTTP session for Databricks uploads
    session = None
    if not args.dry_run and DATABRICKS_HOST and DATABRICKS_TOKEN:
        session = requests.Session()

    clear_screen()
    print_header()
    print(f"  {DIM}Initializing sensors...{RESET}")
    time.sleep(2)

    current_phase = None
    uploaded_count = 0
    start_time = time.time()

    for i, reading in enumerate(readings):
        elapsed = time.time() - start_time

        # ── Phase transition banner ──────────────────────────────────
        if reading["phase"] != current_phase:
            if current_phase is not None:
                print_phase_transition(current_phase, reading["phase"])
            current_phase = reading["phase"]

        # ── Upload to Databricks ─────────────────────────────────────
        uploaded = False
        if session and not args.dry_run:
            uploaded = upload_reading(session, reading)
            if uploaded:
                uploaded_count += 1

        # ── Display reading ──────────────────────────────────────────
        print_reading(i, len(readings), reading, uploaded, elapsed)

        # ── Wait between readings ────────────────────────────────────
        time.sleep(reading["tick"])

    elapsed = time.time() - start_time

    # ── Phase 4: TRIGGER THE CALL ────────────────────────────────────
    if not args.dry_run and not args.skip_call:
        print_call_sequence()
        last_critical = [r for r in readings if r["phase"] == "CRITICAL"][-1]
        call_ok = trigger_emergency_call(last_critical)
        if call_ok:
            print(f"  {BOLD}\033[92m✓ Call placed to {FARMER_PHONE_NUMBER}{RESET}")
        else:
            print(f"  {BOLD}\033[93m⚠ Call skipped (Twilio not configured){RESET}")
    elif args.skip_call:
        print(f"\n  {DIM}--skip-call: Phone call skipped{RESET}")
    else:
        print(f"\n  {DIM}--dry-run: No uploads or calls made{RESET}")

    # ── Summary ──────────────────────────────────────────────────────
    print_summary(readings, uploaded_count, elapsed)

    if session:
        session.close()


if __name__ == "__main__":
    main()
