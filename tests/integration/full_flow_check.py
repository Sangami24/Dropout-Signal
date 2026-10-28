"""Run a non-destructive full-system regression against local Flask and Chrome."""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

from werkzeug.serving import make_server

import app as app_module
import app_overrides
import voice_server


ROOT = Path(__file__).resolve().parent
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def main() -> None:
    if not CHROME.exists():
        raise SystemExit(f"Chrome was not found at {CHROME}")

    screenshots = ROOT / "runtime_verify" / "full_flow"
    screenshots.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dropout-signal-full-flow-") as temp_dir:
        temp_path = Path(temp_dir)
        voice_server._LIVE_STATE_FILE = temp_path / "live.json"
        voice_server.OUTPUT_CSV = str(temp_path / "analysis.csv")
        voice_server.sessions.clear()
        voice_server.completed_calls.clear()
        voice_server.analyzed_results.clear()
        voice_server.wa_sessions.clear()
        voice_server.LLM_AVAILABLE = False
        voice_server.twilio_ready = False
        voice_server.twilio_client = None
        voice_server.DEMO_PHONE = "+15550123456"
        voice_server.CALL_TRANSCRIPT_REPLY_DELAY_SECONDS = 0
        voice_server.WHATSAPP_REPLY_DELAY_SECONDS = 0
        voice_server._persist_live_state()

        call_counter = {"value": 0}

        def fake_start(student_id, student_name, phone, ml_risk):
            call_counter["value"] += 1
            return {
                "student_id": student_id,
                "name": student_name,
                "call_sid": f"CA-FULL-{call_counter['value']:03d}",
                "status": "initiated",
            }

        voice_server._start_call = fake_start
        voice_server._dataset_is_ready = lambda: True
        voice_server._export_results = lambda: None
        app_overrides._dataset_ready = lambda: True

        flask_app = app_module.app
        flask_app.logger.disabled = True
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, flask_app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        def role_cookie(role: str) -> str:
            with flask_app.test_client() as client:
                with client.session_transaction() as session:
                    session["role"] = role
                    session["user"] = f"full-flow-{role}"
                cookie = client.get_cookie("session")
                if cookie is None:
                    raise RuntimeError(f"Could not create the {role} session cookie")
                return cookie.value

        debug_socket = socket.socket()
        debug_socket.bind(("127.0.0.1", 0))
        debug_port = debug_socket.getsockname()[1]
        debug_socket.close()
        chrome = subprocess.Popen(
            [
                str(CHROME),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={temp_path / 'chrome'}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "DROPOUT_SIGNAL_BROWSER_BASE": base_url,
                "DROPOUT_SIGNAL_DEBUG_PORT": str(debug_port),
                "DROPOUT_SIGNAL_COUNSELOR_COOKIE": role_cookie("counselor"),
                "DROPOUT_SIGNAL_ADMIN_COOKIE": role_cookie("admin"),
                "DROPOUT_SIGNAL_SCREENSHOT_DIR": str(screenshots),
                "DROPOUT_SIGNAL_UPLOAD_CSV": str(ROOT / "datasets" / "comprehensive_student_academic_dataset.csv"),
            }
        )
        completed = None
        try:
            completed = subprocess.run(
                ["node", "full_flow_check.mjs"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=540,
            )
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="")
            if completed.returncode:
                raise RuntimeError(f"Full browser flow exited with {completed.returncode}")
        finally:
            chrome.terminate()
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome.kill()
            if completed is not None and completed.returncode and chrome.stderr:
                errors = chrome.stderr.read()
                if errors:
                    print(errors, end="")
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
