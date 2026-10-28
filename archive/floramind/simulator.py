"""
FloraMind — IoT Edge Simulator
================================
Reads a local CSV of acoustic-pop features and continuously streams
mock JSON payloads to a Databricks Unity Catalog Volume via the
Files API, simulating live IoT microphones deployed in agricultural fields.

Usage:
    python simulator.py                          # use defaults
    python simulator.py --csv data/custom.csv    # custom CSV
    python simulator.py --batch-size 10 --interval 1.0
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from itertools import cycle
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("floramind.simulator")

# ── Graceful shutdown ────────────────────────────────────────────────
_shutdown_requested = False


def _signal_handler(signum: int, _frame: Any) -> None:
    global _shutdown_requested
    log.info("Shutdown signal received (sig=%s). Finishing current batch…", signum)
    _shutdown_requested = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ── HTTP session with automatic retries ──────────────────────────────
def _build_session(token: str) -> requests.Session:
    """Return a requests.Session pre-configured with auth, retries, and timeouts."""
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "FloraMind-IoT-Simulator/1.0",
        }
    )

    retry_strategy = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=config.RETRY_BACKOFF_BASE,
        status_forcelist=list(config.RETRY_STATUS_CODES),
        allowed_methods=["PUT", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── Payload construction ─────────────────────────────────────────────
def _build_payload(rows: pd.DataFrame) -> dict[str, Any]:
    """
    Wrap a batch of CSV rows into a JSON envelope that mirrors a real
    IoT microphone burst:

    {
        "batch_id": "<uuid>",
        "edge_ts": "<ISO-8601>",
        "device_count": 3,
        "readings": [ … ]
    }
    """
    readings: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        reading: dict[str, Any] = {
            "sensor_id": row.get("sensor_id", f"MIC-{uuid.uuid4().hex[:6].upper()}"),
            "capture_ts": row.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "peak_frequency_hz": float(row["peak_frequency"]),
            "duration_sec": float(row["duration"]),
            "amplitude": float(row["amplitude"]),
            "plant_species": row.get("plant_species", "unknown"),
            "soil_moisture_pct": float(row["soil_moisture_pct"])
            if "soil_moisture_pct" in row.index
            else None,
        }
        if "sector" in row.index:
            reading["sector"] = str(row["sector"])
        if "stress_label" in row.index:
            reading["stress_label"] = str(row["stress_label"])
        readings.append(reading)

    return {
        "batch_id": str(uuid.uuid4()),
        "edge_ts": datetime.now(timezone.utc).isoformat(),
        "device_count": rows["sensor_id"].nunique() if "sensor_id" in rows.columns else 1,
        "readings": readings,
    }


# ── Upload to Unity Catalog Volume via Files API ────────────────────
def _upload_to_volume(
    session: requests.Session,
    host: str,
    volume_path: str,
    payload: dict[str, Any],
) -> bool:
    """
    Upload a single JSON payload to a Unity Catalog Volume using the
    Files API (PUT /api/2.0/fs/files/<path>).
    The file is written as <volume_path>/<batch_id>.json.

    Returns True on success, False otherwise.
    """
    batch_id = payload["batch_id"]
    file_path = f"{volume_path.strip('/')}/{batch_id}.json"
    json_bytes = json.dumps(payload, default=str).encode("utf-8")

    url = f"{host.rstrip('/')}/api/2.0/fs/files/{file_path}"

    try:
        resp = session.put(
            url,
            data=json_bytes,
            headers={
                "Authorization": session.headers["Authorization"],
                "Content-Type": "application/octet-stream",
                "User-Agent": "FloraMind-IoT-Simulator/1.0",
            },
            timeout=config.REQUEST_TIMEOUT_SEC,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            log.warning("Rate-limited (429). Backing off %ds…", retry_after)
            time.sleep(retry_after)
            resp = session.put(
                url,
                data=json_bytes,
                headers={
                    "Authorization": session.headers["Authorization"],
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "FloraMind-IoT-Simulator/1.0",
                },
                timeout=config.REQUEST_TIMEOUT_SEC,
            )

        if resp.status_code in range(200, 300):
            log.info(
                "✓  Uploaded batch %s → /%s (%d bytes)",
                batch_id[:8],
                file_path,
                len(json_bytes),
            )
            return True

        log.error(
            "✗  Volume PUT failed [%d]: %s",
            resp.status_code,
            resp.text[:300],
        )
        return False

    except requests.exceptions.ConnectionError as exc:
        log.error("Connection error uploading %s: %s", batch_id[:8], exc)
        return False
    except requests.exceptions.Timeout:
        log.error("Timeout uploading %s", batch_id[:8])
        return False


# ── CSV loader ───────────────────────────────────────────────────────
def load_csv(csv_path: str) -> pd.DataFrame:
    """Read and validate the acoustic features CSV."""
    path = Path(csv_path)
    if not path.is_file():
        log.critical("CSV not found: %s", path.resolve())
        sys.exit(1)

    df = pd.read_csv(path)
    required = {"peak_frequency", "duration", "amplitude"}
    missing = required - set(df.columns)
    if missing:
        log.critical("CSV is missing required columns: %s", missing)
        sys.exit(1)

    log.info("Loaded %d rows from %s", len(df), path.name)
    return df


# ── Batch generator (cycles infinitely through CSV rows) ─────────────
def _batch_iter(df: pd.DataFrame, batch_size: int):
    """Yield DataFrames of *batch_size* rows, cycling through the CSV."""
    indices = cycle(range(len(df)))
    while True:
        batch_idx = [next(indices) for _ in range(batch_size)]
        yield df.iloc[batch_idx].copy()


# ── Main loop ────────────────────────────────────────────────────────
def run(
    csv_path: str,
    batch_size: int,
    interval: float,
    max_payloads: int,
    host: str,
    token: str,
    volume_path: str,
) -> None:
    """Core streaming loop."""
    if not host or not token:
        log.critical(
            "DATABRICKS_HOST and DATABRICKS_TOKEN must be set as environment variables."
        )
        sys.exit(1)

    df = load_csv(csv_path)
    session = _build_session(token)
    batches = _batch_iter(df, batch_size)

    sent = 0
    failed = 0
    log.info(
        "Streaming started → host=%s  volume=%s  batch=%d  interval=%.1fs",
        host,
        volume_path,
        batch_size,
        interval,
    )

    for batch_df in batches:
        if _shutdown_requested:
            break
        if max_payloads > 0 and sent >= max_payloads:
            log.info("Reached max_payloads=%d. Stopping.", max_payloads)
            break

        payload = _build_payload(batch_df)
        ok = _upload_to_volume(session, host, volume_path, payload)
        if ok:
            sent += 1
        else:
            failed += 1

        time.sleep(interval)

    log.info("Session complete — sent: %d | failed: %d", sent, failed)
    session.close()


# ── CLI ──────────────────────────────────────────────────────────────
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="floramind-simulator",
        description="FloraMind IoT Edge Simulator — stream acoustic pops to DBFS",
    )
    parser.add_argument(
        "--csv",
        default=config.DEFAULT_CSV_PATH,
        help="Path to the acoustic features CSV (default: data/acoustic_samples.csv)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=config.BATCH_SIZE,
        help=f"Rows per JSON payload (default: {config.BATCH_SIZE})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=config.STREAM_INTERVAL_SEC,
        help=f"Seconds between uploads (default: {config.STREAM_INTERVAL_SEC})",
    )
    parser.add_argument(
        "--max-payloads",
        type=int,
        default=config.MAX_PAYLOADS,
        help="Stop after N payloads (0 = run forever, default: 0)",
    )
    parser.add_argument(
        "--host",
        default=config.DATABRICKS_HOST,
        help="Databricks workspace URL (or set DATABRICKS_HOST env var)",
    )
    parser.add_argument(
        "--token",
        default=config.DATABRICKS_TOKEN,
        help="Databricks PAT (or set DATABRICKS_TOKEN env var)",
    )
    parser.add_argument(
        "--volume-path",
        default=config.UC_VOLUME_PATH,
        help=f"UC Volume path (default: {config.UC_VOLUME_PATH})",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run(
        csv_path=args.csv,
        batch_size=args.batch_size,
        interval=args.interval,
        max_payloads=args.max_payloads,
        host=args.host,
        token=args.token,
        volume_path=args.volume_path,
    )


if __name__ == "__main__":
    main()
