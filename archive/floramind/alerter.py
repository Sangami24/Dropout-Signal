"""
FloraMind — Smart Alert System
================================
Queries the Databricks floramind_predictions table for CRITICAL drought
stress alerts and calls the farmer via Twilio voice call.

The farmer's phone rings with a clear spoken message:
  "FloraMind Alert: Sensor MIC-001 in Sector A1 detected CRITICAL
   drought stress on your tomato crop. Soil moisture at 8 percent.
   Irrigate immediately."

Usage:
    python alerter.py                # query Databricks + call farmer
    python alerter.py --demo         # demo mode (skip Databricks, use sample alert)
    python alerter.py --sms-only     # send SMS instead of voice call

Env vars required:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER,
    FARMER_PHONE_NUMBER, DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests
from twilio.rest import Client

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("floramind.alerter")


# ══════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════

TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
FARMER_PHONE_NUMBER = os.environ.get("FARMER_PHONE_NUMBER", "")

DATABRICKS_HOST  = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")

# Species display names (Latin → common)
SPECIES_NAMES = {
    "solanum_lycopersicum": "tomato",
    "nicotiana_tabacum": "tobacco",
    "zea_mays": "maize",
    "triticum_aestivum": "wheat",
    "oryza_sativa": "rice",
}


# ══════════════════════════════════════════════════════════════════════
# DATABRICKS SQL QUERY
# ══════════════════════════════════════════════════════════════════════

CRITICAL_ALERTS_SQL = """
SELECT
    sensor_id,
    sector,
    plant_species,
    ROUND(AVG(soil_moisture_pct), 1)   AS avg_moisture,
    ROUND(AVG(amplitude), 3)           AS avg_amplitude,
    ROUND(AVG(peak_frequency_khz), 1)  AS avg_frequency,
    COUNT(*)                            AS alert_count,
    MAX(event_ts)                       AS latest_event
FROM floramind_predictions
WHERE predicted_stress = 'CRITICAL'
GROUP BY sensor_id, sector, plant_species
ORDER BY avg_moisture ASC
LIMIT 10
"""


def query_databricks(sql: str) -> list[dict]:
    """Execute SQL via Databricks Statement Execution API and return rows as dicts."""
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        log.error("DATABRICKS_HOST and DATABRICKS_TOKEN must be set")
        sys.exit(1)

    url = f"{DATABRICKS_HOST.rstrip('/')}/api/2.0/sql/statements"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "statement": sql,
        "warehouse_id": None,  # will use serverless
        "wait_timeout": "30s",
        "on_wait_timeout": "CANCEL",
        "catalog": "workspace",
        "schema": "default",
    }

    # Find a SQL warehouse to use
    wh_url = f"{DATABRICKS_HOST.rstrip('/')}/api/2.0/sql/warehouses"
    wh_resp = requests.get(wh_url, headers=headers, timeout=30)
    warehouses = wh_resp.json().get("warehouses", [])
    if not warehouses:
        log.error("No SQL warehouse found. Create one in Databricks first.")
        log.error("For demo, use: python alerter.py --demo")
        sys.exit(1)

    payload["warehouse_id"] = warehouses[0]["id"]
    log.info(f"Using warehouse: {warehouses[0]['name']} ({warehouses[0]['id']})")

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    status = result.get("status", {}).get("state", "UNKNOWN")
    if status != "SUCCEEDED":
        log.error(f"Query failed with status: {status}")
        log.error(result.get("status", {}).get("error", {}))
        return []

    # Parse result into list of dicts
    columns = [col["name"] for col in result["manifest"]["schema"]["columns"]]
    rows = []
    for data_chunk in result.get("result", {}).get("data_array", []):
        rows.append(dict(zip(columns, data_chunk)))

    return rows


# ══════════════════════════════════════════════════════════════════════
# TWILIO VOICE CALL
# ══════════════════════════════════════════════════════════════════════

def build_twiml_message(alerts: list[dict]) -> str:
    """Build TwiML XML for a voice call with spoken alert message."""
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<Response>")
    lines.append("  <Pause length=\"1\"/>")
    lines.append("  <Say voice=\"Polly.Aditi\" language=\"en-IN\">")
    lines.append("    FloraMind Drought Alert System.")
    lines.append("  </Say>")
    lines.append("  <Pause length=\"1\"/>")

    for alert in alerts:
        species = SPECIES_NAMES.get(alert["plant_species"], alert["plant_species"])
        moisture = alert["avg_moisture"]
        sensor = alert["sensor_id"]
        sector = alert["sector"]
        count = alert["alert_count"]

        lines.append("  <Say voice=\"Polly.Aditi\" language=\"en-IN\">")
        lines.append(
            f"    CRITICAL alert. Sensor {sensor} in Sector {sector}. "
            f"Your {species} crop is under severe drought stress. "
            f"Soil moisture is at {moisture} percent. "
            f"{count} critical readings detected. "
            f"Please irrigate sector {sector} immediately."
        )
        lines.append("  </Say>")
        lines.append("  <Pause length=\"1\"/>")

    lines.append("  <Say voice=\"Polly.Aditi\" language=\"en-IN\">")
    lines.append("    This was a FloraMind automated alert. Stay safe, and take care of your crops.")
    lines.append("  </Say>")
    lines.append("</Response>")

    return "\n".join(lines)


def make_voice_call(alerts: list[dict]) -> None:
    """Place a Twilio voice call to the farmer with spoken alerts."""
    _validate_twilio_config()
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    twiml = build_twiml_message(alerts)
    log.info(f"Calling farmer at {FARMER_PHONE_NUMBER}...")

    call = client.calls.create(
        to=FARMER_PHONE_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        twiml=twiml,
    )

    log.info(f"Call initiated! SID: {call.sid}")
    log.info(f"Call status: {call.status}")
    print()
    print("=" * 60)
    print("  PHONE CALL TRIGGERED")
    print("=" * 60)
    print(f"  To:     {FARMER_PHONE_NUMBER}")
    print(f"  From:   {TWILIO_PHONE_NUMBER}")
    print(f"  SID:    {call.sid}")
    print(f"  Status: {call.status}")
    print(f"  Alerts: {len(alerts)} critical sensor(s)")
    print("=" * 60)
    print()
    print("  Your phone should ring in a few seconds...")
    print("  Pick up to hear the FloraMind alert message!")
    print()


def send_sms(alerts: list[dict]) -> None:
    """Send an SMS alert to the farmer."""
    _validate_twilio_config()
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    body_lines = ["🌱 FLORAMIND DROUGHT ALERT\n"]
    for alert in alerts:
        species = SPECIES_NAMES.get(alert["plant_species"], alert["plant_species"])
        body_lines.append(
            f"🔴 CRITICAL: {alert['sensor_id']} ({alert['sector']})\n"
            f"   Crop: {species}\n"
            f"   Moisture: {alert['avg_moisture']}%\n"
            f"   Readings: {alert['alert_count']}\n"
        )
    body_lines.append("⚡ Irrigate immediately!")

    message = client.messages.create(
        to=FARMER_PHONE_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        body="\n".join(body_lines),
    )

    log.info(f"SMS sent! SID: {message.sid}")
    print(f"\n  SMS sent to {FARMER_PHONE_NUMBER} ({message.sid})")


def _validate_twilio_config():
    """Check all Twilio env vars are set."""
    missing = []
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_PHONE_NUMBER:
        missing.append("TWILIO_PHONE_NUMBER")
    if not FARMER_PHONE_NUMBER:
        missing.append("FARMER_PHONE_NUMBER")
    if missing:
        log.error(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# DEMO MODE (no Databricks needed)
# ══════════════════════════════════════════════════════════════════════

DEMO_ALERTS = [
    {
        "sensor_id": "MIC-001",
        "sector": "A1",
        "plant_species": "solanum_lycopersicum",
        "avg_moisture": "8.2",
        "avg_amplitude": "0.891",
        "avg_frequency": "67.3",
        "alert_count": "47",
        "latest_event": "2026-04-05T14:23:00Z",
    },
    {
        "sensor_id": "MIC-003",
        "sector": "B1",
        "plant_species": "zea_mays",
        "avg_moisture": "11.5",
        "avg_amplitude": "0.764",
        "avg_frequency": "62.1",
        "alert_count": "31",
        "latest_event": "2026-04-05T14:19:00Z",
    },
]


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FloraMind Smart Alert System")
    parser.add_argument("--demo", action="store_true",
                        help="Demo mode — use sample alerts, skip Databricks query")
    parser.add_argument("--sms-only", action="store_true",
                        help="Send SMS instead of voice call")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  🌱 FloraMind — Smart Alert System")
    print("=" * 60)
    print()

    # ── Get alerts ────────────────────────────────────────────────────
    if args.demo:
        log.info("Demo mode — using sample CRITICAL alerts")
        alerts = DEMO_ALERTS
    else:
        log.info("Querying Databricks for CRITICAL stress alerts...")
        alerts = query_databricks(CRITICAL_ALERTS_SQL)

    if not alerts:
        print("  ✓ No CRITICAL alerts found. All plants are healthy!")
        print("    (No phone call needed)")
        return

    # ── Display alerts ────────────────────────────────────────────────
    print(f"  Found {len(alerts)} sensor(s) with CRITICAL stress:\n")
    for a in alerts:
        species = SPECIES_NAMES.get(a["plant_species"], a["plant_species"])
        print(f"  🔴 {a['sensor_id']} | Sector {a['sector']} | {species}")
        print(f"     Moisture: {a['avg_moisture']}% | "
              f"Amplitude: {a['avg_amplitude']} | "
              f"Readings: {a['alert_count']}")
        print()

    # ── Trigger alert ─────────────────────────────────────────────────
    if args.sms_only:
        send_sms(alerts)
    else:
        make_voice_call(alerts)


if __name__ == "__main__":
    main()
