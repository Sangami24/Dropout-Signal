"""Run the counselor workflow against local Flask and headless Chrome."""

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


CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def main():
    if not CHROME.exists():
        raise SystemExit(f"Chrome was not found at {CHROME}")

    with tempfile.TemporaryDirectory(prefix="dropout-signal-browser-") as temp_dir:
        temp_path = Path(temp_dir)
        voice_server._LIVE_STATE_FILE = temp_path / "live.json"
        voice_server.OUTPUT_CSV = str(temp_path / "analysis.csv")
        voice_server.sessions.clear()
        voice_server.completed_calls.clear()
        voice_server.analyzed_results.clear()
        voice_server.wa_sessions.clear()
        voice_server._persist_live_state()
        voice_server.LLM_AVAILABLE = False
        voice_server.twilio_ready = False
        voice_server.twilio_client = None
        voice_server.DEMO_PHONE = "+15550123456"
        voice_server._dataset_is_ready = lambda: True
        voice_server._export_results = lambda: None
        app_overrides._dataset_ready = lambda: True
        app_overrides._manual_call_payload = lambda: {
            "student_id": "STU-ACHAL",
            "student_name": "Achal Sangami",
            "ml_risk_score": 0.91,
            "risk_tier": "HIGH",
        }
        voice_server._start_call = lambda student_id, student_name, phone, ml_risk: {
            "student_id": student_id,
            "name": student_name,
            "call_sid": "CA-BROWSER-CHECK",
            "status": "initiated",
        }

        flask_app = app_module.app
        flask_app.logger.disabled = True
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, flask_app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        def role_cookie(role):
            with flask_app.test_client() as client:
                with client.session_transaction() as session:
                    session["role"] = role
                    session["user"] = f"browser-check-{role}"
                return client.get_cookie("session").value

        session_cookie = role_cookie("counselor")
        admin_session_cookie = role_cookie("admin")

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
        environment.update({
            "DROPOUT_SIGNAL_BROWSER_BASE": base_url,
            "DROPOUT_SIGNAL_DEBUG_PORT": str(debug_port),
            "DROPOUT_SIGNAL_SESSION_COOKIE": session_cookie,
            "DROPOUT_SIGNAL_ADMIN_SESSION_COOKIE": admin_session_cookie,
        })
        completed = None
        try:
            completed = subprocess.run(
                ["node", "browser_flow_check.mjs"],
                cwd=Path(__file__).resolve().parent,
                env=environment,
                text=True,
                capture_output=True,
                timeout=100,
            )
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="")
            if completed.returncode:
                raise RuntimeError(f"Browser check exited with {completed.returncode}")
        finally:
            chrome.terminate()
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome.kill()
            chrome_errors = chrome.stderr.read() if chrome.stderr else ""
            if completed is not None and completed.returncode and chrome_errors:
                print(chrome_errors, end="")
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
