"""
FloraMind IoT Edge Simulator — Configuration
=============================================
Centralized configuration for the Volumes streaming simulator.
Set DATABRICKS_HOST and DATABRICKS_TOKEN as environment variables
or in a .env file before running the simulator.
"""

import os

# ── Databricks connection ────────────────────────────────────────────
DATABRICKS_HOST: str = os.environ.get("DATABRICKS_HOST", "")  # e.g. https://adb-xxxx.azuredatabricks.net
DATABRICKS_TOKEN: str = os.environ.get("DATABRICKS_TOKEN", "")

# ── Unity Catalog Volume target path ─────────────────────────────────
# Format: /Volumes/<catalog>/<schema>/<volume>/<subfolder>
UC_VOLUME_PATH: str = os.environ.get(
    "UC_VOLUME_PATH", "/Volumes/workspace/default/floramind_raw/iot_stream"
)

# ── Streaming behaviour ─────────────────────────────────────────────
# Seconds between consecutive payload uploads
STREAM_INTERVAL_SEC: float = float(os.environ.get("STREAM_INTERVAL_SEC", "2.0"))

# Number of CSV rows to bundle per JSON payload
BATCH_SIZE: int = int(os.environ.get("BATCH_SIZE", "5"))

# Maximum number of payloads to send (0 = infinite)
MAX_PAYLOADS: int = int(os.environ.get("MAX_PAYLOADS", "0"))

# ── Rate-limit / retry settings ─────────────────────────────────────
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.5          # exponential back-off base (seconds)
RETRY_STATUS_CODES: frozenset = frozenset({429, 500, 502, 503, 504})

# ── HTTP ─────────────────────────────────────────────────────────────
REQUEST_TIMEOUT_SEC: int = 30

# ── Local data ───────────────────────────────────────────────────────
DEFAULT_CSV_PATH: str = os.path.join(os.path.dirname(__file__), "data", "acoustic_samples.csv")
