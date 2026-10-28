"""Single-process runner for the unified dashboard.

Using Flask's development reloader starts an extra process, which gives live
calls and WhatsApp messages separate in-memory state.  This runner is used
locally so both role dashboards always talk to the same process.
"""

from app import app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
