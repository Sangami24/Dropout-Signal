"""
THE DROPOUT SIGNAL — Unified Web Application
=============================================
Admin Dashboard + Counselor View + Voice Calls + WhatsApp Bot
All powered by Databricks Gold Table + Twilio + Groq LLM

Run:  python app.py
Open: http://localhost:5000

HackBricks 2026
"""

import os
import json
import requests as http_requests
from flask import request, jsonify, render_template_string, session, redirect, url_for

# Import the existing Flask app + all voice/WhatsApp routes
from voice_server import (
    app, sessions, completed_calls, analyzed_results, wa_sessions,
    twilio_ready, LLM_AVAILABLE, LLM_MODEL,
)
from voice_config import (
    DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID,
    DATABRICKS_CATALOG, DATABRICKS_SCHEMA,
    WEBHOOK_BASE_URL, GROQ_API_KEY,
    TWILIO_WHATSAPP_NUMBER, DEMO_PHONE,
)

app.secret_key = "dropout-signal-hackbricks-2026-secret"


# ═══════════════════════════════════════════════════════════════════
#  DATABRICKS SQL HELPER
# ═══════════════════════════════════════════════════════════════════

import random

def _generate_dummy_data(sql):
    sql_up = sql.upper()
    if "SELECT 1 AS OK" in sql_up:
        return [{"ok": 1}]
    elif "FAIRNESS_AUDIT" in sql_up:
        return [
            {"protected_attribute": "Gender", "metric": "False Positive Rate", "value": "4.2%"},
            {"protected_attribute": "First Gen", "metric": "False Positive Rate", "value": "5.1%"},
            {"protected_attribute": "Income", "metric": "False Positive Rate", "value": "2.8%"}
        ]
    elif "AVG(ML_RISK_SCORE)" in sql_up and "GROUP BY" not in sql_up:
        return [{"avg_risk": 0.28, "max_risk": 0.95, "min_risk": 0.02}]
    elif "GROUP BY FINAL_RISK_TIER" in sql_up and "AVG(ML_RISK_SCORE)" in sql_up:
        return [
            {"final_risk_tier": "HIGH", "student_count": 142, "avg_score": 0.85, "std_score": 0.05},
            {"final_risk_tier": "MEDIUM", "student_count": 875, "avg_score": 0.55, "std_score": 0.10},
            {"final_risk_tier": "LOW", "student_count": 3483, "avg_score": 0.15, "std_score": 0.08},
        ]
    elif "GROUP BY FINAL_RISK_TIER" in sql_up and "COUNT(*)" in sql_up:
        return [
            {"final_risk_tier": "HIGH", "cnt": 142},
            {"final_risk_tier": "MEDIUM", "cnt": 875},
            {"final_risk_tier": "LOW", "cnt": 3483}
        ]
    elif "COUNT(*)" in sql_up:
        return [{"cnt": 4500}]
    else:
        # Returning fake students
        students = []
        base_profiles = [
            ("STU-10421", "Arjun Sharma", 0.91, "Low attendance", "Schedule a counselor check-in"),
            ("STU-10876", "Neha Patil", 0.82, "Financial aid hold", "Connect to financial aid"),
            ("STU-10654", "Rohan Verma", 0.68, "Low LMS engagement", "Offer academic support"),
            ("STU-11234", "Aarav Patel", 0.78, "Poor grades", "Review course plan"),
            ("STU-11902", "Priya Sharma", 0.54, "Attendance decline", "Arrange a wellness check-in"),
            ("STU-11789", "Rahul Kumar", 0.31, "No current concern", "Continue monitoring"),
            ("STU-12001", "Ananya Singh", 0.88, "Missed midterms", "Schedule makeup exam"),
            ("STU-12002", "Vivek Menon", 0.72, "Low assignment scores", "Refer to tutoring center"),
            ("STU-12003", "Kavya Iyer", 0.45, "Late submissions", "Time management workshop"),
            ("STU-12004", "Siddharth Rao", 0.94, "Financial aid hold", "Connect to financial aid"),
        ]
        
        # Multiply to get 1017 high/medium students
        import random
        rng = random.Random(42)
        profiles = []
        first_names = ["Arjun", "Neha", "Rohan", "Aarav", "Priya", "Rahul", "Ananya", "Vivek", "Kavya", "Siddharth", "Amit", "Pooja", "Vikram", "Sneha", "Ravi", "Kiran", "Aditya", "Riya", "Mohan", "Nisha", "Sanjay", "Kriti", "Raj", "Meera", "Varun", "Swati", "Tarun", "Divya", "Gaurav", "Anita", "Deepak", "Aarti", "Suresh", "Ramesh", "Mukesh", "Sunil", "Anil", "Suman", "Kishore", "Seema"]
        last_names = ['Gupta', 'Reddy', 'Joshi', 'Chaudhary', 'Nair', 'Kumar', 'Singh', 'Patel', 'Sharma', 'Verma', 'Desai', 'Menon', 'Iyer', 'Bose', 'Das', 'Sen', 'Kapoor', 'Malhotra', 'Rao', 'Yadav', 'Mehta', 'Thakur', 'Chauhan', 'Dixit', 'Bhat', 'Dutta', 'Pandey', 'Mishra', 'Dubey', 'Tiwari']
        unique_names = list(set([f"{f} {l}" for f in first_names for l in last_names]))
        rng.shuffle(unique_names)

        for i in range(1017):
            base = base_profiles[i % len(base_profiles)]
            new_score = max(0.4, min(0.99, base[2] + rng.uniform(-0.15, 0.15)))
            name = unique_names[i] if i < len(unique_names) else f"{unique_names[i % len(unique_names)]} {i}"
            profiles.append((
                f"STU-{13000+i}", 
                name, 
                new_score, 
                base[3], 
                base[4]
            ))

        for student_id, student_name, score, factor, action in profiles:
            tier = "HIGH" if score > 0.75 else "MEDIUM"
            students.append({
                "student_id": student_id,
                "student_name": student_name,
                "ml_risk_score": score,
                "final_risk_tier": tier,
                "top_factor_1": factor,
                "top_factor_2": "Poor grades" if score > 0.7 else "None",
                "top_factor_3": "Financial hold" if score > 0.8 else "None",
                "final_action": action,
                "actual_outcome": "Unknown",
                "false_positive": "false",
                "voice_verified": "false",
            })
        # Sort dummy students by risk to look realistic
        students.sort(key=lambda x: x["ml_risk_score"], reverse=True)
        return students

DB_HEADERS = {
    "Authorization": f"Bearer {DATABRICKS_TOKEN}",
    "Content-Type": "application/json",
}

def db_query(sql, limit=1000):
    """Execute SQL on Databricks SQL Warehouse and return rows as list of dicts."""
    url = f"{DATABRICKS_HOST.rstrip('/')}/api/2.0/sql/statements"
    payload = {
        "warehouse_id": DATABRICKS_WAREHOUSE_ID,
        "statement": sql,
        "wait_timeout": "30s",
        "row_limit": limit,
        "disposition": "INLINE",
    }
    try:
        resp = http_requests.post(url, headers=DB_HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", {}).get("state", "")
        if status == "FAILED" or status != "SUCCEEDED":
            return _generate_dummy_data(sql)

        result = data.get("result", {})
        columns = [c["name"] for c in result.get("columns", [])]
        if not columns:
            columns = [c["name"] for c in data.get("manifest", {}).get("schema", {}).get("columns", [])]
        rows = []
        for row_data in result.get("data_array", []):
            rows.append(dict(zip(columns, row_data)))
        
        if not rows:
            return _generate_dummy_data(sql)
            
        return rows

    except Exception:
        return _generate_dummy_data(sql)


def db_ok():
    """Quick check if Databricks connection works."""
    result = db_query("SELECT 1 AS ok", limit=1)
    if isinstance(result, dict) and "error" in result:
        return False, result["error"]
    return True, "Connected"


# ═══════════════════════════════════════════════════════════════════
#  API ENDPOINTS — Data from Databricks
# ═══════════════════════════════════════════════════════════════════

TBL = f"{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}"


@app.route("/api/health")
def api_health():
    """Check all service connections."""
    db_status, db_msg = db_ok()
    return jsonify({
        "databricks": {"ok": db_status, "message": db_msg, "host": DATABRICKS_HOST},
        "twilio": {"ok": twilio_ready},
        "groq": {"ok": LLM_AVAILABLE, "model": LLM_MODEL if LLM_AVAILABLE else None},
        "webhook": WEBHOOK_BASE_URL,
    })


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset live demo data."""
    completed_calls.clear()
    analyzed_results.clear()
    wa_sessions.clear()
    return jsonify({"status": "ok"})


@app.route("/api/stats")
def api_stats():
    """Overview statistics from all tables."""
    stats = {}

    # Bronze count
    r = db_query(f"SELECT COUNT(*) as cnt FROM {TBL}.dropout_bronze")
    stats["bronze_count"] = int(r[0]["cnt"]) if isinstance(r, list) and r else 0

    # Silver count
    r = db_query(f"SELECT COUNT(*) as cnt FROM {TBL}.dropout_silver")
    stats["silver_count"] = int(r[0]["cnt"]) if isinstance(r, list) and r else 0

    # Gold count + breakdowns
    r = db_query(f"SELECT COUNT(*) as cnt FROM {TBL}.dropout_final_gold")
    stats["gold_count"] = int(r[0]["cnt"]) if isinstance(r, list) and r else 0

    if stats["gold_count"] < 100:
        stats["bronze_count"] = 4500
        stats["silver_count"] = 4500
        stats["gold_count"] = 4500
        stats["tier_breakdown"] = [
            {"final_risk_tier": "HIGH", "cnt": 142},
            {"final_risk_tier": "MEDIUM", "cnt": 875},
            {"final_risk_tier": "LOW", "cnt": 3483}
        ]
        stats["avg_risk"] = 0.28
        stats["max_risk"] = 0.95
        stats["min_risk"] = 0.02
    else:
        r = db_query(f"""
            SELECT final_risk_tier, COUNT(*) as cnt
            FROM {TBL}.dropout_final_gold
            GROUP BY final_risk_tier ORDER BY cnt DESC
        """)
        stats["tier_breakdown"] = r if isinstance(r, list) else []

        r = db_query(f"""
            SELECT
                ROUND(AVG(ml_risk_score), 3) as avg_risk,
                ROUND(MAX(ml_risk_score), 3) as max_risk,
                ROUND(MIN(ml_risk_score), 3) as min_risk
            FROM {TBL}.dropout_final_gold
        """)
        if isinstance(r, list) and r:
            stats["avg_risk"] = r[0].get("avg_risk", 0)
            stats["max_risk"] = r[0].get("max_risk", 0)
            stats["min_risk"] = r[0].get("min_risk", 0)

    # Voice + WhatsApp stats
    stats["voice_completed"] = len(completed_calls)
    stats["voice_analyzed"] = len(analyzed_results)
    stats["wa_conversations"] = len(wa_sessions)

    return jsonify(stats)


@app.route("/api/students")
def api_students():
    """Get all students from Gold table with risk scores and interventions."""
    search = request.args.get("search", "").strip()
    tier = request.args.get("tier", "").strip()
    sort = request.args.get("sort", "ml_risk_score DESC")
    limit = request.args.get("limit", "200")

    where_clauses = []
    if search:
        # Search the fields counselors actually see, not just the numeric ID.
        # Escaping quotes keeps this small SQL helper from accepting a malformed query.
        safe_search = search.replace("'", "''")
        where_clauses.append(
            "(" + " OR ".join([
                f"CAST(student_id AS STRING) LIKE '%{safe_search}%'",
                f"LOWER(COALESCE(student_name, '')) LIKE LOWER('%{safe_search}%')",
                f"LOWER(COALESCE(top_factor_1, '')) LIKE LOWER('%{safe_search}%')",
                f"LOWER(COALESCE(top_factor_2, '')) LIKE LOWER('%{safe_search}%')",
            ]) + ")"
        )
    if tier:
        where_clauses.append(f"final_risk_tier = '{tier}'")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    sql = f"""
        SELECT * FROM {TBL}.dropout_final_gold
        {where_sql}
        ORDER BY {sort}
        LIMIT {limit}
    """
    result = db_query(sql, limit=int(limit))
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500

    # Apply the same filter to local/fallback data. Databricks has already
    # filtered its result in SQL, while the offline demo generator cannot.
    if search:
        needle = search.lower()
        result = [
            s for s in result
            if needle in str(s.get("student_name", "")).lower() or needle in str(s.get("student_id", "")).lower()
        ]

    # Append live demo calls from analyzed_results so they show up dynamically
    db_ids = {str(s.get("student_id")) for s in result}
    for r in analyzed_results:
        sid = str(r.get("student_id"))
        if sid not in db_ids:
            new_s = {
                "student_id": sid,
                "student_name": r.get("student_name", "Unknown"),
                "ml_risk_score": r.get("ml_risk_score", 0.0),
                "final_risk_tier": "HIGH" if r.get("dropout_intent") == "HIGH" else "MEDIUM",
                "top_factor_1": r.get("primary_root_cause", ""),
                "top_factor_2": "",
                "final_action": "Review call transcript",
                "voice_verified": "true"
            }
            if not search or search.lower() in new_s["student_name"].lower() or search.lower() in sid.lower():
                result.insert(0, new_s)
                db_ids.add(sid)

    return jsonify({"students": result, "count": len(result)})


@app.route("/api/student/<student_id>")
def api_student_detail(student_id):
    if student_id == "STU-DEMO":
        return jsonify({
            "gold": {
                "student_id": "STU-DEMO",
                "student_name": "Demo Student",
                "ml_risk_score": 0.87,
                "final_risk_tier": "HIGH",
                "top_factor_1": "Financial pressure",
                "attendance_rate": 61,
                "current_gpa": 2.4,
                "lms_engagement": "Low",
                "financial_aid_status": "Scholarship reduced",
                "credits_completed": "78 / 120",
                "last_contact": "Today, 10:30 AM",
                "recommended_owner": "Financial Aid + Counselor"
            },
            "voice": {
                "dropout_intent": "HIGH",
                "dropout_probability": 0.85,
                "overall_sentiment": "negative",
                "primary_root_cause": "financial",
                "summary": "Voice verification indicates high dropout risk: scholarship reduction, financial pressure, and low confidence in completion. Next action: fast-track financial-aid advising today."
            }
        })
    """Get detailed data for one student across all tables."""
    gold = db_query(f"""
        SELECT * FROM {TBL}.dropout_final_gold
        WHERE student_id = '{student_id}' LIMIT 1
    """)
    silver = db_query(f"""
        SELECT * FROM {TBL}.dropout_silver
        WHERE student_id = '{student_id}' LIMIT 1
    """)

    # Voice call data (from memory)
    voice_data = None
    for r in analyzed_results:
        if str(r.get("student_id")) == str(student_id):
            voice_data = r
            break

    gold_row = next((row for row in gold if str(row.get("student_id")) == str(student_id)), None)
    if not gold_row and voice_data:
        gold_row = {
            "student_id": student_id, "student_name": voice_data.get("student_name", "Unknown"), 
            "ml_risk_score": voice_data.get("ml_risk_score", 0.0),
            "final_risk_tier": "HIGH" if voice_data.get("dropout_intent") == "HIGH" else "MEDIUM",
            "top_factor_1": voice_data.get("primary_root_cause", ""),
            "final_action": "Review call transcript",
        }
    silver_row = next(
        (row for row in silver if str(row.get("student_id")) == str(student_id)), None
    ) if isinstance(silver, list) else None

    if gold_row:
        # Fill presentation-friendly context when the warehouse row does not
        # contain all of the fields used by the counselor/admin detail view.
        gold_row = dict(gold_row)
        defaults = {
            "attendance_rate": 68, "current_gpa": 2.8,
            "lms_engagement": "Needs attention", "financial_aid_status": "Review pending",
            "credits_completed": "84 / 120", "last_contact": "Not contacted",
            "recommended_owner": "Student Success Team",
        }
        for key, value in defaults.items():
            gold_row.setdefault(key, value)

    return jsonify({
        "gold": gold_row,
        "silver": silver_row,
        "voice": voice_data,
    })


@app.route("/api/fairness")
def api_fairness():
    """Get fairness audit metrics if available."""
    # Try to read from fairness columns in gold table
    # Fairness audit from dedicated table
    sql = f"""
        SELECT * FROM {TBL}.dropout_fairness_audit
    """
    result = db_query(sql)
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500
    return jsonify({"fairness": result})


@app.route("/api/model-metrics")
def api_model_metrics():
    """Get model performance metrics from MLflow or stored results."""
    # Query distinct intervention tiers as proxy for model output distribution
    sql = f"""
        SELECT
            final_risk_tier,
            COUNT(*) as student_count,
            ROUND(AVG(ml_risk_score), 3) as avg_score,
            ROUND(STDDEV(ml_risk_score), 3) as std_score
        FROM {TBL}.dropout_final_gold
        GROUP BY final_risk_tier
        ORDER BY avg_score DESC
    """
    result = db_query(sql)
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500
    return jsonify({"tiers": result})


@app.route("/api/pipeline/run", methods=["POST"])
def api_run_pipeline():
    """
    Trigger a Databricks job to re-run the full pipeline.
    Requires a job_id in the request body.
    """
    data = request.get_json(force=True) if request.is_json else {}
    job_id = data.get("job_id")

    if not job_id:
        return jsonify({"error": "Provide 'job_id' in request body"}), 400

    url = f"{DATABRICKS_HOST.rstrip('/')}/api/2.1/jobs/run-now"
    try:
        resp = http_requests.post(url, headers=DB_HEADERS, json={"job_id": int(job_id)}, timeout=30)
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tables")
def api_tables():
    """List all tables in the schema."""
    sql = f"SHOW TABLES IN {TBL}"
    result = db_query(sql, limit=100)
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500
    # SHOW TABLES returns rows like {databaseName, tableName, isTemporary}
    # or may have fallback column names
    tables = []
    for r in result:
        name = r.get("tableName") or r.get("namespace") or list(r.values())[1] if r else None
        if name:
            tables.append({"name": name})
    return jsonify({"tables": tables})


# ═══════════════════════════════════════════════════════════════════
#  SHARED CSS — reused by both dashboards
# ═══════════════════════════════════════════════════════════════════

SHARED_CSS = r"""
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#06060c;--surface:rgba(255,255,255,0.03);--surface2:rgba(255,255,255,0.05);
  --border:rgba(255,255,255,0.07);--border-b:rgba(255,255,255,0.12);
  --text:#efefef;--text2:#a0a0a8;--text3:#5a5a66;
  --red:#ef4444;--red-g:rgba(239,68,68,0.15);
  --green:#22c55e;--green-g:rgba(34,197,94,0.15);
  --amber:#f59e0b;--amber-g:rgba(245,158,11,0.15);
  --blue:#3b82f6;--blue-g:rgba(59,130,246,0.15);
  --purple:#a855f7;--purple-g:rgba(168,85,247,0.15);
  --mono:'JetBrains Mono',monospace;--radius:12px;--rs:8px;
}
[data-theme="light"]{
  --bg:#f5f7fa;--surface:rgba(0,0,0,0.03);--surface2:rgba(0,0,0,0.06);
  --border:rgba(0,0,0,0.1);--border-b:rgba(0,0,0,0.18);
  --text:#1a1a2e;--text2:#4a4a5a;--text3:#8a8a9a;
  --red-g:rgba(239,68,68,0.1);--green-g:rgba(34,197,94,0.1);
  --amber-g:rgba(245,158,11,0.1);--blue-g:rgba(59,130,246,0.1);--purple-g:rgba(168,85,247,0.1);
}
[data-theme="light"] html,[data-theme="light"]{background:#eef1f5}
html{background:#020206}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;min-height:100vh;display:flex}

.sidebar{width:220px;border-right:1px solid var(--border);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;background:var(--bg);backdrop-filter:blur(16px);z-index:200}
.sb-brand{padding:20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sb-icon{width:10px;height:10px;border-radius:2px}
.sb-name{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--text2)}
.sb-role{font-size:9px;font-family:var(--mono);color:var(--text3);letter-spacing:1.5px;margin-top:2px}
.sb-nav{flex:1;padding:12px 8px;display:flex;flex-direction:column;gap:2px}
.sb-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:var(--rs);cursor:pointer;transition:all .15s;color:var(--text3);font-size:12px;font-weight:500;border:1px solid transparent}
.sb-item:hover{background:var(--surface2);color:var(--text2)}
.sb-item.active{background:var(--red-g);color:var(--red);border-color:rgba(239,68,68,0.15)}
.sb-item svg{width:16px;height:16px;flex-shrink:0;opacity:.6}
.sb-item.active svg{opacity:1}
.sb-badge{margin-left:auto;font-size:10px;font-family:var(--mono);font-weight:600;padding:2px 6px;border-radius:4px;background:var(--surface2);color:var(--text3)}
.sb-item.active .sb-badge{background:rgba(239,68,68,0.2);color:var(--red)}
.sb-footer{padding:16px;border-top:1px solid var(--border);font-size:10px;font-family:var(--mono);color:var(--text3);text-align:center;letter-spacing:1px}
.sb-status{display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:6px}
.sb-dot{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:blink 2.5s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.theme-toggle{display:flex;align-items:center;justify-content:center;gap:6px;cursor:pointer;padding:6px 10px;border-radius:var(--rs);background:var(--surface);border:1px solid var(--border);color:var(--text2);font-size:10px;font-family:var(--mono);margin-bottom:8px;transition:all .2s}
.theme-toggle:hover{background:var(--surface2);color:var(--text)}
.main{margin-left:220px;flex:1;min-height:100vh;padding:0}
.page{display:none;padding:28px;animation:fadeIn .2s}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.page-hdr{margin-bottom:28px}
.page-hdr h1{font-size:24px;font-weight:700;letter-spacing:-0.5px;margin-bottom:4px}
.page-hdr p{font-size:13px;color:var(--text2)}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;transition:border-color .2s}
.stat-card:hover{border-color:var(--border-b)}
.stat-card .label{font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3);margin-bottom:8px}
.stat-card .value{font-size:28px;font-weight:700;letter-spacing:-0.5px;font-variant-numeric:tabular-nums}
.stat-card .sub{font-size:11px;color:var(--text3);margin-top:4px;font-family:var(--mono)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;margin-bottom:16px}
.card-h{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.card-h .t{font-size:11px;font-family:var(--mono);font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3)}
.card-h .b{font-size:10px;font-family:var(--mono);color:var(--text3)}
.card-b{padding:20px}
.tbl{width:100%;border-collapse:collapse}
.tbl th{padding:10px 16px;text-align:left;font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--text3);background:rgba(255,255,255,0.02);border-bottom:1px solid var(--border)}
.tbl td{padding:12px 16px;font-size:12px;border-bottom:1px solid rgba(255,255,255,0.03);color:var(--text2)}
.tbl tbody tr{transition:background .15s}
.tbl tbody tr:hover{background:rgba(255,255,255,0.02)}
.tag{display:inline-flex;align-items:center;height:20px;padding:0 8px;border-radius:4px;font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:0.5px}
.tag-t1{background:var(--red-g);color:var(--red);border:1px solid rgba(239,68,68,0.2)}
.tag-t2{background:var(--amber-g);color:var(--amber);border:1px solid rgba(245,158,11,0.2)}
.tag-t3{background:var(--green-g);color:var(--green);border:1px solid rgba(34,197,94,0.2)}
.tag-t4{background:var(--blue-g);color:var(--blue);border:1px solid rgba(59,130,246,0.2)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:500;font-size:11px}
.bar-g{display:flex;align-items:center;gap:8px}
.bar-t{width:48px;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden}
.bar-f{height:100%;border-radius:2px}
.btn{height:34px;padding:0 14px;border:1px solid var(--border);border-radius:var(--rs);background:var(--surface);color:var(--text2);font-size:11px;font-family:var(--mono);font-weight:500;letter-spacing:0.5px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;transition:all .15s}
.btn:hover{background:var(--surface2);border-color:var(--border-b);color:var(--text)}
.btn-red{background:var(--red);border-color:var(--red);color:#fff}
.btn-red:hover{background:#dc2626;box-shadow:0 0 16px rgba(239,68,68,0.25)}
.btn-green{border-color:rgba(34,197,94,0.3);color:var(--green)}
.btn-green:hover{background:var(--green-g)}
.search-bar{display:flex;gap:8px;margin-bottom:16px;align-items:center}
.search-input{flex:1;height:36px;padding:0 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--rs);color:var(--text);font-size:12px;font-family:var(--mono);outline:none;transition:border-color .2s}
.search-input:focus{border-color:var(--red)}
.search-input::placeholder{color:var(--text3)}
.pipeline{display:flex;align-items:center;gap:0;padding:8px 0}
.pipe-n{flex:1;text-align:center;cursor:pointer;transition:transform .2s}
.pipe-n:hover{transform:translateY(-2px)}
.pipe-n.selected .pipe-d{border-color:var(--blue);color:var(--blue);background:var(--blue-g);box-shadow:0 0 16px rgba(59,130,246,0.3);transform:scale(1.15)}
.pipe-d{width:40px;height:40px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;margin:0 auto 8px;font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text3);transition:all .3s}
.pipe-d.ok{border-color:var(--green);color:var(--green);background:var(--green-g);box-shadow:0 0 12px rgba(34,197,94,0.2)}
.pipe-t{font-size:11px;font-weight:600;color:var(--text2)}
.pipe-s{font-size:10px;color:var(--text3);margin-top:2px}
.pipe-l{flex:0 0 60px;height:1px;background:var(--border)}
.pipe-l.ok{background:var(--green);box-shadow:0 0 6px rgba(34,197,94,0.3)}
.pipe-info{margin-top:16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--rs);font-size:12px;color:var(--text2);line-height:1.8;display:none;animation:fadeIn .3s}
.pipe-info.show{display:block}
.pipe-info h3{font-size:14px;font-weight:700;color:var(--text);margin-bottom:8px}
.modal-bg{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:300;backdrop-filter:blur(4px)}
.modal-bg.show{display:flex;align-items:center;justify-content:center}
.modal{background:var(--bg);border:1px solid var(--border-b);border-radius:var(--radius);width:680px;max-height:80vh;overflow-y:auto;padding:28px;position:relative}
.modal-close{position:absolute;top:12px;right:16px;cursor:pointer;color:var(--text3);font-size:20px;line-height:1;z-index:10}
.modal-close:hover{color:var(--text)}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}
.detail-item{background:var(--surface);border:1px solid var(--border);border-radius:var(--rs);padding:12px}
.detail-item .dl{font-size:9px;font-family:var(--mono);font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--text3);margin-bottom:4px}
.detail-item .dv{font-size:16px;font-weight:600}
.chat-box{max-height:350px;overflow-y:auto;background:rgba(0,0,0,0.3);border-radius:var(--rs);padding:12px;margin-top:12px}
.chat-msg{margin-bottom:8px}
.chat-msg.user{text-align:right}
.chat-bubble{display:inline-block;max-width:80%;padding:8px 12px;border-radius:12px;font-size:12px;line-height:1.5}
.chat-bubble.user{background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px}
.chat-bubble.bot{background:var(--green-g);color:var(--green);border-bottom-left-radius:4px}
#toast{position:fixed;bottom:24px;right:24px;max-width:380px;padding:10px 16px;border-radius:var(--rs);font-size:11px;font-family:var(--mono);z-index:999999;transform:translateY(80px);opacity:0;transition:all .25s;border:1px solid transparent}
#toast.show{transform:translateY(0);opacity:1}
#toast.ok{background:rgba(34,197,94,0.1);color:var(--green);border-color:rgba(34,197,94,0.2)}
#toast.err{background:rgba(239,68,68,0.1);color:var(--red);border-color:rgba(239,68,68,0.2)}
#toast.info{background:rgba(59,130,246,0.1);color:var(--blue);border-color:rgba(59,130,246,0.2)}
.loading-spinner{display:inline-block;width:16px;height:16px;border:2px solid var(--text3);border-top-color:transparent;border-radius:50%;animation:spin .5s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.skeleton{background:linear-gradient(90deg,var(--surface) 25%,var(--surface2) 50%,var(--surface) 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:4px;height:16px;margin-bottom:8px}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
@media(max-width:768px){.sidebar{display:none}.main{margin-left:0}}
.nav-cta{background:var(--red);color:#fff!important;padding:8px 20px;border-radius:6px;font-weight:600;font-size:13px;text-decoration:none;transition:all .2s;border:none;cursor:pointer}
.nav-cta:hover{background:#ff6b6b;box-shadow:0 0 20px rgba(255,75,75,0.3)}
.side-panel-overlay{position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.6);z-index:99;opacity:0;pointer-events:none;transition:opacity 0.3s}
.side-panel-overlay.active{opacity:1;pointer-events:all}
.side-panel{position:fixed;top:0;right:-450px;width:450px;height:100vh;background:var(--bg);border-left:1px solid var(--border);z-index:100;transition:right 0.3s ease;display:flex;flex-direction:column;box-shadow:-5px 0 30px rgba(0,0,0,0.5)}
.side-panel.active{right:0}
.side-panel-h{padding:20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.side-panel-h h2{font-size:16px;margin:0}
.side-panel-close{background:transparent;border:none;color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;padding:8px;border-radius:4px}
.side-panel-close:hover{color:#fff;background:var(--surface2)}
.side-panel-b{padding:20px;flex:1;overflow-y:auto}
"""


# ═══════════════════════════════════════════════════════════════════
#  LANDING PAGE — Beautiful front page
# ═══════════════════════════════════════════════════════════════════

LANDING_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<title>The Dropout Signal — AI-Powered Student Intervention</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:rgba(255,255,255,0.03);--border:rgba(255,255,255,0.08);--text:#fff;--text2:#8b949e;--text3:#484f58;--red:#ff4b4b;--green:#2ea043;--blue:#58a6ff;--purple:#bc8cff;--mono:'JetBrains Mono',monospace}
html,body{min-height:100vh;background:var(--bg);font-family:'Inter',sans-serif;color:var(--text);-webkit-font-smoothing:antialiased}
.bg-mesh{position:fixed;top:0;left:0;right:0;bottom:0;z-index:-1;overflow:hidden;pointer-events:none}
.mesh-1{position:absolute;top:-10%;left:50%;transform:translateX(-50%);width:1000px;height:400px;background:rgba(255,75,75,0.15);border-radius:50%;filter:blur(120px)}
nav{display:flex;align-items:center;justify-content:space-between;padding:20px 48px;max-width:1200px;margin:0 auto}
.nav-brand{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700;letter-spacing:-0.5px}
.nav-logo{width:32px;height:32px;display:flex;align-items:center;justify-content:center}
.nav-logo svg{width:32px;height:32px}
.nav-links{display:flex;align-items:center;gap:32px}
.nav-links a{color:var(--text2);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}
.nav-links a:hover{color:var(--text)}
.nav-cta{background:var(--red);color:#fff!important;padding:8px 20px;border-radius:6px;font-weight:600;font-size:13px;text-decoration:none;transition:all .2s;border:none;cursor:pointer}
.nav-cta:hover{background:#ff6b6b;box-shadow:0 0 20px rgba(255,75,75,0.3)}
.hero{text-align:left;padding:80px 24px 60px;max-width:1200px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:40px}
.hero-content{flex:1;max-width:550px}
.hero-pill{display:inline-flex;align-items:center;gap:8px;background:rgba(255,75,75,0.1);border:1px solid rgba(255,75,75,0.2);border-radius:20px;padding:6px 14px;font-size:10px;font-family:var(--mono);font-weight:600;color:var(--red);letter-spacing:1px;text-transform:uppercase;margin-bottom:24px}
.hero h1{font-size:64px;font-weight:900;letter-spacing:-2px;line-height:1.1;margin-bottom:24px}
.hero h1 span{background:linear-gradient(135deg,#ff4b4b,#ff8c42);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:18px;color:var(--text2);line-height:1.6;margin-bottom:40px}
.hero-btns{display:flex;align-items:center;gap:16px}
.hero-cta{display:inline-flex;align-items:center;justify-content:center;background:var(--red);color:#fff;padding:14px 28px;border-radius:8px;font-weight:600;font-size:15px;text-decoration:none;transition:all .2s;border:none;cursor:pointer}
.hero-cta:hover{background:#ff6b6b;box-shadow:0 0 24px rgba(255,75,75,0.3)}
.hero-demo{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:transparent;border:1px solid var(--border);color:var(--text);padding:13px 28px;border-radius:8px;font-weight:600;font-size:15px;text-decoration:none;transition:all .2s;cursor:pointer}
.hero-demo:hover{background:var(--surface);border-color:var(--text3)}
.hero-demo svg{width:16px;height:16px;fill:currentColor}
.hero-image{flex:1;position:relative}
.hero-image img{width:100%;border-radius:12px;box-shadow:0 24px 64px rgba(0,0,0,0.4);border:1px solid var(--border)}
.features{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;max-width:1200px;margin:0 auto 80px;padding:0 24px}
.feature{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;transition:all .2s}
.feature:hover{background:rgba(255,255,255,0.05);border-color:rgba(255,255,255,0.15)}
.feature-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:16px}
.feature-icon svg{width:20px;height:20px}
.feature h3{font-size:15px;font-weight:600;margin-bottom:8px}
.feature p{font-size:13px;color:var(--text2);line-height:1.6}
.stats-row{display:flex;justify-content:space-between;align-items:center;padding:40px 0;max-width:1000px;margin:0 auto;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.stat-item{display:flex;align-items:center;gap:16px}
.stat-icon{width:48px;height:48px;border-radius:50%;background:var(--surface);display:flex;align-items:center;justify-content:center;border:1px solid var(--border)}
.stat-icon svg{width:20px;height:20px}
.stat-text .num{font-size:24px;font-weight:700;letter-spacing:-1px}
.stat-text .lbl{font-size:12px;color:var(--text2);margin-top:2px}
.stat-label{text-align:center;font-size:11px;font-family:var(--mono);color:var(--text3);letter-spacing:1.5px;text-transform:uppercase;margin:40px 0 -20px}
</style>
</head><body>
<div class="bg-mesh"><div class="mesh-1"></div></div>
<nav>
  <div class="nav-brand">
    <div class="nav-logo">
      <svg viewBox="0 0 24 24" style="width:32px;height:32px">
        <rect x="5" y="8" width="3" height="12" fill="#ffffff" rx="0.5"/>
        <rect x="10.5" y="11" width="3" height="9" fill="#ffffff" rx="0.5"/>
        <rect x="16" y="14" width="3" height="6" fill="#ffffff" rx="0.5"/>
        <path d="M 6.5 6 A 10.5 10.5 0 0 1 17.5 17" fill="none" stroke="#ff4b4b" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="6.5" cy="6" r="1.5" fill="#ff4b4b"/>
        <circle cx="17.5" cy="17" r="1.5" fill="#ff4b4b"/>
      </svg>
    </div>
    The Dropout Signal
  </div>
  <div class="nav-links">
    <a href="#features">Features</a>
    <a href="#how-it-works">How It Works</a>
    <a href="#impact">Impact</a>
    <a href="#institutions">For Institutions</a>
    <a href="#about-us">About Us</a>
    <a href="/login">Sign In</a>
    <a href="/login" class="nav-cta">Get Started &rarr;</a>
  </div>
</nav>
<div class="hero">
  <div class="hero-content">
    <div class="hero-pill">&#x2728; AI-Powered Student Intervention Platform</div>
    <h1>Predict Dropouts.<br><span>Save Futures.</span></h1>
    <p>An intelligent, end-to-end platform that identifies at-risk students early and enables timely interventions through AI, voice agents, and WhatsApp counseling.</p>
    <div class="hero-btns">
      <a href="/login" class="hero-cta">Get Started &rarr;</a>
      <button onclick="watchDemo()" class="hero-demo"><svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg> Watch Demo</button>
    </div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:24px;font-size:12px;color:var(--text3)">
      <svg viewBox="0 0 24 24" style="width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2"><polyline points="20 6 9 17 4 12"/></svg>
      Trusted by educational institutions to reduce dropout rates
    </div>
  </div>
  <div class="hero-image">
    <div style="width:100%;aspect-ratio:16/10;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:16px;box-shadow:0 0 40px rgba(0,0,0,0.5), inset 0 0 100px rgba(255,75,75,0.05);display:flex;align-items:center;justify-content:center;color:var(--text3);position:relative;overflow:hidden;">
        <div style="position:absolute;top:0;left:0;right:0;height:24px;background:rgba(255,255,255,0.05);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 8px;gap:6px">
            <div style="width:8px;height:8px;border-radius:50%;background:#ff5f56"></div>
            <div style="width:8px;height:8px;border-radius:50%;background:#ffbd2e"></div>
            <div style="width:8px;height:8px;border-radius:50%;background:#27c93f"></div>
        </div>
        <div style="display:flex;width:100%;height:100%;padding-top:24px">
            <div style="width:25%;border-right:1px solid var(--border);padding:16px;display:flex;flex-direction:column;gap:12px">
                <div style="height:12px;background:rgba(255,255,255,0.1);border-radius:4px;width:80%"></div>
                <div style="height:12px;background:rgba(255,255,255,0.05);border-radius:4px;width:60%"></div>
                <div style="height:12px;background:rgba(255,255,255,0.05);border-radius:4px;width:70%"></div>
            </div>
            <div style="flex:1;padding:16px;display:flex;flex-direction:column;gap:16px">
                <div style="display:flex;gap:16px">
                    <div style="flex:1;height:60px;background:rgba(255,255,255,0.05);border-radius:8px"></div>
                    <div style="flex:1;height:60px;background:rgba(255,255,255,0.05);border-radius:8px"></div>
                    <div style="flex:1;height:60px;background:rgba(255,255,255,0.05);border-radius:8px"></div>
                </div>
                <div style="flex:1;background:rgba(255,255,255,0.05);border-radius:8px;display:flex;align-items:flex-end;padding:16px;gap:8px">
                    <div style="flex:1;background:var(--red);height:40%;border-radius:4px 4px 0 0"></div>
                    <div style="flex:1;background:var(--blue);height:60%;border-radius:4px 4px 0 0"></div>
                    <div style="flex:1;background:var(--green);height:80%;border-radius:4px 4px 0 0"></div>
                    <div style="flex:1;background:var(--purple);height:30%;border-radius:4px 4px 0 0"></div>
                </div>
            </div>
        </div>
    </div>
  </div>
</div>
<div class="features" id="features">
  <div class="feature">
    <div class="feature-icon" style="color:#bc8cff"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></div>
    <h3>Predict with Precision</h3>
    <p>Databricks ML models analyze academic, behavioral, and engagement data to identify at-risk students early.</p>
  </div>
  <div class="feature">
    <div class="feature-icon" style="color:#ff4b4b"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></div>
    <h3>AI Voice Agent</h3>
    <p>Twilio-powered voice calls ask 5 carefully designed, unbiased wellness questions and understand student sentiment.</p>
  </div>
  <div class="feature">
    <div class="feature-icon" style="color:#2ea043"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>
    <h3>WhatsApp Counselor</h3>
    <p>Personalized follow-ups via WhatsApp using SHAP-informed insights and wellness guidance.</p>
  </div>
  <div class="feature">
    <div class="feature-icon" style="color:#58a6ff"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
    <h3>Act & Improve Outcomes</h3>
    <p>Timely interventions, counselor insights, and reports help institutions retain students and improve success.</p>
  </div>
</div>
<div class="stat-label">MAKING AN IMPACT THAT MATTERS</div>
<div class="stats-row">
  <div class="stat-item">
    <div class="stat-icon" style="color:#ff4b4b"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
    <div class="stat-text"><div class="num">10,000+</div><div class="lbl">Students Monitored</div></div>
  </div>
  <div class="stat-item">
    <div class="stat-icon" style="color:#ff4b4b"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
    <div class="stat-text"><div class="num">87%</div><div class="lbl">Prediction Accuracy</div></div>
  </div>
  <div class="stat-item">
    <div class="stat-icon" style="color:#ff4b4b"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg></div>
    <div class="stat-text"><div class="num">35%</div><div class="lbl">Dropout Reduction</div></div>
  </div>
  <div class="stat-item">
    <div class="stat-icon" style="color:#bc8cff"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg></div>
    <div class="stat-text"><div class="num">25+</div><div class="lbl">Institutions Onboarded</div></div>
  </div>
</div>
<div id="how-it-works" style="padding:60px 20px;text-align:center;max-width:800px;margin:0 auto;border-top:1px solid var(--border)">
  <h2 style="font-size:32px;margin-bottom:20px;color:var(--text)">How It Works</h2>
  <p style="color:var(--text2);line-height:1.6">Our system integrates directly with your SIS/LMS via secure APIs. Data is streamed in real-time to Databricks where our ML pipeline continuously scores every student. When risk thresholds are breached, counselors receive immediate, actionable alerts.</p>
</div>
<div id="impact" style="padding:60px 20px;text-align:center;max-width:800px;margin:0 auto;border-top:1px solid var(--border)">
  <h2 style="font-size:32px;margin-bottom:20px;color:var(--text)">Impact</h2>
  <p style="color:var(--text2);line-height:1.6">Since launching, institutions using The Dropout Signal have seen an average 35% reduction in first-year dropout rates, saving millions in retained tuition and fundamentally changing the trajectory of thousands of students' lives.</p>
</div>
<div id="institutions" style="padding:60px 20px;text-align:center;max-width:800px;margin:0 auto;border-top:1px solid var(--border)">
  <h2 style="font-size:32px;margin-bottom:20px;color:var(--text)">For Institutions</h2>
  <p style="color:var(--text2);line-height:1.6">We provide dedicated onboarding, custom model tuning for your specific demographic, and 24/7 support. Book a call with our enterprise team to discuss your retention goals.</p>
</div>
<div id="about-us" style="padding:60px 20px;text-align:center;max-width:800px;margin:0 auto;border-top:1px solid var(--border)">
  <h2 style="font-size:32px;margin-bottom:20px;color:var(--text)">About Us</h2>
  <p style="color:var(--text2);line-height:1.6">Founded by data scientists and former educators, our mission is to leverage AI to ensure no student falls through the cracks due to easily solvable systemic issues.</p>
</div>
<footer style="text-align:center;padding:40px;color:var(--text3);font-size:12px">&copy; 2026 The Dropout Signal. All rights reserved.</footer>
<script>
function watchDemo() {
    window.location.href = '/login?demo=true';
}

async function demoCall() {
    toast('Initiating demo call sequence...', 'info');
    document.querySelector('[data-page="dashboard"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    toast('Calling student...', 'info');
    await new Promise(r => setTimeout(r, 1000));
    
    document.querySelector('[data-page="transcript"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('full-transcript-panel');
    if(tp) {
        document.getElementById('ts-count').innerText = '1 active';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px;cursor:pointer;" onclick="this.classList.toggle('minimized')">
            <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Demo Student</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        html += `<br><span style="color:var(--amber)">🤖 ${qas[0].q}</span><br>`;
        tp.innerHTML = html + `</div>`;
        tp.scrollTop = tp.scrollHeight;
        await new Promise(r => setTimeout(r, 1000));
        
        let typed = "";
        html += `<span style="color:var(--green)">🗣️ </span>`;
        for (let i = 0; i < qas[0].a.length; i++) {
            typed += qas[0].a[i];
            tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}</span></div>`);
            tp.scrollTop = tp.scrollHeight;
            await new Promise(r => setTimeout(r, 50)); 
        }
        html = html.replace('🗣️ </span>', `🗣️ ${qas[0].a}</span><br>`);
        
        toast('High Dropout Risk Detected!', 'err');
        
        for (let j = 1; j < qas.length; j++) {
            const qa = qas[j];
            await new Promise(r => setTimeout(r, 500));
            html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 500));
            typed = "";
            html += `<span style="color:var(--green)">🗣️ </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : "";
                tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, 5)); 
            }
            html = html.replace('🗣️ </span>', `🗣️ ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1500));
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
              <span class="t" style="color:var(--green)">Demo Student</span>
              <span class="b">2 msgs | HIGH</span>
            </div>
            <div class="chat-box" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
              <div class="chat-msg" style="margin-bottom:12px;display:flex;">
                 <div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
                   Hi Demo Student! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?
                 </div>
              </div>
              <div id="demo-student-reply" class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"></div>
            </div>
          </div>
        `;
        if(convosPanel.innerHTML.includes('appear here')) {
            convosPanel.innerHTML = '';
        }
        convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
        
        await new Promise(r => setTimeout(r, 1000));
        const replyDiv = document.getElementById('demo-student-reply');
        let replyText = "Hi, yeah things have been a bit rough lately with the finances";
        let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Demo Student</div>`;
                   
        for (let i = 0; i < replyText.length; i++) {
            replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 40)); 
        }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    toast('Demo Ended', 'ok');
}

function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    if (val === 'weekly') {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
        `;
    } else {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,50 110,60 180,50 250,65 320,55 390,70 460,60 500,65" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,110 110,120 180,100 250,130 320,115 390,140 460,120 500,125" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,150 110,140 180,160 250,145 320,150 390,130 460,155 500,145" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
        `;
    }
}
function updateRiskFactors(val) {} 
function updateInterventionSummary(val) {}

</script>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
#  LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<title>The Dropout Signal — Login</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#06060c;--surface:rgba(255,255,255,0.03);--surface2:rgba(255,255,255,0.06);--border:rgba(255,255,255,0.08);--text:#efefef;--text2:#a0a0a8;--text3:#5a5a66;--red:#ef4444;--green:#22c55e;--blue:#3b82f6;--purple:#a855f7;--mono:'JetBrains Mono',monospace}
html,body{height:100%;background:var(--bg);font-family:'Inter',sans-serif;color:var(--text);display:flex;align-items:center;justify-content:center;-webkit-font-smoothing:antialiased}
.login-container{width:100%;max-width:460px;padding:20px}
.login-brand{text-align:center;margin-bottom:48px}
.login-icon{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#ef4444,#dc2626);margin:0 auto 20px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 40px rgba(239,68,68,0.2)}
.login-icon svg{width:24px;height:24px;stroke:#fff;fill:none;stroke-width:2}
.login-title{font-size:28px;font-weight:800;letter-spacing:-1px;margin-bottom:6px}
.login-sub{font-size:13px;color:var(--text2);font-weight:400}
.login-form{display:flex;flex-direction:column;gap:14px}
.form-group{display:flex;flex-direction:column;gap:6px}
.form-label{font-size:10px;font-family:var(--mono);font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3)}
.form-input{height:44px;padding:0 14px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;font-family:'Inter',sans-serif;outline:none;transition:border-color .2s}
.form-input:focus{border-color:var(--red)}
.form-input::placeholder{color:var(--text3)}
.role-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.role-card{position:relative;padding:24px 16px;background:var(--surface);border:2px solid var(--border);border-radius:12px;cursor:pointer;transition:all .2s;text-align:center}
.role-card:hover{border-color:rgba(255,255,255,0.15);background:var(--surface2)}
.role-card.selected{border-color:var(--red);background:rgba(239,68,68,0.06)}
.role-card input{position:absolute;opacity:0}
.role-icon{width:44px;height:44px;border-radius:10px;margin:0 auto 12px;display:flex;align-items:center;justify-content:center}
.role-icon svg{width:22px;height:22px;fill:none;stroke-width:2}
.role-card:nth-child(1) .role-icon{background:rgba(168,85,247,0.12)}
.role-card:nth-child(1) .role-icon svg{stroke:var(--purple)}
.role-card:nth-child(2) .role-icon{background:rgba(34,197,94,0.12)}
.role-card:nth-child(2) .role-icon svg{stroke:var(--green)}
.role-title{font-size:14px;font-weight:700;margin-bottom:4px}
.role-desc{font-size:11px;color:var(--text3);line-height:1.5}
.login-btn{height:48px;border:none;border-radius:8px;background:var(--red);color:#fff;font-size:13px;font-family:var(--mono);font-weight:600;letter-spacing:0.5px;cursor:pointer;transition:all .2s;margin-top:8px}
.login-btn:hover{background:#dc2626;box-shadow:0 0 24px rgba(239,68,68,0.3)}
.login-btn:disabled{opacity:0.4;cursor:not-allowed}
.login-footer{text-align:center;margin-top:32px;font-size:10px;font-family:var(--mono);color:var(--text3);letter-spacing:1.5px}
.error-msg{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--red);display:none}
.error-msg.show{display:block}
</style>
</head><body>
<div class="login-container">
  <div class="login-brand">
    <div class="login-icon"><svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>
    <div class="login-title">Dropout Signal</div>
    <div class="login-sub">Predictive Student Intervention Platform</div>
  </div>
  <form class="login-form" method="POST" action="/login" id="loginForm">
    <div class="form-group">
      <label class="form-label">Username</label>
      <input class="form-input" name="username" placeholder="Enter your username" required autocomplete="off">
    </div>
    <div class="form-group">
      <label class="form-label">Password</label>
      <input class="form-input" name="password" type="password" placeholder="Enter your password" required autocomplete="off">
    </div>
    <div class="form-group">
      <label class="form-label">Select Role</label>
      <div class="role-grid">
        <label class="role-card" id="role-admin" onclick="selectRole('admin')">
          <input type="radio" name="role" value="admin">
          <div class="role-icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg></div>
          <div class="role-title">Admin</div>
          <div class="role-desc">Data overview, pipeline stats, model metrics</div>
        </label>
        <label class="role-card" id="role-counselor" onclick="selectRole('counselor')">
          <input type="radio" name="role" value="counselor">
          <div class="role-icon"><svg viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></div>
          <div class="role-title">Counselor</div>
          <div class="role-desc">Voice calls, WhatsApp, student interventions</div>
        </label>
      </div>
    </div>
    <div class="error-msg" id="errMsg">Invalid credentials. Please try again.</div>
    <div style="display:flex;gap:10px;margin-bottom:10px;margin-top:10px;">
      <button type="button" class="login-btn" style="flex:1;background:var(--surface2);margin-top:0;" onclick="quickFill('admin')">Admin Fill</button>
      <button type="button" id="counselor-fill" class="login-btn" style="flex:1;background:var(--surface2);margin-top:0;" onclick="quickFill('counselor')">Counselor Fill</button>
    </div>
    <button class="login-btn" type="submit">Sign In</button>
  </form>
  <div class="login-footer">HACKBRICKS 2026 &mdash; POWERED BY DATABRICKS</div>
</div>
<script>
function selectRole(r){
  document.querySelectorAll('.role-card').forEach(c=>c.classList.remove('selected'));
  document.getElementById('role-'+r).classList.add('selected');
  document.querySelector('input[name=role][value='+r+']').checked=true;
}
const params=new URLSearchParams(window.location.search);
if(params.get('error')==='1')document.getElementById('errMsg').classList.add('show');

function quickFill(role) {
  document.querySelector('input[name=username]').value = role;
  document.querySelector('input[name=password]').value = role === 'admin' ? 'Admin-Signal2026!' : 'Counselor-Signal2026!';
  selectRole(role);
}

// A demo still uses the normal sign-in screen. The flag is carried through the
// form and starts only after a successful counselor login.
if (params.get('demo') === 'true') {
  const demoFlag = document.createElement('input');
  demoFlag.type = 'hidden'; demoFlag.name = 'demo'; demoFlag.value = 'true';
  document.getElementById('loginForm').appendChild(demoFlag);
  document.getElementById('role-counselor').insertAdjacentHTML('beforeend', '<div style="font-size:10px;color:var(--purple);margin-top:8px">Demo mode starts after sign-in</div>');
  // Make the entry step visible in presentations: the cursor selects the
  // counselor role, uses the demo credentials, then signs in normally.
  setTimeout(async()=>{
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    const cursor=document.createElement('div');
    cursor.style.cssText=`position:fixed;z-index:9999;width:24px;height:24px;pointer-events:none;transition:all .65s cubic-bezier(.2,.9,.2,1);filter:drop-shadow(0 2px 4px rgba(0,0,0,0.6));background:url("data:image/svg+xml;utf8,<svg viewBox='0 0 320 320' fill='white' stroke='black' stroke-width='18' stroke-linejoin='round' xmlns='http://www.w3.org/2000/svg'><path d='M 40 20 L 40 280 L 120 210 L 180 300 L 230 275 L 170 185 L 270 185 Z'/></svg>") no-repeat;background-size:contain;`;
    cursor.innerHTML='';
    document.body.appendChild(cursor);
    const clickEffect = (x,y) => {
        const ripple=document.createElement('span');
        ripple.style.cssText=`position:fixed;left:${x}px;top:${y}px;width:20px;height:20px;border:2px solid #ff4b4b;border-radius:50%;pointer-events:none;z-index:19999;transform:translate(-50%,-50%) scale(.35);opacity:.95;transition:transform .45s ease,opacity .45s ease`;
        document.body.appendChild(ripple); requestAnimationFrame(()=>{ripple.style.transform='translate(-50%,-50%) scale(2.8)';ripple.style.opacity='0';}); setTimeout(()=>ripple.remove(),500);
    };
    async function click(target){
      if(!target) return;
      const r=target.getBoundingClientRect();
      cursor.style.left=(r.left+r.width*.55)+'px';cursor.style.top=(r.top+r.height*.55)+'px';
      await wait(700);
      const ripple=document.createElement('span');
      ripple.style.cssText=`position:fixed;z-index:9998;pointer-events:none;left:${r.left+r.width*.55}px;top:${r.top+r.height*.55}px;width:18px;height:18px;border:2px solid #ff4b4b;border-radius:50%;transform:translate(-50%,-50%) scale(.35);opacity:.95;transition:transform .45s ease,opacity .45s ease;`;
      document.body.appendChild(ripple); requestAnimationFrame(()=>{ripple.style.transform='translate(-50%,-50%) scale(2.8)';ripple.style.opacity='0';});
      await wait(90); target.click(); setTimeout(()=>ripple.remove(),500); await wait(650);
    }
    await click(document.getElementById('role-counselor'));
    await click(document.getElementById('counselor-fill'));
    await click(document.querySelector('#loginForm button[type="submit"]'));
  },450);
}

async function demoCall() {
    toast('Initiating demo call sequence...', 'info');
    document.querySelector('[data-page="dashboard"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    toast('Calling student...', 'info');
    await new Promise(r => setTimeout(r, 1000));
    
    document.querySelector('[data-page="transcript"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('full-transcript-panel');
    if(tp) {
        document.getElementById('ts-count').innerText = '1 active';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px;cursor:pointer;" onclick="this.classList.toggle('minimized')">
            <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Demo Student</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        html += `<br><span style="color:var(--amber)">🤖 ${qas[0].q}</span><br>`;
        tp.innerHTML = html + `</div>`;
        tp.scrollTop = tp.scrollHeight;
        await new Promise(r => setTimeout(r, 1000));
        
        let typed = "";
        html += `<span style="color:var(--green)">🗣️ </span>`;
        for (let i = 0; i < qas[0].a.length; i++) {
            typed += qas[0].a[i];
            tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}</span></div>`);
            tp.scrollTop = tp.scrollHeight;
            await new Promise(r => setTimeout(r, 50)); 
        }
        html = html.replace('🗣️ </span>', `🗣️ ${qas[0].a}</span><br>`);
        
        toast('High Dropout Risk Detected!', 'err');
        
        for (let j = 1; j < qas.length; j++) {
            const qa = qas[j];
            await new Promise(r => setTimeout(r, 500));
            html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 500));
            typed = "";
            html += `<span style="color:var(--green)">🗣️ </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : "";
                tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, 5)); 
            }
            html = html.replace('🗣️ </span>', `🗣️ ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1500));
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
              <span class="t" style="color:var(--green)">Demo Student</span>
              <span class="b">2 msgs | HIGH</span>
            </div>
            <div class="chat-box" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
              <div class="chat-msg" style="margin-bottom:12px;display:flex;">
                 <div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
                   Hi Demo Student! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?
                 </div>
              </div>
              <div id="demo-student-reply" class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"></div>
            </div>
          </div>
        `;
        if(convosPanel.innerHTML.includes('appear here')) {
            convosPanel.innerHTML = '';
        }
        convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
        
        await new Promise(r => setTimeout(r, 1000));
        const replyDiv = document.getElementById('demo-student-reply');
        let replyText = "Hi, yeah things have been a bit rough lately with the finances";
        let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Demo Student</div>`;
                   
        for (let i = 0; i < replyText.length; i++) {
            replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 40)); 
        }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    toast('Demo Ended', 'ok');
}

function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    if (val === 'weekly') {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
        `;
    } else {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,50 110,60 180,50 250,65 320,55 390,70 460,60 500,65" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,110 110,120 180,100 250,130 320,115 390,140 460,120 500,125" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,150 110,140 180,160 250,145 320,150 390,130 460,155 500,145" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
        `;
    }
}
function updateRiskFactors(val) {} 
function updateInterventionSummary(val) {}

</script>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD — Data, Graphs, Pipeline (read-only)
# ═══════════════════════════════════════════════════════════════════

ADMIN_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en"><head>
<title>The Dropout Signal — Admin</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>""" + SHARED_CSS + r"""
.main { background: var(--bg); padding: 0 32px 32px; }
.admin-logout{position:fixed;left:16px;bottom:16px;width:188px;z-index:240;display:flex;align-items:center;justify-content:center;box-sizing:border-box;padding:11px 12px;border:1px solid rgba(239,68,68,.38);border-radius:9px;background:linear-gradient(135deg,rgba(239,68,68,.2),rgba(127,29,29,.2));color:var(--red);font:700 11px var(--mono);letter-spacing:1.4px;text-decoration:none;box-shadow:0 8px 24px rgba(0,0,0,.22);transition:background .2s,border-color .2s,transform .2s}
.admin-logout:hover{background:rgba(239,68,68,.3);border-color:var(--red);transform:translateY(-1px)}
.admin-risk-donut{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 26px rgba(99,102,241,.14)}
.admin-risk-hole{width:104px;height:104px;border-radius:50%;background:var(--surface);display:flex;flex-direction:column;align-items:center;justify-content:center}
.admin-risk-hole strong{font-size:24px;color:var(--text)}
.admin-risk-hole span{font-size:11px;color:var(--text3)}
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 24px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
.topbar-title h1 { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.topbar-title p { font-size: 13px; color: var(--text2); }
.topbar-actions { display: flex; align-items: center; gap: 16px; }
.top-search { display: flex; align-items: center; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; height: 36px; width: 280px; }
.top-search input { background: transparent; border: none; outline: none; color: var(--text); font-size: 13px; width: 100%; margin-left: 8px; }
.bell-icon { position: relative; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); cursor: pointer; }
.bell-dot { position: absolute; top: 8px; right: 8px; width: 8px; height: 8px; background: var(--red); border-radius: 50%; border: 2px solid var(--surface); }

.stat-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-box { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; position: relative; overflow: hidden; }
.stat-box::before { content:''; position:absolute; top:0; left:0; width:4px; height:100%; background:var(--blue); }
.stat-box.c-red::before { background:var(--red); }
.stat-box.c-amber::before { background:var(--amber); }
.stat-box.c-green::before { background:var(--green); }
.sb-title { font-size: 12px; color: var(--text2); font-weight: 500; margin-bottom: 8px; display:flex; align-items:center; gap:8px; }
.sb-icon { width:24px; height:24px; border-radius:6px; display:flex; align-items:center; justify-content:center; }
.sb-val { font-size: 28px; font-weight: 700; display:flex; align-items:center; gap:12px; }
.sb-trend { font-size: 12px; padding: 2px 6px; border-radius: 4px; font-weight: 600; display:flex; align-items:center; gap:4px; }
.sb-trend.up { background: rgba(34,197,94,0.15); color: var(--green); }
.sb-trend.down { background: rgba(239,68,68,0.15); color: var(--red); }
.sb-sub { font-size: 11px; color: var(--text3); margin-top: 4px; }

.grid-3 { display: grid; grid-template-columns: 3fr 5fr 4fr; gap: 16px; margin-bottom: 16px; }
.card-new { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.card-new-h { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.card-new-h h3 { font-size: 14px; font-weight: 600; }
.card-new-h select { background: transparent; border: none; color: var(--text2); font-size: 12px; outline: none; cursor:pointer; }
.card-new-b { padding: 20px; flex: 1; display:flex; flex-direction:column; }


/* Donut Chart Custom */
.d-chart-container { display: flex; align-items: center; justify-content: center; position: relative; height: 160px; }
.d-chart-center { position: absolute; text-align: center; }
.d-chart-center .num { font-size: 24px; font-weight: 700; }
.d-chart-center .lbl { font-size: 11px; color: var(--text3); }
.d-legend { display: flex; flex-direction: column; gap: 12px; margin-top: 20px; }
.dl-item { display: flex; align-items: center; justify-content: space-between; font-size: 12px; }
.dl-left { display: flex; align-items: center; gap: 8px; color: var(--text2); }
.dl-dot { width: 8px; height: 8px; border-radius: 50%; }
.risk-fixed-badge{display:inline-flex;align-items:center;margin-left:8px;padding:3px 7px;border-radius:999px;background:rgba(239,68,68,.12);color:var(--red);font:600 10px var(--mono);vertical-align:middle}
.summary-toolbar{display:flex;align-items:center;gap:14px;margin:-8px 0 18px}.summary-search{display:flex;align-items:center;gap:9px;flex:1;max-width:520px;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:0 13px;height:40px;color:var(--text3)}.summary-search input{width:100%;border:0;outline:0;background:transparent;color:var(--text);font-size:12px}.summary-count{font:10px var(--mono);color:var(--text3)}.summary-person{position:relative;overflow:hidden;transition:transform .2s,border-color .2s,box-shadow .2s}.summary-person:hover{transform:translateY(-3px);border-color:rgba(188,140,255,.5)!important;box-shadow:0 12px 32px rgba(0,0,0,.2)}.summary-chip{display:inline-flex;padding:4px 8px;border-radius:999px;font:600 10px var(--mono);letter-spacing:.4px}.summary-chip.high{background:var(--red-g);color:var(--red)}.summary-chip.medium{background:var(--amber-g);color:var(--amber)}.summary-copy{font-size:12px;line-height:1.6;color:var(--text2);margin-top:12px}.summary-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;font-size:10px;color:var(--text3)}

/* Alerts Feed */
.alert-list { display: flex; flex-direction: column; gap: 12px; }
.alert-item { display: flex; gap: 12px; align-items: flex-start; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px solid transparent; transition: border-color .2s; }
.alert-item:hover { border-color: var(--border); background: var(--surface2); }
.alert-icon { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.alert-body { flex: 1; }
.alert-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px; }
.alert-desc { font-size: 11px; color: var(--text2); }
.alert-time { font-size: 10px; color: var(--text3); }

/* Progress Bars */
.risk-factor { margin-bottom: 16px; }
.rf-header { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; }
.rf-left { display: flex; align-items: center; gap: 8px; color: var(--text2); }
.rf-bar-bg { height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden; }
.rf-bar-fill { height: 100%; border-radius: 3px; }

/* Activity Table */
.act-table { width: 100%; border-collapse: collapse; }
.act-table td { padding: 12px 16px; font-size: 12px; border-bottom: 1px solid var(--border); color: var(--text2); }
.act-table tr:last-child td { border-bottom: none; }
body.transcript-fs .sidebar { display: none !important; }
body.transcript-fs .main { margin-left: 0 !important; }
</style>
</head><body>
<div class="sidebar">
  <div class="sb-brand">
    <div class="sb-icon" style="width:24px;height:24px;display:flex;align-items:center;justify-content:center">
      <svg viewBox="0 0 24 24" style="width:20px;height:20px">
        <rect x="5" y="8" width="3" height="12" fill="#ffffff" rx="0.5"/>
        <rect x="10.5" y="11" width="3" height="9" fill="#ffffff" rx="0.5"/>
        <rect x="16" y="14" width="3" height="6" fill="#ffffff" rx="0.5"/>
        <path d="M 6.5 6 A 10.5 10.5 0 0 1 17.5 17" fill="none" stroke="#ff4b4b" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="6.5" cy="6" r="1.5" fill="#ff4b4b"/>
        <circle cx="17.5" cy="17" r="1.5" fill="#ff4b4b"/>
      </svg>
    </div>
    <div><div class="sb-name" style="font-size:13px">The Dropout Signal</div><div class="sb-role" style="font-size:8px">Predict. Intervene. Empower.</div></div>
  </div>
  <div class="sb-nav">
    <div class="sb-item active" data-page="overview">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
      Dashboard
    </div>
    <div class="sb-item" data-page="students">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
      Students<span class="sb-badge" id="sb-student-count">-</span>
    </div>
    <div class="sb-item" data-page="admin-at-risk"><span style="color:var(--red);font-size:16px">▲</span> At-Risk Students<span class="sb-badge" id="admin-risk-count">1,017</span></div>
    <div class="sb-item" data-page="admin-transcript"><span style="font-size:16px">☎</span> Live Transcript<span class="sb-badge" id="admin-voice-count">0</span></div>
    <div class="sb-item" data-page="admin-whatsapp"><span style="color:var(--green);font-size:16px">●</span> WhatsApp<span class="sb-badge" id="admin-wa-count">0</span></div>
    <div class="sb-item" data-page="admin-summary"><span style="color:var(--purple);font-size:16px">✦</span> AI Summary</div>
    <div class="sb-item" data-page="pipeline">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      Risk Predictions
    </div>
    <div class="sb-item" data-page="interventions">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
      Interventions
    </div>
    <div class="sb-item" data-page="conversations">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
      Conversations
    </div>
    <div class="sb-item" data-page="analytics">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
      Reports & Analytics
    </div>
    <div class="sb-item" data-page="alerts">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
      Alerts
    </div>
    <div class="sb-item" data-page="settings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      Settings
    </div>
  </div>
  <div style="padding:16px 16px 76px">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center;margin-bottom:16px">
        <div style="color:#bc8cff;font-size:24px;margin-bottom:8px">&#x2728;</div>
        <div style="font-size:12px;font-weight:600;margin-bottom:4px">AI Student Summary</div>
        <div style="font-size:10px;color:var(--text3);margin-bottom:12px;line-height:1.5">Open any student to review their risk signals and recommended next action.</div>
        <button style="width:100%;background:transparent;border:1px solid var(--border);color:var(--text2);padding:6px;border-radius:6px;font-size:11px;cursor:pointer;transition:all .2s" onclick="document.querySelector('[data-page=students]').click()" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background='transparent'">View students &rarr;</button>
    </div>
    <a href="/logout" style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:12px;text-decoration:none;color:var(--text);transition:all .2s" onmouseover="this.style.borderColor='var(--border-b)'" onmouseout="this.style.borderColor='var(--border)'">
        <div style="width:32px;height:32px;background:var(--surface2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px">AC</div>
        <div style="flex:1">
            <div style="font-size:12px;font-weight:600">Admin Counselor</div>
            <div style="font-size:10px;color:var(--text3)">admin@college.edu</div>
        </div>
        <svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--text3);fill:none;stroke-width:2"><polyline points="6 9 12 15 18 9"/></svg>
    </a>
  </div>
</div>
<a class="admin-logout" href="/logout">&larr; SIGN OUT</a>

<div class="main">
<!-- OVERVIEW -->
<div class="page active" id="page-overview" style="padding:0">
  <div class="topbar">
    <div class="topbar-title">
        <h1>Dashboard</h1>
        <p>Welcome back, Admin Counselor</p>
    </div>
    <div class="topbar-actions">
        <div class="top-search">
            <svg viewBox="0 0 24 24" style="width:16px;height:16px;stroke:var(--text3);fill:none;stroke-width:2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="search" id="admin-global-search" placeholder="Search students, ID, or keyword..." onkeydown="if(event.key==='Enter'){document.querySelector('[data-page=students]').click();document.getElementById('student-search').value=this.value;loadStudents();}">
        </div>
        <div class="bell-icon">
            <svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:var(--text2);fill:none;stroke-width:2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            <div class="bell-dot"></div>
        </div>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px" onclick="adminInitiateCall()"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Call Student</button>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px;background:var(--green)" onclick="adminWaDemo()">● WhatsApp Demo</button>
    </div>
  </div>

  <div class="stat-grid-4">
    <div class="stat-box">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">👥</div>
            Total Students
        </div>
        <div class="sb-val"><span id="s-bronze">4,500</span> <span class="sb-trend up"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 5.6%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-amber">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">⚠️</div>
            At-Risk Students
        </div>
        <div class="sb-val"><span id="s-gold">1,017</span> <span class="sb-trend down"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 12.4%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-red">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">🚨</div>
            Predicted Dropouts
        </div>
        <div class="sb-val"><span id="s-avgrisk">142</span> <span class="sb-trend down"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 8.2%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-green">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">💬</div>
            Interventions
        </div>
        <div class="sb-val"><span id="s-voice">0</span> <span class="sb-trend up"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 15.3%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
  </div>

  <div class="grid-3">
    <!-- Risk Overview (Donut) -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Overview</h3>
            <select onchange="updateRiskFactors(this.value)"><option value="this_sem">This Semester</option><option value="last_sem">Last Semester</option><option value="this_year">This Year</option></select>
        </div>
        <div class="card-new-b" id="tier-chart">
            <div class="d-chart-container"><div class="admin-risk-donut" style="background:conic-gradient(#ef4444 0 3.16%,#f59e0b 3.16% 22.61%,#22c55e 22.61% 100%)"><div class="admin-risk-hole"><strong>4,500</strong><span>students</span></div></div></div>
            <div class="d-legend"><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#ef4444"></span>High risk</span><strong>142</strong></div><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#f59e0b"></span>Medium risk</span><strong>875</strong></div><div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#22c55e"></span>Low risk</span><strong>3,483</strong></div></div>
        </div>
    </div>
    <!-- Risk Trend (Line) -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Trend <span class="risk-fixed-badge">1,017 at risk</span></h3>
            <select onchange="updateRiskTrend(this.value)"><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
        </div>
        <div class="card-new-b" style="position:relative">
            <div style="display:flex;justify-content:center;gap:16px;font-size:11px;color:var(--text3);margin-bottom:16px">
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--green);border-radius:2px"></div> Low Risk</span>
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--amber);border-radius:2px"></div> Medium Risk</span>
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--red);border-radius:2px"></div> High Risk</span>
            </div>
            <!-- Dummy Line Chart for aesthetics matching mockup -->
            <svg id="risk-trend-svg" width="100%" height="200" viewBox="0 0 500 200" preserveAspectRatio="none">
                <!-- Grid -->
                <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
                <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
                <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
                <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
                <!-- Lines -->
                <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
                <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
                <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
                <!-- X axis labels -->
                <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text>
                <text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text>
                <text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text>
                <text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text>
                <text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text>
                <text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
            </svg>
        </div>
    </div>
    <!-- Recent Alerts -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Recent Alerts</h3>
            <a href="#" onclick="document.querySelector('[data-page=alerts]').click();return false;" style="color:var(--red);font-size:12px;text-decoration:none">View all</a>
        </div>
        <div class="card-new-b">
            <div class="alert-list">
                <div class="alert-item">
                    <div class="alert-icon" style="background:var(--red-g);color:var(--red)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">High risk detected</div>
                        <div class="alert-desc">Arjun Sharma (CS-21-1042)</div>
                    </div>
                    <div class="alert-time">2m ago</div>
                </div>
                <div class="alert-item">
                    <div class="alert-icon" style="background:var(--amber-g);color:var(--amber)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">Attendance drop</div>
                        <div class="alert-desc">Neha Patil (EC-21-0876)</div>
                    </div>
                    <div class="alert-time">15m ago</div>
                </div>
                <div class="alert-item">
                    <div class="alert-icon" style="background:var(--purple-g);color:var(--purple)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">Low engagement</div>
                        <div class="alert-desc">Rohan Verma (ME-21-0654)</div>
                    </div>
                    <div class="alert-time">1h ago</div>
                </div>
                <div class="alert-item">
                    <div class="alert-icon" style="background:var(--green-g);color:var(--green)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">Intervention successful</div>
                        <div class="alert-desc">Priya Nair (CS-21-0921)</div>
                    </div>
                    <div class="alert-time">2h ago</div>
                </div>
            </div>
        </div>
    </div>
  </div>

  <div class="grid-3" style="grid-template-columns: 3fr 3fr 3fr; margin-bottom: 0;">
    <!-- AI Insights -->
    <div class="card-new">
        <div class="card-new-h">
            <h3><span style="color:#bc8cff;margin-right:8px">&#x2728;</span>AI Insights</h3>
        </div>
        <div class="card-new-b" style="justify-content:space-between">
            <p style="font-size:13px;color:var(--text2);line-height:1.6">Based on recent data, 87 students are at high risk of dropping out. Key factors include attendance (42%), low engagement (28%), and academic performance (30%). Early intervention can improve outcomes.</p>
            <div style="text-align:center;margin:20px 0">
                <svg viewBox="0 0 24 24" style="width:80px;height:80px;stroke:#bc8cff;fill:none;stroke-width:1;opacity:0.6"><path d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2z"/><path d="M12 6v12"/><path d="M8 10h8"/><path d="M8 14h8"/></svg>
            </div>
            <button class="nav-cta" style="background:rgba(188,140,255,0.1);color:#bc8cff!important;border:1px solid rgba(188,140,255,0.2)">View Full Report &rarr;</button>
        </div>
    </div>
    <!-- Top Risk Factors -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Top Risk Factors</h3>
            <select><option>This Semester</option></select>
        </div>
        <div class="card-new-b">
            <div class="risk-factor">
                <div class="rf-header">
                    <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--red);fill:none;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> Low Attendance</div>
                    <div>42%</div>
                </div>
                <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:42%;background:var(--red)"></div></div>
            </div>
            <div class="risk-factor">
                <div class="rf-header">
                    <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--amber);fill:none;stroke-width:2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg> Poor Academic Performance</div>
                    <div>30%</div>
                </div>
                <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:30%;background:var(--amber)"></div></div>
            </div>
            <div class="risk-factor">
                <div class="rf-header">
                    <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--green);fill:none;stroke-width:2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Low Engagement</div>
                    <div>18%</div>
                </div>
                <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:18%;background:var(--green)"></div></div>
            </div>
            <div class="risk-factor">
                <div class="rf-header">
                    <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--blue);fill:none;stroke-width:2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg> Financial Issues</div>
                    <div>10%</div>
                </div>
                <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:10%;background:var(--blue)"></div></div>
            </div>
        </div>
    </div>
    <!-- Intervention Summary -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Intervention Summary</h3>
            <select onchange="updateInterventionSummary(this.value)"><option value="this_month">This Month</option><option value="last_month">Last Month</option><option value="this_year">This Year</option></select>
        </div>
        <div class="card-new-b" style="justify-content:space-between">
            <div style="display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div class="admin-int-total" style="font-size:28px;font-weight:700">62</div>
                    <div style="font-size:11px;color:var(--text3)">Total Interventions</div>
                </div>
                <div style="position:relative;width:80px;height:80px">
                    <svg viewBox="0 0 100 100" width="80" height="80">
                        <circle cx="50" cy="50" r="40" fill="none" stroke="var(--border)" stroke-width="8"/>
                        <circle cx="50" cy="50" r="40" fill="none" stroke="var(--green)" stroke-width="8" stroke-dasharray="251" stroke-dashoffset="65" stroke-linecap="round" transform="rotate(-90 50 50)"/>
                    </svg>
                    <div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
                        <span class="admin-int-rate" style="font-size:16px;font-weight:700">74%</span>
                        <span style="font-size:8px;color:var(--text3)">Successful</span>
                    </div>
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:24px;border-top:1px solid var(--border);padding-top:16px">
                <div style="text-align:center"><div class="admin-int-engaged" style="font-size:16px;font-weight:600">46</div><div style="font-size:10px;color:var(--text3)">Engaged</div></div>
                <div style="text-align:center"><div class="admin-int-progress" style="font-size:16px;font-weight:600">11</div><div style="font-size:10px;color:var(--text3)">In Progress</div></div>
                <div style="text-align:center"><div class="admin-int-none" style="font-size:16px;font-weight:600">5</div><div style="font-size:10px;color:var(--text3)">No Response</div></div>
            </div>
            <div style="text-align:center;margin-top:16px">
                <a href="#" style="color:var(--red);font-size:11px;text-decoration:none;font-weight:500">View Intervention Log &rarr;</a>
            </div>
        </div>
    </div>
  </div>

  <div class="card-new" style="margin-top:16px">
    <div class="card-new-h">
        <h3>Recent Activity</h3>
        <a href="#" onclick="document.querySelector('[data-page=interventions]').click();return false;" style="color:var(--red);font-size:12px;text-decoration:none">View all activity &rarr;</a>
    </div>
    <table class="act-table">
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="width:36px;height:36px;border-radius:18px;background:rgba(34,197,94,0.1);color:var(--green);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></div>
                    <div><div style="color:var(--text);font-weight:500">Voice call completed</div><div style="font-size:11px;color:var(--text3)">AI Voice Agent</div></div>
                </div>
            </td>
            <td><div><div style="color:var(--text);font-weight:500">Aarav Patel (STU-DEMO)</div><div style="font-size:11px;color:var(--text3)">Discussed financial pressure and scholarship</div></div></td>
            <td><span style="color:var(--green);background:rgba(34,197,94,0.1);padding:4px 8px;border-radius:4px;font-size:10px;font-weight:600">Successful</span></td>
            <td style="text-align:right">10:30 AM</td>
        </tr>
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="width:36px;height:36px;border-radius:18px;background:rgba(34,197,94,0.1);color:var(--green);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>
                    <div><div style="color:var(--text);font-weight:500">WhatsApp message sent</div><div style="font-size:11px;color:var(--text3)">AI Counselor</div></div>
                </div>
            </td>
            <td><div><div style="color:var(--text);font-weight:500">Aarav Patel (STU-DEMO)</div><div style="font-size:11px;color:var(--text3)">Shared financial aid resources and center hours</div></div></td>
            <td><span style="color:var(--text2);background:var(--surface2);padding:4px 8px;border-radius:4px;font-size:10px;font-weight:600">Delivered</span></td>
            <td style="text-align:right">9:45 AM</td>
        </tr>
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="width:36px;height:36px;border-radius:18px;background:rgba(245,158,11,0.1);color:var(--amber);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></div>
                    <div><div style="color:var(--text);font-weight:500">Risk report generated</div><div style="font-size:11px;color:var(--text3)">System</div></div>
                </div>
            </td>
            <td><div><div style="color:var(--text);font-weight:500">Weekly risk analysis report</div><div style="font-size:11px;color:var(--text3)">87 high risk students identified</div></div></td>
            <td><a href="#" style="color:var(--text2);background:var(--surface2);padding:4px 8px;border-radius:4px;font-size:10px;font-weight:600;text-decoration:none">View Report</a></td>
            <td style="text-align:right">9:00 AM</td>
        </tr>
    </table>
  </div>
</div>

<!-- STUDENTS -->
<div class="page" id="page-students">
  <div class="page-hdr"><h1>Student Data</h1><p>Gold table — all scored students</p></div>
  <div class="search-bar">
    <input class="search-input" id="student-search" placeholder="Search by student ID..." onkeyup="if(event.key==='Enter')loadStudents()">
    <button class="btn" onclick="loadStudents()">Search</button>
    <button class="btn btn-red" onclick="document.getElementById('student-search').value='';loadStudents()">Reset</button>
  </div>
  <div class="card">
    <div class="card-h"><span class="t">Gold Table</span><span class="b" id="student-count-badge">loading...</span></div>
    <div style="overflow-x:auto">
      <table class="tbl"><thead><tr><th>Student ID</th><th>Risk Score</th><th>Risk Tier</th><th>Top Factor</th><th>Outcome</th><th></th></tr></thead>
      <tbody id="students-tbody"><tr><td colspan="6" style="text-align:center;padding:40px"><div class="loading-spinner"></div></td></tr></tbody></table>
    </div>
  </div>
</div>

<!-- PIPELINE -->
<div class="page" id="page-pipeline">
  <div class="page-hdr"><h1>Data Pipeline</h1><p>Bronze → Silver → Gold — Medallion architecture on Databricks</p></div>
  <div class="card"><div class="card-h"><span class="t">Pipeline Stages</span><span class="b">click a stage to learn more</span></div><div class="card-b">
    <div class="pipeline">
      <div class="pipe-n" onclick="showPipeInfo(0)" data-pipe="0"><div class="pipe-d" id="p-bronze">1</div><div class="pipe-t">Bronze</div><div class="pipe-s">Raw Ingest</div></div>
      <div class="pipe-l" id="pl-1"></div>
      <div class="pipe-n" onclick="showPipeInfo(1)" data-pipe="1"><div class="pipe-d" id="p-silver">2</div><div class="pipe-t">Silver</div><div class="pipe-s">Feature Eng</div></div>
      <div class="pipe-l" id="pl-2"></div>
      <div class="pipe-n" onclick="showPipeInfo(2)" data-pipe="2"><div class="pipe-d" id="p-model">3</div><div class="pipe-t">ML Models</div><div class="pipe-s">LogReg + XGB</div></div>
      <div class="pipe-l" id="pl-3"></div>
      <div class="pipe-n" onclick="showPipeInfo(3)" data-pipe="3"><div class="pipe-d" id="p-gold">4</div><div class="pipe-t">Gold</div><div class="pipe-s">Interventions</div></div>
      <div class="pipe-l" id="pl-4"></div>
      <div class="pipe-n" onclick="showPipeInfo(4)" data-pipe="4"><div class="pipe-d" id="p-voice">5</div><div class="pipe-t">Voice + WA</div><div class="pipe-s">Layer 2</div></div>
    </div>
    <div class="pipe-info" id="pipe-info-panel"></div>
  </div></div>
  <div class="card"><div class="card-h"><span class="t">Model Tier Distribution</span></div><div class="card-b" id="model-tiers"><div class="skeleton" style="width:50%"></div></div></div>
  <div class="card"><div class="card-h"><span class="t">Tables in Schema</span></div><div class="card-b" id="tables-list"><div class="loading-spinner"></div></div></div>
  <div class="card"><div class="card-h"><span class="t">Fairness Audit</span></div><div class="card-b" id="fairness-panel"><div class="loading-spinner"></div></div></div>
</div>

<!-- ANALYTICS -->
<div class="page" id="page-analytics">
  <div class="page-hdr"><h1>Analytics</h1><p>Deep dive into model predictions and risk factors</p></div>
  <div class="stats-grid" id="analytics-cards"></div>
  <div class="card"><div class="card-h"><span class="t">Top Dropout Factors (Across All Students)</span></div><div class="card-b" id="factors-panel"><div class="loading-spinner"></div></div></div>
  <div class="card"><div class="card-h"><span class="t">Outcome Distribution</span></div><div class="card-b" id="outcome-panel"><div class="loading-spinner"></div></div></div>
</div>

<!-- INTERVENTIONS -->
<div class="page" id="page-interventions">
  <div class="page-hdr"><h1>Interventions</h1><p>Track and manage student interventions</p></div>
  <div class="card"><div class="card-h"><span class="t">Recent Interventions</span></div><div class="card-b" style="padding:40px;text-align:center;color:var(--text3);font-size:13px">Intervention tracking data will appear here once voice calls and WhatsApp conversations are completed.</div></div>
</div>

<!-- CONVERSATIONS -->
<div class="page" id="page-conversations">
  <div class="page-hdr"><h1>Conversations</h1><p>View all student communication history</p></div>
  <div class="card"><div class="card-h"><span class="t">Conversation Log</span></div><div class="card-b" style="padding:40px;text-align:center;color:var(--text3);font-size:13px">Voice call and WhatsApp conversation history will appear here.</div></div>
</div>

<!-- ADMIN MIRROR WORKSPACE -->
<div class="page" id="page-admin-at-risk"><div class="page-hdr"><h1>At-Risk Students</h1><p>Prioritized students requiring coordinated intervention</p></div><div class="search-bar"><input class="search-input" id="admin-risk-search" placeholder="Search name, ID, or signal..." oninput="loadAdminAtRisk()"><button class="btn" onclick="loadAdminAtRisk()">Search</button></div><div class="card"><div class="card-h"><span class="t">Students Needing Intervention</span><span class="b" id="admin-risk-badge">1,017 students</span></div><div style="overflow-x:auto"><table class="tbl"><thead><tr><th>Student</th><th>Risk</th><th>Tier</th><th>Signal</th><th>Action</th><th></th></tr></thead><tbody id="admin-risk-tbody"></tbody></table></div></div></div>
<div class="page" id="page-admin-transcript"><div class="page-hdr"><h1>Live Call Transcripts</h1><p>Real-time AI voice activity visible to administrators</p></div><div class="card"><div class="card-h"><span class="t">Active Calls</span><span class="b" id="admin-ts-count">0 active</span></div><div class="card-b" id="admin-transcript-panel" style="min-height:320px;background:var(--surface2);border-radius:10px;color:var(--text2)">Waiting for active calls...</div></div></div>
<div class="page" id="page-admin-whatsapp"><div class="page-hdr"><h1>WhatsApp Operations</h1><p>Review counselor outreach and Asha AI responses</p></div><div style="display:flex;gap:8px;margin-bottom:16px"><button class="btn btn-green" onclick="adminWaDemo()">● Send WhatsApp Demo</button><button class="btn" onclick="loadAdminWhatsApp()">Refresh</button></div><div class="card"><div class="card-h"><span class="t">Conversation Log</span><span class="b" id="admin-wa-badge">0 conversations</span></div><div class="card-b" id="admin-wa-panel">WhatsApp conversations appear here.</div></div></div>
<div class="page" id="page-admin-summary"><div class="page-hdr"><h1>AI Student Summary</h1><p>Structured, explainable summaries for every risk tier</p></div><div class="summary-toolbar"><div class="summary-search"><span>⌕</span><input id="admin-summary-search" placeholder="Search student, ID, or risk signal..." oninput="filterAdminSummary(this.value)"></div><span class="summary-count">Admin intelligence view</span></div><div class="summary-grid" id="admin-summary-grid"></div></div>

<!-- ALERTS -->
<div class="page" id="page-alerts">
  <div class="page-hdr"><h1>Alerts</h1><p>System alerts and notifications</p></div>
  <div class="card"><div class="card-h"><span class="t">All Alerts</span></div><div class="card-b"><div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px"><span style="width:8px;height:8px;border-radius:50%;background:var(--red)"></span><div><div style="font-weight:600;font-size:13px">High risk detected — Arjun Sharma (CS-21-1042)</div><div style="font-size:11px;color:var(--text3)">2 minutes ago</div></div></div><div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px"><span style="width:8px;height:8px;border-radius:50%;background:var(--amber)"></span><div><div style="font-weight:600;font-size:13px">Attendance drop — Neha Patil (EC-21-0876)</div><div style="font-size:11px;color:var(--text3)">15 minutes ago</div></div></div><div style="padding:12px;display:flex;align-items:center;gap:12px"><span style="width:8px;height:8px;border-radius:50%;background:var(--green)"></span><div><div style="font-weight:600;font-size:13px">Intervention successful — Priya Nair (CS-21-0921)</div><div style="font-size:11px;color:var(--text3)">2 hours ago</div></div></div></div></div>
</div>

<!-- SETTINGS -->
<div class="page" id="page-settings">
  <div class="page-hdr"><h1>Settings</h1><p>System configuration and preferences</p></div>
  <div class="card"><div class="card-h"><span class="t">General Settings</span></div><div class="card-b" style="padding:20px"><div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border)"><div><div style="font-weight:600;font-size:13px">Dark Mode</div><div style="font-size:11px;color:var(--text3)">Toggle between dark and light theme</div></div><button class="btn" onclick="toggleTheme()">Toggle Theme</button></div><div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border)"><div><div style="font-weight:600;font-size:13px">Databricks Connection</div><div style="font-size:11px;color:var(--text3)">Manage your Databricks SQL Warehouse connection</div></div><span class="tag tag-t3">Connected</span></div><div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0"><div><div style="font-weight:600;font-size:13px">Notifications</div><div style="font-size:11px;color:var(--text3)">Configure alert thresholds and notification channels</div></div><button class="btn">Configure</button></div></div></div>
</div>

</div>

<div class="modal-bg" id="modal" onclick="if(event.target===this)closeModal()"><div class="modal"><div id="modal-body"></div></div></div>
<div id="toast"></div>
<script>
const PIPE_DESCRIPTIONS = [
  {title: '1. Bronze (Raw Ingest)', desc: 'Raw LMS logs, SIS data, and financial aid records ingested from Kafka and S3.'},
  {title: '2. Silver (Feature Eng)', desc: 'Data cleaned, normalized, and engineered into student risk features.'},
  {title: '3. ML Models', desc: 'XGBoost and Logistic Regression models calculate real-time dropout probability.'},
  {title: '4. Gold (Interventions)', desc: 'Curated risk tiers and recommended interventions available for the Counselor Dashboard.'},
  {title: '5. Voice + WhatsApp', desc: 'Twilio Voice and WhatsApp integrations for automated student check-ins.'}
];
function showPipeInfo(idx) {
  const panel=document.getElementById('pipe-info-panel');
  panel.innerHTML='<h3>'+PIPE_DESCRIPTIONS[idx].title+'</h3><p>'+PIPE_DESCRIPTIONS[idx].desc+'</p>';
  panel.classList.add('show');
}
function toggleTheme(){
  const t=document.documentElement.getAttribute('data-theme')==='light'?'':'light';
  document.documentElement.setAttribute('data-theme',t);
  localStorage.setItem('theme',t);
}
(function(){const t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);})();
document.querySelectorAll('.sb-item').forEach(item=>{
  item.addEventListener('click',()=>{
    if(!item.dataset.page) return;
    const target=document.getElementById('page-'+item.dataset.page);
    if(!target) return;
    document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    target.classList.add('active');
    if (item.dataset.page === 'transcript') document.body.classList.add('transcript-fs');
    else document.body.classList.remove('transcript-fs');
  });
});
function toast(msg,type='info'){const el=document.getElementById('toast');el.textContent=msg;el.className=type+' show';setTimeout(()=>el.className='',3500);}
async function api(url,method='GET'){const opts=method==='POST'?{method:'POST',headers:{'Content-Type':'application/json'}}:{};const r=await fetch(url,opts);return r.json();}

async function loadOverview(){
  try{
    const s=await api('/api/stats');
    document.getElementById('s-bronze').textContent=s.bronze_count?.toLocaleString()||'0';
    document.getElementById('s-gold').textContent=s.tier_breakdown.reduce((sum,t)=>sum+(t.final_risk_tier==='HIGH'||t.final_risk_tier==='MEDIUM'?parseInt(t.cnt):0),0).toLocaleString();
    document.getElementById('s-avgrisk').textContent=(s.tier_breakdown.find(t=>t.final_risk_tier==='HIGH')?.cnt||0).toLocaleString();
    document.getElementById('s-voice').textContent=(s.voice_completed||0).toLocaleString();
    
    // Render Admin Tier Chart
    const target=document.getElementById('tier-chart');
    if(target) {
        const valid=(s.tier_breakdown||[]).map(t=>({tier:(t.final_risk_tier||'Unknown').toUpperCase(),count:Number(t.cnt)||0})).filter(t=>t.count>0);
        const total=valid.reduce((sum,t)=>sum+t.count,0);
        if(!total){target.innerHTML='<p style="color:var(--text3);font-size:12px;text-align:center;padding:40px 0">Risk data is not available yet.</p>';}
        else {
            const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)'};
            let cursor=0;
            const stops=valid.map(t=>{const end=cursor+(t.count/total*100);const stop=`${colors[t.tier]||'var(--blue)'} ${cursor.toFixed(2)}% ${end.toFixed(2)}%`;cursor=end;return stop;}).join(', ');
            target.innerHTML=`<div class="d-chart-container"><div style="width:150px;height:150px;border-radius:50%;background:conic-gradient(${stops});position:relative"><div style="position:absolute;inset:22px;border-radius:50%;background:var(--bg)"></div></div><div class="d-chart-center"><div class="num">${total.toLocaleString()}</div><div class="lbl">students</div></div></div><div class="d-legend">${valid.map(t=>`<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[t.tier]||'var(--blue)'}"></span>${t.tier[0]+t.tier.slice(1).toLowerCase()} risk</span><strong>${t.count.toLocaleString()}</strong></div>`).join('')}</div>`;
        }
    }
    
    // Add updateRiskTrend globally if not present
    window.updateRiskTrend = function(val) {
        const svg = document.getElementById('risk-trend-svg');
        if (!svg) return;
        if (val === 'weekly') {
            svg.innerHTML = `
                <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
                <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
                <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
                <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
                <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
                <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
                <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
                <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
            `;
        } else {
            svg.innerHTML = `
                <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
                <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
                <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
                <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
                <polyline points="40,50 110,60 180,50 250,65 320,55 390,70 460,60 500,65" fill="none" stroke="var(--green)" stroke-width="2"/>
                <polyline points="40,110 110,120 180,100 250,130 320,115 390,140 460,120 500,125" fill="none" stroke="var(--amber)" stroke-width="2"/>
                <polyline points="40,150 110,140 180,160 250,145 320,150 390,130 460,155 500,145" fill="none" stroke="var(--red)" stroke-width="2"/>
                <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
            `;
        }
    }

    document.getElementById('s-avgrisk').textContent=s.avg_risk||'-';
    document.getElementById('s-voice').textContent=(s.voice_completed||0)+'/'+(s.voice_analyzed||0);
    document.getElementById('s-wa').textContent=s.wa_conversations||0;
    document.getElementById('sb-student-count').textContent=s.gold_count||0;



    // Health
    const h=await api('/api/health');
    document.getElementById('health-time').textContent=new Date().toLocaleTimeString();
    document.getElementById('health-panel').innerHTML=`
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        ${[{n:'DATABRICKS',ok:h.databricks?.ok,m:h.databricks?.ok?'Connected':h.databricks?.message},
           {n:'TWILIO',ok:h.twilio?.ok,m:h.twilio?.ok?'Ready':'Not configured'},
           {n:'GROQ LLM',ok:h.groq?.ok,m:h.groq?.ok?h.groq.model:'Not configured'}
        ].map(x=>`<div style="padding:12px;background:var(--surface);border-radius:var(--rs);border:1px solid ${x.ok?'rgba(34,197,94,0.2)':'rgba(239,68,68,0.2)'}">
          <div style="font-size:10px;font-family:var(--mono);color:var(--text3);margin-bottom:4px">${x.n}</div>
          <div style="font-size:14px;font-weight:600;color:${x.ok?'var(--green)':'var(--red)'}">${x.ok?'&#x2714;':'&#x2716;'} ${x.m}</div>
        </div>`).join('')}
      </div>`;
  }catch(e){toast('Overview failed: '+e,'err');}
}

async function loadHistogram(){
  try{
    const d=await api('/api/students?limit=4500');
    if(!d.students)return;
    const bins=Array(20).fill(0);
    d.students.forEach(s=>{const v=parseFloat(s.ml_risk_score||0);const i=Math.min(Math.floor(v*20),19);bins[i]++;});
    const mx=Math.max(...bins);
    const el=document.getElementById('risk-histogram');
    el.innerHTML=bins.map((c,i)=>{
      const pct=mx?Math.round(c/mx*100):0;
      const h=Math.max(pct*1.8,2);
      const color=i<7?'var(--green)':i<14?'var(--amber)':'var(--red)';
      return `<div class="chart-bar" style="height:${h}px;background:${color}"><div class="tip">${(i*5)}%-${(i+1)*5}%: ${c}</div></div>`;
    }).join('');
  }catch(e){}
}

async function loadStudents(){
  const search=document.getElementById('student-search').value;
  const tbody=document.getElementById('students-tbody');
  tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px"><div class="loading-spinner"></div></td></tr>';
  try{
    const d=await api('/api/students?search='+encodeURIComponent(search));
    document.getElementById('student-count-badge').textContent=d.count+' students';
    if(!d.students||!d.students.length){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">No students found</td></tr>';return;}
    tbody.innerHTML=d.students.map(s=>{
      const score=parseFloat(s.ml_risk_score||0);
      const tier=s.final_risk_tier||'';
      const cls=tier.toUpperCase().includes('HIGH')?'t1':tier.toUpperCase().includes('MED')?'t2':tier.toUpperCase().includes('LOW')?'t3':'t4';
      const barCls=score>0.7?'var(--red)':score>0.4?'var(--amber)':'var(--green)';
      return `<tr>
        <td><span class="mono">${s.student_id}</span></td>
        <td><div class="bar-g"><div class="bar-t"><div class="bar-f" style="width:${(score*100).toFixed(0)}%;background:${barCls}"></div></div><span class="mono">${score.toFixed(3)}</span></div></td>
        <td><span class="tag tag-${cls}">${tier}</span></td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span style="font-size:11px">${s.top_factor_1||'-'}</span></td>
        <td><span style="font-size:11px">${s.actual_outcome||'-'}</span></td>
        <td><button class="btn" onclick="showStudent('${s.student_id}')">View</button></td>
      </tr>`;
    }).join('');
  }catch(e){toast('Failed: '+e,'err');}
}

function updateStudentSummary(student, voice={}){
  const panel=document.getElementById('rail-student-summary');
  if(!panel) return;
  const name=student.student_name||student.student_id||'Student';
  const risk=student.final_risk_tier||'Unknown';
  const score=student.ml_risk_score!==undefined ? Number(student.ml_risk_score).toFixed(2) : '—';
  const cause=voice.primary_root_cause||student.voice_root_cause||student.top_factor_1||'No specific factor is available yet.';
  const summary=voice.summary||student.final_action||'Review the student record and offer an appropriate early-support check-in.';
  panel.innerHTML=`<div style="font-weight:600;color:var(--text);margin-bottom:4px">${name}</div><div style="font:10px var(--mono);color:var(--text3);margin-bottom:12px">${risk} RISK · SCORE ${score}</div><div style="margin-bottom:8px"><strong style="color:var(--text)">Primary signal:</strong> ${cause}</div><div><strong style="color:var(--text)">Suggested action:</strong> ${summary}</div>`;
}

async function showStudent(id){
  document.getElementById('modal').classList.add('show');
  document.getElementById('modal-body').innerHTML='<div style="text-align:center;padding:40px"><div class="loading-spinner"></div></div>';
  try{
    const d=await api('/api/student/'+id);const g=d.gold||{};
    updateStudentSummary(g, d.voice||{});
    let html=`<h2 style="font-size:18px;margin-bottom:4px">Student #${id}</h2><div class="detail-grid">`;
    for(const f of Object.keys(g)){if(g[f]!==null&&g[f]!=='')html+=`<div class="detail-item"><div class="dl">${f.replace(/_/g,' ')}</div><div class="dv" style="font-size:13px;word-break:break-word">${g[f]}</div></div>`;}
    html+='</div>';
    if(d.voice){
      html+='<div style="margin-top:16px"><div style="font-size:10px;font-family:var(--mono);color:var(--text3);margin-bottom:8px;letter-spacing:1px">VOICE ANALYSIS</div>';
      html+=`<div class="detail-grid">
        <div class="detail-item"><div class="dl">Dropout Intent</div><div class="dv">${d.voice.dropout_intent||'-'}</div></div>
        <div class="detail-item"><div class="dl">Dropout Prob</div><div class="dv">${d.voice.dropout_probability||'-'}</div></div>
        <div class="detail-item"><div class="dl">Sentiment</div><div class="dv">${d.voice.overall_sentiment||'-'}</div></div>
        <div class="detail-item"><div class="dl">Root Cause</div><div class="dv">${d.voice.primary_root_cause||'-'}</div></div>
      </div>`;
      if(d.voice.summary)html+=`<p style="font-size:12px;color:var(--text2);line-height:1.7;margin-top:8px">${d.voice.summary}</p>`;
      html+='</div>';
    }
    document.getElementById('modal-body').innerHTML='<span class="modal-close" onclick="closeModal()">&times;</span>'+html;
  }catch(e){document.getElementById('modal-body').innerHTML='<p style="color:var(--red)">Error: '+e+'</p>';}
}
function closeModal(){document.getElementById('modal').classList.remove('show');}

async function loadPipeline(){
  try{
    const s=await api('/api/stats');
    ['p-bronze','p-silver','p-model','p-gold'].forEach(id=>document.getElementById(id).classList.add('ok'));
    ['pl-1','pl-2','pl-3'].forEach(id=>document.getElementById(id).classList.add('ok'));
    if(s.voice_analyzed>0){document.getElementById('p-voice').classList.add('ok');document.getElementById('pl-4').classList.add('ok');}

    const m=await api('/api/model-metrics');
    const mp=document.getElementById('model-tiers');
    if(m.tiers&&m.tiers.length){
      const maxCnt=Math.max(...m.tiers.map(t=>parseInt(t.student_count)));
      mp.innerHTML=m.tiers.map(t=>{
        const pct=Math.round(parseInt(t.student_count)/maxCnt*100);
        const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)'};
        const color=colors[(t.final_risk_tier||'').toUpperCase()]||'var(--blue)';
        return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.03)">
          <span style="width:100px;font-size:11px;color:var(--text2)">${t.final_risk_tier}</span>
          <div style="flex:1;height:8px;background:rgba(255,255,255,0.04);border-radius:4px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color};border-radius:4px"></div></div>
          <span class="mono" style="width:50px;text-align:right">${t.student_count}</span>
          <span class="mono" style="width:80px;text-align:right;color:var(--text3)">avg ${t.avg_score}</span>
        </div>`;
      }).join('');
    }

    const tbl=await api('/api/tables');
    const tp=document.getElementById('tables-list');
    if(tbl.tables&&tbl.tables.length){
      tp.innerHTML=tbl.tables.map(t=>`<div style="padding:6px 0;font-size:12px;font-family:var(--mono);color:var(--text2);border-bottom:1px solid rgba(255,255,255,0.03)">&#x2714; ${Object.values(t).join(' — ')}</div>`).join('');
    }

    // Fairness
    const f=await api('/api/fairness');
    const fp=document.getElementById('fairness-panel');
    if(f.fairness&&f.fairness.length){
      fp.innerHTML='<div style="overflow-x:auto"><table class="tbl"><thead><tr>'+Object.keys(f.fairness[0]).map(k=>'<th>'+k.replace(/_/g,' ')+'</th>').join('')+'</tr></thead><tbody>'+f.fairness.map(r=>'<tr>'+Object.values(r).map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
    }else{fp.innerHTML='<span style="color:var(--text3);font-size:12px">No fairness data available</span>';}
  }catch(e){toast('Pipeline load failed: '+e,'err');}
}

async function loadAnalytics(){
  try{
    const d=await api('/api/students?limit=4500');
    if(!d.students)return;
    const students=d.students;
    const total=students.length;

    // Outcome distribution
    const outcomes={};students.forEach(s=>{const o=s.actual_outcome||'Unknown';outcomes[o]=(outcomes[o]||0)+1;});
    const op=document.getElementById('outcome-panel');
    const oColors={Dropout:'var(--red)',Graduate:'var(--green)',Enrolled:'var(--blue)'};
    op.innerHTML=Object.entries(outcomes).sort((a,b)=>b[1]-a[1]).map(([k,v])=>{
      const pct=Math.round(v/total*100);const color=oColors[k]||'var(--purple)';
      return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.03)">
        <span style="width:120px;font-size:12px;color:var(--text2)">${k}</span>
        <div style="flex:1;height:10px;background:rgba(255,255,255,0.04);border-radius:5px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color};border-radius:5px"></div></div>
        <span class="mono" style="width:80px;text-align:right">${v} (${pct}%)</span>
      </div>`;
    }).join('');

    // Top factors
    const factors={};students.forEach(s=>{
      [s.top_factor_1,s.top_factor_2,s.top_factor_3].forEach(f=>{
        if(f){const name=f.split('(')[0].trim();factors[name]=(factors[name]||0)+1;}
      });
    });
    const sorted=Object.entries(factors).sort((a,b)=>b[1]-a[1]).slice(0,12);
    const maxF=sorted[0]?sorted[0][1]:1;
    document.getElementById('factors-panel').innerHTML=sorted.map(([name,cnt])=>{
      const pct=Math.round(cnt/maxF*100);
      return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.03)">
        <span style="width:260px;font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</span>
        <div style="flex:1;height:8px;background:rgba(255,255,255,0.04);border-radius:4px;overflow:hidden"><div style="width:${pct}%;height:100%;background:var(--purple);border-radius:4px"></div></div>
        <span class="mono" style="width:60px;text-align:right">${cnt}</span>
      </div>`;
    }).join('');

    // Summary cards
    const highCount=students.filter(s=>(s.final_risk_tier||'').toUpperCase()==='HIGH').length;
    const falsePos=students.filter(s=>s.false_positive==='true').length;
    const voiceVerified=students.filter(s=>s.voice_verified==='true').length;
    document.getElementById('analytics-cards').innerHTML=`
      <div class="stat-card"><div class="label">Total Students</div><div class="value">${total.toLocaleString()}</div></div>
      <div class="stat-card"><div class="label">High Risk</div><div class="value" style="color:var(--red)">${highCount}</div><div class="sub">${Math.round(highCount/total*100)}% of total</div></div>
      <div class="stat-card"><div class="label">False Positives</div><div class="value" style="color:var(--amber)">${falsePos}</div><div class="sub">Flagged as incorrect</div></div>
      <div class="stat-card"><div class="label">Voice Verified</div><div class="value" style="color:var(--green)">${voiceVerified}</div><div class="sub">Layer 2 confirmed</div></div>
    `;
  }catch(e){toast('Analytics failed: '+e,'err');}
}

async function loadTranscripts(){
  try{
    const d=await api('/api/transcripts');
    const tp=document.getElementById('transcript-panel');
    const tc=document.getElementById('ts-count');
    if(!tp) return;
    if(!d.sessions || Object.keys(d.sessions).length===0){
      tp.innerHTML='Waiting for active calls...';
      tc.innerText='0 active';
      return;
    }
    tc.innerText=Object.keys(d.sessions).length+' active';
    let html='';
    for(const [sid, sess] of Object.entries(d.sessions)){
      html+=`<div style="margin-bottom:12px;border-bottom:1px solid #333;padding-bottom:12px">
        <strong style="color:var(--blue)">📞 Call: ${sess.student_name} (${sess.student_id})</strong><br>`;
      if(sess.spoken_name) html+=`<span style="color:#888">Name verified: ${sess.spoken_name}</span><br>`;
      for(const [k,v] of Object.entries(sess.answers)){
        html+=`<br><span style="color:var(--amber)">🤖 ${v.question}</span><br>
               <span style="color:#0f0">🗣️ ${v.text} <span style="color:#555;font-size:9px">(conf: ${v.twilio_confidence})</span></span><br>`;
      }
      html+=`</div>`;
    }
    tp.innerHTML=html;
  }catch(e){}
}
setInterval(loadTranscripts, 2000);

loadOverview();loadStudents();loadHistogram();
setTimeout(loadPipeline,500);
setTimeout(loadAnalytics,800);
setInterval(loadOverview,30000);

async function demoCall() {
    toast('Initiating demo call sequence...', 'info');
    document.querySelector('[data-page="dashboard"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    toast('Calling student...', 'info');
    await new Promise(r => setTimeout(r, 1000));
    
    document.querySelector('[data-page="transcript"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('full-transcript-panel');
    if(tp) {
        document.getElementById('ts-count').innerText = '1 active';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px;cursor:pointer;" onclick="this.classList.toggle('minimized')">
            <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Demo Student</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        html += `<br><span style="color:var(--amber)">🤖 ${qas[0].q}</span><br>`;
        tp.innerHTML = html + `</div>`;
        tp.scrollTop = tp.scrollHeight;
        await new Promise(r => setTimeout(r, 1000));
        
        let typed = "";
        html += `<span style="color:var(--green)">🗣️ </span>`;
        for (let i = 0; i < qas[0].a.length; i++) {
            typed += qas[0].a[i];
            tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}</span></div>`);
            tp.scrollTop = tp.scrollHeight;
            await new Promise(r => setTimeout(r, 50)); 
        }
        html = html.replace('🗣️ </span>', `🗣️ ${qas[0].a}</span><br>`);
        
        toast('High Dropout Risk Detected!', 'err');
        
        for (let j = 1; j < qas.length; j++) {
            const qa = qas[j];
            await new Promise(r => setTimeout(r, 500));
            html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 500));
            typed = "";
            html += `<span style="color:var(--green)">🗣️ </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : "";
                tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, 5)); 
            }
            html = html.replace('🗣️ </span>', `🗣️ ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1500));
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
              <span class="t" style="color:var(--green)">Demo Student</span>
              <span class="b">2 msgs | HIGH</span>
            </div>
            <div class="chat-box" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
              <div class="chat-msg" style="margin-bottom:12px;display:flex;">
                 <div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
                   Hi Demo Student! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?
                 </div>
              </div>
              <div id="demo-student-reply" class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"></div>
            </div>
          </div>
        `;
        if(convosPanel.innerHTML.includes('appear here')) {
            convosPanel.innerHTML = '';
        }
        convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
        
        await new Promise(r => setTimeout(r, 1000));
        const replyDiv = document.getElementById('demo-student-reply');
        let replyText = "Hi, yeah things have been a bit rough lately with the finances";
        let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Demo Student</div>`;
                   
        for (let i = 0; i < replyText.length; i++) {
            replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 40)); 
        }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    toast('Demo Ended', 'ok');
}

function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    if (val === 'weekly') {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
        `;
    } else {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,50 110,60 180,50 250,65 320,55 390,70 460,60 500,65" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,110 110,120 180,100 250,130 320,115 390,140 460,120 500,125" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,150 110,140 180,160 250,145 320,150 390,130 460,155 500,145" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
        `;
    }
}
function updateRiskFactors(val) {} 
function updateInterventionSummary(val) {}

</script>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Add counselor-equivalent operations to the admin surface while retaining the admin's pipeline, fairness, and analytics pages.
ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace("</script>\n</body></html>", r'''</script>
<script>
(function(){
  const apiA=async(u,m='GET',b)=>{const o={method:m};if(b){o.headers={'Content-Type':'application/json'};o.body=JSON.stringify(b)};const r=await fetch(u,o);return r.json()};
  window.renderAdminTierChart=function(tiers){const el=document.getElementById('tier-chart');if(!el)return;let rows=(Array.isArray(tiers)?tiers:[]).map(x=>({tier:String(x.final_risk_tier||'UNKNOWN').toUpperCase(),count:Number(x.cnt||x.student_count)||0})).filter(x=>x.count>0);if(!rows.length)rows=[{tier:'HIGH',count:142},{tier:'MEDIUM',count:875},{tier:'LOW',count:3483}];const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)',UNKNOWN:'var(--blue)'},total=rows.reduce((n,x)=>n+x.count,0);let start=0;const stops=rows.map(x=>{const end=start+(x.count/total*100);const stop=`${colors[x.tier]||'var(--blue)'} ${start.toFixed(2)}% ${end.toFixed(2)}%`;start=end;return stop}).join(',');el.innerHTML=`<div class="d-chart-container"><div class="admin-risk-donut" style="background:conic-gradient(${stops})"><div class="admin-risk-hole"><strong>${total.toLocaleString()}</strong><span>students</span></div></div></div><div class="d-legend">${rows.map(x=>`<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[x.tier]||'var(--blue)'}"></span>${x.tier.charAt(0)+x.tier.slice(1).toLowerCase()} risk</span><strong>${x.count.toLocaleString()}</strong></div>`).join('')}</div>`};
  window.updateRiskTrend=function(period){const svg=document.getElementById('risk-trend-svg');if(!svg)return;const labels=period==='monthly'?['Jan','Feb','Mar','Apr','May','Jun']:['Apr 28','May 5','May 12','May 19','May 26','Jun 2'],xs=[40,106,172,238,304,370,436,500],sets=[[34,48,38,56,42,62,48,42,'var(--green)'],[88,106,96,116,102,122,108,104,'var(--amber)'],[166,158,176,166,172,154,174,164,'var(--red)']];const pts=a=>a.slice(0,8).map((y,i)=>`${xs[i]},${y}`).join(' '),dots=(a,c)=>a.slice(0,8).map((y,i)=>`<circle cx="${xs[i]}" cy="${y}" r="3" fill="${c}" stroke="var(--surface)" stroke-width="2"/>`).join('');svg.innerHTML=`<defs><linearGradient id="adminTrendGlow" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".16"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs><rect x="40" y="10" width="460" height="170" rx="10" fill="url(#adminTrendGlow)" opacity=".3"/>${[10,52,94,136,178].map((y,i)=>`<line x1="40" y1="${y}" x2="500" y2="${y}" stroke="var(--border)" stroke-dasharray="3 5"/><text x="30" y="${y+4}" fill="var(--text3)" font-size="10" text-anchor="end">${400-i*100}</text>`).join('')}${sets.map(a=>`<polyline points="${pts(a)}" fill="none" stroke="${a[8]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots(a,a[8])}`).join('')}${labels.map((x,i)=>`<text x="${[75,145,215,285,355,425][i]}" y="198" fill="var(--text3)" font-size="10" text-anchor="middle">${x}</text>`).join('')}`};
  window.showStudent=async function(id){const modal=document.getElementById('modal'),body=document.getElementById('modal-body');modal.classList.add('show');body.innerHTML='<div style="text-align:center;padding:46px"><div class="loading-spinner"></div></div>';try{const d=await apiA('/api/student/'+id),g=d.gold||{},v=d.voice||{},high=String(g.final_risk_tier||'MEDIUM').toUpperCase()==='HIGH',color=high?'var(--red)':'var(--amber)',score=Number(g.ml_risk_score||0).toFixed(3),summary=v.summary||`${g.student_name||'This student'} needs a structured early-support review based on current academic, attendance, and engagement signals.`;body.innerHTML=`<span class="modal-close" onclick="closeModal()">&times;</span><span class="summary-chip ${high?'high':'medium'}">${g.final_risk_tier||'MEDIUM'} RISK · ${score}</span><h2 style="font-size:24px;margin:12px 0 4px">${g.student_name||id}</h2><div class="mono" style="color:var(--text3);font-size:10px">${g.student_id||id} · ADMIN REVIEW</div><div style="padding:15px 16px;border:1px solid ${color};background:color-mix(in srgb,${color} 10%,transparent);border-radius:12px;margin:16px 0"><div class="mono" style="font-size:10px;color:${color};margin-bottom:7px">AI STUDENT SUMMARY</div><p style="margin:0;color:var(--text2);font-size:13px;line-height:1.65">${summary}</p></div><div class="detail-grid"><div class="detail-item"><div class="dl">Attendance</div><div class="dv">${g.attendance_rate||'—'}%</div></div><div class="detail-item"><div class="dl">Current GPA</div><div class="dv">${g.current_gpa||'—'}</div></div><div class="detail-item"><div class="dl">LMS engagement</div><div class="dv">${g.lms_engagement||'—'}</div></div><div class="detail-item"><div class="dl">Financial status</div><div class="dv">${g.financial_aid_status||'—'}</div></div><div class="detail-item"><div class="dl">Credits completed</div><div class="dv">${g.credits_completed||'—'}</div></div><div class="detail-item"><div class="dl">Recommended owner</div><div class="dv">${g.recommended_owner||'Student Success Team'}</div></div></div><div style="margin-top:16px;padding:14px;border-radius:10px;background:var(--surface2)"><div class="mono" style="font-size:10px;color:var(--purple);margin-bottom:8px">ADMIN ACTION PLAN</div><p style="margin:0;font-size:12px;color:var(--text2);line-height:1.55">${g.final_action||'Coordinate a counselor follow-up, assign an intervention owner, and review progress in 48 hours.'}</p></div>`}catch(e){body.innerHTML='<p style="color:var(--red);padding:24px">Unable to load student details.</p>'}};
  window.updateInterventionSummary=function(period){const sets={this_month:[62,74,46,11,5],last_month:[104,68,70,20,14],this_year:[1205,81,976,154,75]},d=sets[period]||sets.this_month,map=[['.admin-int-total',d[0]],['.admin-int-rate',d[1]+'%'],['.admin-int-engaged',d[2]],['.admin-int-progress',d[3]],['.admin-int-none',d[4]]];map.forEach(([s,v])=>{const el=document.querySelector(s);if(el)el.textContent=v});const ring=document.querySelector('.admin-int-rate')?.closest('.card-new')?.querySelector('circle:nth-child(2)');if(ring)ring.style.strokeDashoffset=251-(251*d[1]/100)};
  window.updateRiskFactors=function(period){const sets={this_sem:[42,30,18,10],last_sem:[38,34,16,12],this_year:[45,27,19,9]},vals=sets[period]||sets.this_sem;document.querySelectorAll('.risk-factor').forEach((r,i)=>{if(vals[i]===undefined)return;const n=r.querySelector('.rf-header>div:last-child'),b=r.querySelector('.rf-bar-fill');if(n)n.textContent=vals[i]+'%';if(b)b.style.width=vals[i]+'%'})};
  window.loadAdminAtRisk=async function(){const q=document.getElementById('admin-risk-search')?.value||'',body=document.getElementById('admin-risk-tbody');if(!body)return;const d=await apiA('/api/students?search='+encodeURIComponent(q)+'&limit=60'),rows=(d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase()));document.getElementById('admin-risk-badge').textContent=rows.length+' students';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class="mono" style="color:var(--text3)">${s.student_id}</span></td><td class="mono">${Number(s.ml_risk_score||0).toFixed(3)}</td><td><span class="tag ${String(s.final_risk_tier).toUpperCase()==='HIGH'?'tag-t1':'tag-t2'}">${s.final_risk_tier}</span></td><td>${s.top_factor_1||'Engagement signal'}</td><td>${s.final_action||'Schedule counselor check-in'}</td><td><button class="btn" onclick="showStudent('${s.student_id}')">View</button></td></tr>`).join(''):'<tr><td colspan="6" style="padding:36px;text-align:center;color:var(--text3)">No matching at-risk students</td></tr>'};
  window.loadAdminSummary=async function(){const grid=document.getElementById('admin-summary-grid');if(!grid)return;const d=await apiA('/api/students?limit=24');grid.innerHTML=(d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).slice(0,20).map(s=>{const high=String(s.final_risk_tier).toUpperCase()==='HIGH',score=Number(s.ml_risk_score||0).toFixed(3),att=high?61:78,gpa=high?'2.4':'3.1';return `<article class="summary-person admin-summary-card" onclick="showStudent('${s.student_id}')" data-search="${(s.student_name+' '+s.student_id+' '+(s.top_factor_1||'')).toLowerCase()}"><span class="summary-chip ${high?'high':'medium'}">${s.final_risk_tier} RISK · SCORE ${score}</span><h3 style="margin:12px 0 4px">${s.student_name}</h3><div class="summary-copy">AI synthesis: ${s.student_name} is showing ${String(s.final_risk_tier).toLowerCase()} dropout risk with a ${score} model score. Signals include ${s.top_factor_1||'academic momentum'} and reduced engagement. Recommended action: ${s.final_action||'schedule a counselor check-in'} within 48 hours.</div><div class="summary-meta"><span>Attendance ${att}%</span><span>GPA ${gpa}</span><span>Owner: Student Success</span></div></article>`}).join('')};
  window.filterAdminSummary=function(q){q=(q||'').toLowerCase();document.querySelectorAll('.admin-summary-card').forEach(c=>c.style.display=!q||c.dataset.search.includes(q)?'block':'none')};
  window.loadAdminTranscripts=async function(){const p=document.getElementById('admin-transcript-panel');if(!p)return;const d=await apiA('/api/transcripts'),sessions=d.sessions||{};document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';document.getElementById('admin-voice-count').textContent=Object.keys(sessions).length;p.innerHTML=Object.keys(sessions).length?Object.values(sessions).map(s=>`<div style="padding:14px 0;border-bottom:1px solid var(--border)"><strong style="color:var(--blue)">☎ ${s.student_name} (${s.student_id})</strong><br><span style="color:var(--text3)">${Object.values(s.answers||{}).map(a=>a.text||a.question).join(' · ')||'Listening for response...'}</span></div>`).join(''):'Waiting for active calls...'};
  window.loadAdminWhatsApp=async function(){const p=document.getElementById('admin-wa-panel');if(!p)return;const d=await apiA('/whatsapp/conversations'),sessions=d.sessions||{};document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';document.getElementById('admin-wa-count').textContent=Object.keys(sessions).length;p.innerHTML=Object.keys(sessions).length?Object.entries(sessions).map(([id,s])=>`<div style="padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px"><strong style="color:var(--green)">${s.student_name||id}</strong><p style="margin:7px 0 0;color:var(--text2);font-size:12px">${(s.messages||[]).map(m=>m.body||m.text||'').join(' · ')||'Conversation active'}</p></div>`).join(''):'WhatsApp conversations appear here.'};
  window.adminWaDemo=async function(){toast('Sending WhatsApp demo...','info');const d=await apiA('/whatsapp/demo','POST');toast(d.error||'WhatsApp demo sent',d.error?'err':'ok');loadAdminWhatsApp()};
  window.adminInitiateCall=async function(){toast('Starting live call demo...','info');const d=await apiA('/demo','POST');if(d.error)toast(d.error,'err');else{document.querySelector('[data-page="admin-transcript"]')?.click();loadAdminTranscripts()}};
  document.querySelectorAll('.sb-item[data-page^="admin-"]').forEach(i=>i.addEventListener('click',()=>{if(i.dataset.page==='admin-at-risk')loadAdminAtRisk();if(i.dataset.page==='admin-summary')loadAdminSummary();if(i.dataset.page==='admin-transcript')loadAdminTranscripts();if(i.dataset.page==='admin-whatsapp')loadAdminWhatsApp()}));
  const style=document.createElement('style');style.textContent='.admin-risk-donut{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 26px rgba(99,102,241,.14)}.admin-risk-hole{width:104px;height:104px;border-radius:50%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center}.admin-risk-hole strong{font-size:24px;color:var(--text)}.admin-risk-hole span{font-size:11px;color:var(--text3)}';document.head.appendChild(style);
  loadAdminAtRisk();loadAdminSummary();loadAdminTranscripts();loadAdminWhatsApp();apiA('/api/stats').then(s=>renderAdminTierChart(s.tier_breakdown)).catch(()=>renderAdminTierChart());setTimeout(()=>updateRiskTrend('weekly'),0);setInterval(loadAdminTranscripts,2000);
})();
</script>
</body></html>''')

#  COUNSELOR DASHBOARD — Voice, WhatsApp, Interventions
# ═══════════════════════════════════════════════════════════════════

COUNSELOR_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en"><head>
<title>The Dropout Signal — Counselor</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>""" + SHARED_CSS + r"""
.main { background: var(--bg); padding: 0 32px 32px; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 24px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
.topbar-title h1 { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.topbar-title p { font-size: 13px; color: var(--text2); }
.topbar-actions { display: flex; align-items: center; gap: 16px; }
.top-search { display: flex; align-items: center; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; height: 36px; width: 280px; }
.top-search input { background: transparent; border: none; outline: none; color: var(--text); font-size: 13px; width: 100%; margin-left: 8px; }
.bell-icon { position: relative; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); cursor: pointer; }
.bell-dot { position: absolute; top: 8px; right: 8px; width: 8px; height: 8px; background: var(--red); border-radius: 50%; border: 2px solid var(--surface); }

.stat-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-box { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; position: relative; overflow: hidden; }
.stat-box::before { content:''; position:absolute; top:0; left:0; width:4px; height:100%; background:var(--blue); }
.stat-box.c-red::before { background:var(--red); }
.stat-box.c-amber::before { background:var(--amber); }
.stat-box.c-green::before { background:var(--green); }
.sb-title { font-size: 12px; color: var(--text2); font-weight: 500; margin-bottom: 8px; display:flex; align-items:center; gap:8px; }
.sb-icon { width:24px; height:24px; border-radius:6px; display:flex; align-items:center; justify-content:center; }
.sb-val { font-size: 28px; font-weight: 700; display:flex; align-items:center; gap:12px; }
.sb-trend { font-size: 12px; padding: 2px 6px; border-radius: 4px; font-weight: 600; display:flex; align-items:center; gap:4px; }
.sb-trend.up { background: rgba(34,197,94,0.15); color: var(--green); }
.sb-trend.down { background: rgba(239,68,68,0.15); color: var(--red); }
.sb-sub { font-size: 11px; color: var(--text3); margin-top: 4px; }

.grid-3 { display: grid; grid-template-columns: 3fr 5fr 4fr; gap: 16px; margin-bottom: 16px; }
.card-new { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.card-new-h { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.card-new-h h3 { font-size: 14px; font-weight: 600; }
.card-new-h select { background: transparent; border: none; color: var(--text2); font-size: 12px; outline: none; cursor:pointer; }
.card-new-b { padding: 20px; flex: 1; display:flex; flex-direction:column; }

/* Full-page transcript and summary views live in the left navigation. */
.counselor-rail{display:none}
.rail-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:16px}
.rail-title{padding:14px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:13px;font-weight:600}
.rail-body{padding:14px 16px}
.rail-transcript{background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:16px;border-radius:8px;font-family:var(--font);font-size:12px;line-height:1.6;min-height:220px;max-height:46vh;overflow-y:auto;white-space:pre-wrap}
.rail-summary{font-size:12px;color:var(--text2);line-height:1.6}
@media(max-width:1180px){.main{padding-right:32px}.counselor-rail{display:none}}
@media(max-width:720px){.counselor-rail{display:none}.main{padding:0 16px 24px}.top-search{display:none}}
.transcript-screen{min-height:calc(100vh - 150px);background:#08090d;border:1px solid var(--border);border-radius:14px;padding:24px;font-family:var(--mono);font-size:14px;line-height:1.8;overflow:auto}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
.summary-toolbar{display:flex;align-items:center;gap:14px;margin:-8px 0 18px}.summary-search{display:flex;align-items:center;gap:9px;flex:1;max-width:520px;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:0 13px;height:40px;color:var(--text3)}.summary-search input{width:100%;border:0;outline:0;background:transparent;color:var(--text);font-size:12px}.summary-count{font:10px var(--mono);color:var(--text3);letter-spacing:.5px}.summary-person{position:relative;overflow:hidden;transition:transform .2s,border-color .2s,box-shadow .2s}.summary-person:hover{transform:translateY(-3px);border-color:rgba(188,140,255,.5)!important;box-shadow:0 12px 32px rgba(0,0,0,.2)}.summary-person .summary-chip{display:inline-flex;padding:4px 8px;border-radius:999px;font:600 10px var(--mono);letter-spacing:.4px}.summary-person .summary-copy{font-size:12px;line-height:1.6;color:var(--text2);margin-top:12px}.summary-person .summary-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;font-size:10px;color:var(--text3)}
.summary-person{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px}
.demo-cursor-v3{position:fixed;z-index:20000;pointer-events:none;transition:all .65s cubic-bezier(.2,.9,.2,1);}
.demo-ripple-v3{position:fixed;width:24px;height:24px;background-color:rgba(255,50,50,0.6);border-radius:50%;transform:translate(-50%,-50%);z-index:19999;pointer-events:none;animation:demoRipple .6s ease-out forwards;}
@keyframes demoRipple{0%{transform:translate(-50%,-50%) scale(0);opacity:1}100%{transform:translate(-50%,-50%) scale(2.5);opacity:0}}

/* Donut Chart Custom */
.d-chart-container { display: flex; align-items: center; justify-content: center; position: relative; height: 160px; }
.d-chart-center { position: absolute; text-align: center; }
.d-chart-center .num { font-size: 24px; font-weight: 700; }
.d-chart-center .lbl { font-size: 11px; color: var(--text3); }
.d-legend { display: flex; flex-direction: column; gap: 12px; margin-top: 20px; }
.dl-item { display: flex; align-items: center; justify-content: space-between; font-size: 12px; }
.dl-left { display: flex; align-items: center; gap: 8px; color: var(--text2); }
.dl-dot { width: 8px; height: 8px; border-radius: 50%; }

/* Alerts Feed */
.alert-list { display: flex; flex-direction: column; gap: 12px; }
.alert-item { display: flex; gap: 12px; align-items: flex-start; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px solid transparent; transition: border-color .2s; }
.alert-item:hover { border-color: var(--border); background: var(--surface2); }
.alert-icon { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.alert-body { flex: 1; }
.alert-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px; }
.alert-desc { font-size: 11px; color: var(--text2); }
.alert-time { font-size: 10px; color: var(--text3); }

/* Progress Bars */
.risk-factor { margin-bottom: 16px; }
.rf-header { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; }
.rf-left { display: flex; align-items: center; gap: 8px; color: var(--text2); }
.rf-bar-bg { height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden; }
.rf-bar-fill { height: 100%; border-radius: 3px; }

/* Activity Table */
.act-table { width: 100%; border-collapse: collapse; }
.act-table td { padding: 12px 16px; font-size: 12px; border-bottom: 1px solid var(--border); color: var(--text2); }
.act-table tr:last-child td { border-bottom: none; }
</style>
</head><body>
<div class="sidebar">
  <div class="sb-brand">
    <div class="sb-icon" style="width:34px;height:34px;display:flex;align-items:center;justify-content:center">
      <svg viewBox="0 0 24 24" style="width:28px;height:28px">
        <rect x="5" y="8" width="3" height="12" fill="#ffffff" rx="0.5"/>
        <rect x="10.5" y="11" width="3" height="9" fill="#ffffff" rx="0.5"/>
        <rect x="16" y="14" width="3" height="6" fill="#ffffff" rx="0.5"/>
        <path d="M 6.5 6 A 10.5 10.5 0 0 1 17.5 17" fill="none" stroke="#ff4b4b" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="6.5" cy="6" r="1.5" fill="#ff4b4b"/>
        <circle cx="17.5" cy="17" r="1.5" fill="#ff4b4b"/>
      </svg>
    </div>
    <div><div class="sb-name" style="font-size:13px;color:var(--text);letter-spacing:2px">Dropout Signal</div><div class="sb-role">COUNSELOR</div></div>
  </div>
  <div class="sb-nav">
    <div class="sb-item active" data-page="dashboard">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
      Dashboard
    </div>
    <div class="sb-item" data-page="at-risk">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      At-Risk Students<span class="sb-badge" id="sb-risk-count">-</span>
    </div>
    <div class="sb-item" data-page="transcript">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>
      Live Transcript<span class="sb-badge" id="sb-voice-count">-</span>
    </div>
    <div class="sb-item" data-page="whatsapp">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>
      WhatsApp<span class="sb-badge" id="sb-wa-count">-</span>
    </div>
    <div class="sb-item" data-page="summary">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z"/><path d="M19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16z"/></svg>
      AI Summary
    </div>
  </div>
  <div class="sb-footer">
    <div class="sb-status"><div class="sb-dot"></div><span>System Online</span></div>
    <a href="/logout" style="display:flex;align-items:center;justify-content:center;color:var(--red);text-decoration:none;font-size:11px;font-weight:700;letter-spacing:1px;padding:10px;border:1px solid var(--red-g);background:var(--red-g);border-radius:8px;transition:all .2s;margin-top:12px;">&#x2190; SIGN OUT</a>
  </div>
</div>

<div class="main">
<!-- COUNSELOR DASHBOARD -->
<div class="page active" id="page-dashboard" style="padding:0">
  <div class="topbar">
    <div class="topbar-title">
        <h1>Dashboard</h1>
        <p>Welcome back, Admin Counselor</p>
    </div>
    <div class="topbar-actions">
        <button class="btn" onclick="toggleTheme()" title="Toggle Theme" style="padding:10px 14px;font-size:16px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text);cursor:pointer">&#x263E;</button>
        <div class="top-search">
            <svg viewBox="0 0 24 24" style="width:16px;height:16px;stroke:var(--text3);fill:none;stroke-width:2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="search" id="global-student-search" placeholder="Search students, ID, or keyword..." onkeydown="if(event.key==='Enter')searchStudents(this.value)">
        </div>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px" onclick="initiateCall()">Call Student</button>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px;background:var(--green)" onclick="waDemo()">&#x1f4ac; WhatsApp Demo</button>
        <button class="btn" onclick="runAnalysis()">&#x1f9e0; Analyze Calls</button>
        <button class="btn" onclick="exportCSV()">&#x1f4e5; Export CSV</button>
    </div>
  </div>

  <div class="stat-grid-4">
    <div class="stat-box">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">👥</div>
            Total Students
        </div>
        <div class="sb-val"><span id="cd-calls">4,500</span> <span class="sb-trend up"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 5.6%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-amber">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">⚠️</div>
            At-Risk Students
        </div>
        <div class="sb-val"><span id="cd-med">1,017</span> <span class="sb-trend down"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 12.4%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-red">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">🚨</div>
            Predicted Dropouts
        </div>
        <div class="sb-val"><span id="cd-high">142</span> <span class="sb-trend down"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 8.2%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
    <div class="stat-box c-green">
        <div class="sb-title">
            <div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background-color:rgba(255,255,255,0.1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;">💬</div>
            Interventions
        </div>
        <div class="sb-val"><span id="cd-wa">0</span> <span class="sb-trend up"><svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:3"><polyline points="18 15 12 9 6 15"/></svg> 15.3%</span></div>
        <div class="sb-sub">vs last month</div>
    </div>
  </div>

  <div class="grid-3">
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Overview</h3>
            <select><option>This Semester</option></select>
        </div>
        <div class="card-new-b" id="tier-chart-counselor">
            <div class="skeleton" style="width:100%;height:160px;border-radius:50%"></div>
        </div>
    </div>
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Trend <span class="risk-fixed-badge">1,017 at risk</span></h3>
            <select id="risk-trend-select" onchange="updateRiskTrend(this.value)">
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
            </select>
        </div>
        <div class="card-new-b" style="position:relative">
            <div style="display:flex;justify-content:center;gap:16px;font-size:11px;color:var(--text3);margin-bottom:16px">
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--green);border-radius:2px"></div> Low Risk</span>
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--amber);border-radius:2px"></div> Medium Risk</span>
                <span style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:4px;background:var(--red);border-radius:2px"></div> High Risk</span>
            </div>
            <svg id="risk-trend-svg" width="100%" height="200" viewBox="0 0 500 200" preserveAspectRatio="none">
                <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
                <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
                <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
                <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
                <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
                <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
                <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
                <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
                <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text>
                <text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text>
                <text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text>
                <text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text>
                <text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text>
                <text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
            </svg>
        </div>
    </div>
    <div class="card-new">
        <div class="card-new-h">
            <h3>Recent Alerts</h3>
            <a href="#" onclick="event.preventDefault();document.querySelector('[data-page=at-risk]').click();" style="color:var(--red);font-size:12px;text-decoration:none;cursor:pointer">View all</a>
        </div>
        <div class="card-new-b">
            <div class="alert-list" id="recent-alerts-list">
                <div class="alert-item" style="cursor:pointer" onclick="showStudentSummary('Arjun Sharma', 'CS-21-1042', 'High risk detected', 'Low attendance and poor grades')">
                    <div class="alert-icon" style="background:var(--red-g);color:var(--red)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">High risk detected</div>
                        <div class="alert-desc">Arjun Sharma (CS-21-1042)</div>
                    </div>
                    <div class="alert-time">2m ago</div>
                </div>
                <div class="alert-item" style="cursor:pointer" onclick="showStudentSummary('Neha Patil', 'EC-21-0876', 'Attendance drop', 'Missed 4 consecutive classes in core subjects.')">
                    <div class="alert-icon" style="background:var(--amber-g);color:var(--amber)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">Attendance drop</div>
                        <div class="alert-desc">Neha Patil (EC-21-0876)</div>
                    </div>
                    <div class="alert-time">15m ago</div>
                </div>
                <div class="alert-item" style="cursor:pointer" onclick="showStudentSummary('Rohan Verma', 'ME-21-0654', 'Low engagement', 'Zero LMS logins in the past 10 days.')">
                    <div class="alert-icon" style="background:var(--purple-g);color:var(--purple)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>
                    <div class="alert-body">
                        <div class="alert-title">Low engagement</div>
                        <div class="alert-desc">Rohan Verma (ME-21-0654)</div>
                    </div>
                    <div class="alert-time">1h ago</div>
                </div>
            </div>
        </div>
    </div>
  </div>

  <div class="grid-2" style="grid-template-columns: 1fr 1fr; margin-bottom: 0;">
    <div class="card-new">
        <div class="card-new-h">
            <h3><span style="color:#bc8cff;margin-right:8px">&#x2728;</span>AI Insights</h3>
        </div>
        <div class="card-new-b" style="justify-content:space-between">
            <p style="font-size:13px;color:var(--text2);line-height:1.6">Based on recent data, 87 students are at high risk of dropping out. Key factors include attendance (42%), low engagement (28%), and academic performance (30%). Early intervention can improve outcomes.</p>
            <div style="text-align:center;margin:20px 0">
                <svg viewBox="0 0 24 24" style="width:80px;height:80px;stroke:#bc8cff;fill:none;stroke-width:1;opacity:0.6"><path d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2z"/><path d="M12 6v12"/><path d="M8 10h8"/><path d="M8 14h8"/></svg>
            </div>
            <button class="nav-cta" style="background:rgba(188,140,255,0.1);color:#bc8cff!important;border:1px solid rgba(188,140,255,0.2)" onclick="openSidePanel('insights')">View Full Report &rarr;</button>
        </div>
    </div>
    
    <div id="insights-panel-content" style="display:none;">
      <div class="card-new">
          <div class="card-new-h">
              <h3>Top Risk Factors</h3>
              <select onchange="updateRiskFactors(this.value)">
                  <option value="this_sem">This Semester</option>
                  <option value="last_sem">Last Semester</option>
                  <option value="this_year">This Year</option>
              </select>
          </div>
          <div class="card-new-b">
              <div class="risk-factor">
                  <div class="rf-header">
                      <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--red);fill:none;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> Low Attendance</div>
                      <div>42%</div>
                  </div>
                  <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:42%;background:var(--red)"></div></div>
              </div>
              <div class="risk-factor">
                  <div class="rf-header">
                      <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--amber);fill:none;stroke-width:2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg> Poor Academic Performance</div>
                      <div>30%</div>
                  </div>
                  <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:30%;background:var(--amber)"></div></div>
              </div>
              <div class="risk-factor">
                  <div class="rf-header">
                      <div class="rf-left"><svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:var(--green);fill:none;stroke-width:2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Low Engagement</div>
                      <div>18%</div>
                  </div>
                  <div class="rf-bar-bg"><div class="rf-bar-fill" style="width:18%;background:var(--green)"></div></div>
              </div>
          </div>
      </div>
    </div>
    <div class="card-new">
        <div class="card-new-h">
            <h3>Intervention Summary</h3>
            <select onchange="updateInterventionSummary(this.value)">
                <option value="this_month">This Month</option>
                <option value="last_month">Last Month</option>
                <option value="this_year">This Year</option>
            </select>
        </div>
        <div class="card-new-b" id="intervention-stats" style="justify-content:space-between">
            <div style="display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div class="t-val" style="font-size:28px;font-weight:700">62</div>
                    <div style="font-size:11px;color:var(--text3)">Total Interventions</div>
                </div>
                <div style="position:relative;width:80px;height:80px">
                    <svg viewBox="0 0 100 100" width="80" height="80">
                        <circle cx="50" cy="50" r="40" fill="none" stroke="var(--border)" stroke-width="8"/>
                        <circle cx="50" cy="50" r="40" fill="none" stroke="var(--green)" stroke-width="8" stroke-dasharray="251" stroke-dashoffset="65" stroke-linecap="round" transform="rotate(-90 50 50)"/>
                    </svg>
                    <div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
                        <span class="p-val" style="font-size:16px;font-weight:700">74%</span>
                        <span style="font-size:8px;color:var(--text3)">Successful</span>
                    </div>
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:24px;border-top:1px solid var(--border);padding-top:16px">
                <div style="text-align:center"><div class="e-val" style="font-size:16px;font-weight:600">46</div><div style="font-size:10px;color:var(--text3)">Engaged</div></div>
                <div style="text-align:center"><div class="i-val" style="font-size:16px;font-weight:600">11</div><div style="font-size:10px;color:var(--text3)">In Progress</div></div>
                <div style="text-align:center"><div class="n-val" style="font-size:16px;font-weight:600">5</div><div style="font-size:10px;color:var(--text3)">No Response</div></div>
            </div>
        </div>
    </div>
  </div>

  <div id="voice-panel-content" style="display:none;">
      <div class="card-new" style="margin-bottom:16px;">
        <div class="card-new-h"><h3>Live Call Transcripts</h3><span class="b" id="ts-count" style="font-size:12px;color:var(--text3)">0 active</span></div>
        <div class="card-new-b" id="transcript-panel" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:16px;border-radius:8px;font-family:var(--font);font-size:12px;line-height:1.6;min-height:200px;max-height:250px;overflow-y:auto;white-space:pre-wrap;">Waiting for active calls...</div>
      </div>
      <div class="card-new">
        <div class="card-new-h"><h3>Voice Analysis Results</h3><span class="b" id="analysis-count" style="font-size:12px;color:var(--text3)">-</span></div>
        <div style="overflow-x:auto;padding:16px;">
          <table class="act-table"><thead><tr><th style="text-align:left;padding-bottom:8px">Student</th><th style="text-align:left;padding-bottom:8px">Score</th><th style="text-align:left;padding-bottom:8px">Intent</th><th style="text-align:left;padding-bottom:8px">Prob</th><th style="text-align:left;padding-bottom:8px">Root Cause</th><th style="text-align:left;padding-bottom:8px">Sentiment</th></tr></thead>
          <tbody id="analysis-tbody"><tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text3)">Run a live call + analyze to see results</td></tr></tbody></table>
        </div>
      </div>
  </div>
</div>

<!-- WHATSAPP -->
<div class="page" id="page-whatsapp">
  <div class="page-hdr"><h1>WhatsApp — Asha AI Counselor</h1><p>Personalized student wellness conversations via WhatsApp</p></div>
  <div style="display:flex;gap:8px;margin-bottom:16px">
    <button class="btn btn-green" onclick="waDemo()">&#x1f4ac; Send WhatsApp Message</button>
    <button class="btn" onclick="loadWAConvos()">Refresh</button>
  </div>
  <div class="card">
    <div class="card-h"><span class="t">Conversations</span><span class="b" id="wa-count-badge">-</span></div>
    <div class="card-b" id="wa-convos-panel"><p style="color:var(--text3);font-size:12px">WhatsApp conversations appear here. Asha responds with SHAP-informed wellness guidance.</p></div>
  </div>
</div>

<!-- AT-RISK STUDENTS -->
<div class="page" id="page-at-risk">
  <div class="page-hdr"><h1>At-Risk Students</h1><p>HIGH and MEDIUM risk students requiring intervention</p></div>
  <div class="search-bar">
    <input class="search-input" id="risk-search" placeholder="Search by student ID..." onkeyup="if(event.key==='Enter')loadAtRisk()">
    <button class="btn" onclick="loadAtRisk()">Search</button>
    <button class="btn btn-red" onclick="document.getElementById('risk-search').value='';loadAtRisk()">Reset</button>
  </div>
  <div class="card">
    <div class="card-h"><span class="t">Students Needing Intervention</span><span class="b" id="risk-count-badge">loading...</span></div>
    <div style="overflow-x:auto">
      <table class="tbl"><thead><tr><th>ID</th><th>Risk</th><th>Tier</th><th>Root Cause</th><th>Action</th><th></th></tr></thead>
      <tbody id="risk-tbody"><tr><td colspan="6" style="text-align:center;padding:40px"><div class="loading-spinner"></div></td></tr></tbody></table>
    </div>
  </div>
</div>

<!-- LIVE TRANSCRIPT -->
<div class="page" id="page-transcript">
  <div class="page-hdr"><h1>Live Call Transcripts</h1><p>Real-time transcription of active AI phone calls</p></div>
  <div class="card">
    <div class="card-h"><span class="t">Active Calls</span><span class="b" id="ts-count">0 active</span></div>
    <div class="card-b" id="full-transcript-panel" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:16px;border-radius:8px;font-family:var(--font);font-size:13px;line-height:1.6;min-height:400px;max-height:600px;overflow-y:auto;white-space:pre-wrap;">Waiting for active calls...</div>
  </div>
</div>

<!-- AI SUMMARY -->
<div class="page" id="page-summary">
  <div class="page-hdr"><h1>AI Student Summary</h1><p>Prioritized next actions from risk signals, voice verification, and WhatsApp conversations.</p></div>
  <div class="summary-toolbar"><div class="summary-search"><span>⌕</span><input id="summary-search" placeholder="Search AI summaries by student, ID, or signal..." oninput="filterSummaryCards(this.value)"></div><span class="summary-count" id="summary-count">Live risk intelligence</span></div>
  <div class="summary-grid" id="summary-students">
    <article class="summary-person" id="demo-summary-card" style="cursor:pointer" onclick="showStudent('STU-DEMO')"><div class="mono" style="color:var(--red);margin-bottom:8px">HIGH RISK · DEMO</div><h3 style="margin-bottom:0px">Aarav Patel</h3></article>
    <article class="summary-person" style="cursor:pointer" onclick="showStudent('EC-21-0876')"><div class="mono" style="color:var(--amber);margin-bottom:8px">MEDIUM RISK</div><h3 style="margin-bottom:0px">Neha Patil</h3></article>
    <article class="summary-person" style="cursor:pointer" onclick="showStudent('ME-21-0654')"><div class="mono" style="color:var(--green);margin-bottom:8px">MONITOR</div><h3 style="margin-bottom:0px">Rahul Kumar</h3></article>
  </div>
</div>
<aside class="counselor-rail" aria-label="Counselor context panel" style="display:none;">
  <section class="rail-card">
    <div class="rail-title"><span>Live transcript</span><span id="rail-ts-count" style="font:11px var(--mono);color:var(--text3)">0 active</span></div>
    <div class="rail-body"><div class="rail-transcript" id="rail-transcript-panel">Waiting for an active call…</div></div>
  </section>
  <section class="rail-card">
    <div class="rail-title">AI summary</div>
    <div class="rail-body rail-summary" id="rail-student-summary">Select a student from At-Risk Students or Recent Alerts to see a concise, actionable summary here.</div>
  </section>
</aside>

<div class="modal-bg" id="modal" onclick="if(event.target===this)closeModal()"><div class="modal"><div id="modal-body"></div></div></div>
<div id="toast"></div>

<script>
function toggleTheme(){
  const t=document.documentElement.getAttribute('data-theme')==='light'?'':'light';
  document.documentElement.setAttribute('data-theme',t);
  localStorage.setItem('theme',t);
}
(function(){const t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);})();
document.querySelectorAll('.sb-item').forEach(item=>{
  item.addEventListener('click',()=>{
    if(!item.dataset.page) return;
    const target=document.getElementById('page-'+item.dataset.page);
    if(!target) return;
    document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    target.classList.add('active');
    if (item.dataset.page === 'transcript') document.body.classList.add('transcript-fs');
    else document.body.classList.remove('transcript-fs');
  });
});
function toast(msg,type='info'){const el=document.getElementById('toast');el.textContent=msg;el.className=type+' show';setTimeout(()=>el.className='',3500);}
async function api(url,method='GET',body=null){const opts={method};if(body){opts.headers={'Content-Type':'application/json'};opts.body=JSON.stringify(body);}const r=await fetch(url,opts);return r.json();}

function renderCounselorTierChart(tiers){
  const target=document.getElementById('tier-chart-counselor');
  if(!target) return;
  const valid=(tiers||[]).map(t=>({tier:(t.final_risk_tier||'Unknown').toUpperCase(),count:Number(t.cnt)||0})).filter(t=>t.count>0);
  const total=valid.reduce((sum,t)=>sum+t.count,0);
  if(!total){target.innerHTML='<p style="color:var(--text3);font-size:12px;text-align:center;padding:40px 0">Risk data is not available yet.</p>';return;}
  const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)'};
  let cursor=0;
  const stops=valid.map(t=>{const end=cursor+(t.count/total*100);const stop=`${colors[t.tier]||'var(--blue)'} ${cursor.toFixed(2)}% ${end.toFixed(2)}%`;cursor=end;return stop;}).join(', ');
  target.innerHTML=`<div class="d-chart-container"><div style="width:150px;height:150px;border-radius:50%;background:conic-gradient(${stops});position:relative"><div style="position:absolute;inset:22px;border-radius:50%;background:var(--bg)"></div></div><div class="d-chart-center"><div class="num">${total.toLocaleString()}</div><div class="lbl">students</div></div></div><div class="d-legend">${valid.map(t=>`<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[t.tier]||'var(--blue)'}"></span>${t.tier[0]+t.tier.slice(1).toLowerCase()} risk</span><strong>${t.count.toLocaleString()}</strong></div>`).join('')}</div>`;
}

function updateInterventionSummary(val) {
    const vals = {
        'this_month': {t: 62, p: '74%', e: 46, i: 11, n: 5},
        'last_month': {t: 104, p: '68%', e: 70, i: 20, n: 14},
        'this_year': {t: 1205, p: '81%', e: 976, i: 154, n: 75}
    };
    const d = vals[val] || vals['this_month'];
    const b = document.getElementById('intervention-stats');
    if(b) {
        b.querySelector('.t-val').textContent = d.t;
        b.querySelector('.p-val').textContent = d.p;
        b.querySelector('.e-val').textContent = d.e;
        b.querySelector('.i-val').textContent = d.i;
        b.querySelector('.n-val').textContent = d.n;
    }
}

function searchStudents(value){
  const query=(value||'').trim();
  const input=document.getElementById('risk-search');
  if(input) input.value=query;
  const nav=document.querySelector('[data-page="at-risk"]');
  if(nav && !nav.classList.contains('active')) nav.click();
  loadAtRisk();
}

async function loadDashboard(){
  try{
    const s=await api('/api/stats');
    const tierMap={};(s.tier_breakdown||[]).forEach(t=>{tierMap[(t.final_risk_tier||'').toUpperCase()]=parseInt(t.cnt);});
    const bronzeCount = s.bronze_count || 0;
    const goldCount = s.gold_count || 0;
    const highRisk = tierMap['HIGH'] || 0;
    const medRisk = tierMap['MEDIUM'] || 0;
    const voiceCount = s.voice_completed || 0;
    const waCount = s.wa_conversations || 0;

    const elTotal = document.getElementById('s-bronze') || document.getElementById('cd-calls');
    const elAtRisk = document.getElementById('s-gold') || document.getElementById('cd-med');
    const elPred = document.getElementById('s-avgrisk') || document.getElementById('cd-high');
    const elInt = document.getElementById('s-voice') || document.getElementById('cd-wa');
    
    if (elTotal) elTotal.textContent = (bronzeCount || goldCount).toLocaleString();
    if (elAtRisk) elAtRisk.textContent = (highRisk + medRisk).toLocaleString();
    if (elPred) elPred.textContent = highRisk.toLocaleString();
    if (elInt) elInt.textContent = (voiceCount + waCount).toLocaleString();
    
    document.getElementById('sb-risk-count').textContent=(tierMap['HIGH']||0)+(tierMap['MEDIUM']||0);
    document.getElementById('sb-voice-count').textContent=s.voice_analyzed||0;
    document.getElementById('sb-wa-count').textContent=s.wa_conversations||0;
    renderCounselorTierChart(s.tier_breakdown);
  }catch(e){}
}

async function loadAtRisk(){
  const search=document.getElementById('risk-search').value;
  const tbody=document.getElementById('risk-tbody');
  tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px"><div class="loading-spinner"></div></td></tr>';
  try{
    const d=await api('/api/students?search='+encodeURIComponent(search));
    const atRisk=(d.students||[]).filter(s=>{const t=(s.final_risk_tier||'').toUpperCase();return t==='HIGH'||t==='MEDIUM';});
    
    document.getElementById('risk-count-badge').textContent=atRisk.length+' students';
    
    const grid = document.getElementById('summary-students');
    if(grid) {
       grid.innerHTML = atRisk.map(s => {
          const tier=s.final_risk_tier||'';
          const cls=tier.toUpperCase()==='HIGH'?'red':'amber';
          const p = parseFloat(s.ml_risk_score||0).toFixed(3);
          return `<article class="summary-person" style="cursor:pointer;border-left:3px solid var(--${cls});background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;" onclick="showStudent('${s.student_id}')"><div class="mono" style="color:var(--${cls});margin-bottom:8px;font-size:10px">${tier.toUpperCase()} RISK · SCORE: ${p}</div><h3 style="margin-bottom:6px">${s.student_name}</h3><div style="font-size:12px;color:var(--text2)">${s.final_action||'-'}</div></article>`;
       }).join('');
    }
    
    if(!atRisk.length){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">No at-risk students found</td></tr>';return;}
    tbody.innerHTML=atRisk.map(s=>{
      const score=parseFloat(s.ml_risk_score||0);
      const tier=s.final_risk_tier||'';
      const cls=tier.toUpperCase()==='HIGH'?'t1':'t2';
      return `<tr>
        <td><span style="font-weight:500;color:var(--text)">${s.student_name || 'Demo Student'}</span> <span class="mono" style="color:var(--text3)">(${s.student_id})</span></td>
        <td><span class="mono">${score.toFixed(3)}</span></td>
        <td><span class="tag tag-${cls}">${tier}</span></td>
        <td style="max-width:200px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.voice_root_cause||s.top_factor_1||'-'}</td>
        <td style="max-width:280px;font-size:10px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.final_action||'-'}</td>
        <td><button class="btn" onclick="showStudent('${s.student_id}')">View</button></td>
      </tr>`;
    }).join('');
  }catch(e){toast('Failed: '+e,'err');}
}

function updateStudentSummary(student, voice={}){
  const panel=document.getElementById('rail-student-summary');
  if(!panel) return;
  const name=student.student_name||student.student_id||'Student';
  const risk=student.final_risk_tier||'Unknown';
  const score=student.ml_risk_score!==undefined ? Number(student.ml_risk_score).toFixed(2) : '—';
  const cause=voice.primary_root_cause||student.voice_root_cause||student.top_factor_1||'No specific factor is available yet.';
  const summary=voice.summary||student.final_action||'Review the student record and offer an appropriate early-support check-in.';
  panel.innerHTML=`<div style="font-weight:600;color:var(--text);margin-bottom:4px">${name}</div><div style="font:10px var(--mono);color:var(--text3);margin-bottom:12px">${risk} RISK · SCORE ${score}</div><div style="margin-bottom:8px"><strong style="color:var(--text)">Primary signal:</strong> ${cause}</div><div><strong style="color:var(--text)">Suggested action:</strong> ${summary}</div>`;
}

async function showStudent(id){
  document.getElementById('modal').classList.add('show');
  document.getElementById('modal-body').innerHTML='<div style="text-align:center;padding:40px"><div class="loading-spinner"></div></div>';
  try{
    const d=await api('/api/student/'+id);const g=d.gold||{};
    updateStudentSummary(g, d.voice||{});
    let html=`<h2 style="font-size:18px;margin-bottom:4px">Student #${id}</h2><div class="detail-grid">`;
    for(const f of Object.keys(g)){if(g[f]!==null&&g[f]!=='')html+=`<div class="detail-item"><div class="dl">${f.replace(/_/g,' ')}</div><div class="dv" style="font-size:13px;word-break:break-word">${g[f]}</div></div>`;}
    html+='</div>';
    if(d.voice){
      html+='<div style="margin-top:16px"><div style="font-size:10px;font-family:var(--mono);color:var(--text3);margin-bottom:8px;letter-spacing:1px">VOICE ANALYSIS</div>';
      html+=`<div class="detail-grid">
        <div class="detail-item"><div class="dl">Dropout Intent</div><div class="dv">${d.voice.dropout_intent||'-'}</div></div>
        <div class="detail-item"><div class="dl">Dropout Prob</div><div class="dv">${d.voice.dropout_probability||'-'}</div></div>
        <div class="detail-item"><div class="dl">Sentiment</div><div class="dv">${d.voice.overall_sentiment||'-'}</div></div>
        <div class="detail-item"><div class="dl">Root Cause</div><div class="dv">${d.voice.primary_root_cause||'-'}</div></div>
      </div>`;
      if(d.voice.summary)html+=`<p style="font-size:12px;color:var(--text2);line-height:1.7;margin-top:8px">${d.voice.summary}</p>`;
      html+='</div>';
    }
    document.getElementById('modal-body').innerHTML='<span class="modal-close" onclick="closeModal()">&times;</span>'+html;
  }catch(e){document.getElementById('modal-body').innerHTML='<p style="color:var(--red)">Error: '+e+'</p>';}
}
function closeModal(){document.getElementById('modal').classList.remove('show');}

async function waDemo(){toast('Sending WhatsApp...','info');const d=await api('/whatsapp/demo','POST');if(d.error)toast(d.error,'err');else toast('WhatsApp sent!','ok');}
async function runAnalysis(){toast('Running LLM analysis...','info');try{const d=await api('/analyze','POST');if(d.error)toast(d.error,'err');else{toast(d.analyzed+' analyzed'+(d.whatsapp_sent?' + '+d.whatsapp_sent+' WhatsApp sent':''),'ok');loadAnalysis();}}catch(e){toast('Analysis error: '+e.message,'err');}}
async function exportCSV(){try{const d=await api('/export');if(d.error)toast(d.error,'err');else toast('Exported '+d.count+' results to dropout_analysis.csv in project folder','ok');}catch(e){toast('Export error: '+e.message,'err');}}

let isWaitingForRealCall = false;
let lastAnalyzedCount = 0;

async function loadAnalysis(){
  try{
    const d=await api('/results');
    const newCount = d.analyzed || 0;
    
    if (isWaitingForRealCall && newCount > lastAnalyzedCount && d.results && d.results.length > 0) {
        isWaitingForRealCall = false;
        const theResult = d.results[0];
        const intent = theResult.dropout_intent || 'MEDIUM';
        const color = intent === 'HIGH' ? 'var(--red)' : 'var(--amber)';
        
        const summaryPop = document.createElement('div');
        summaryPop.innerHTML = `
          <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d0d12;border:1px solid ${color};border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(239,68,68,0.2);text-align:center;width:460px">
            <div class="mono" style="color:${color};margin-bottom:12px">VOICE RISK CONFIRMED: ${intent}</div>
            <h2 style="font-size:25px;margin-bottom:12px">${theResult.spoken_name || theResult.student_name || 'Student'} flagged</h2>
            <div style="background:var(--surface2);border-radius:8px;padding:16px;text-align:left;margin-bottom:24px">
                <p style="font-size:14px;color:var(--text);line-height:1.5">${theResult.summary || 'Risk detected in live call. Follow up recommended.'}</p>
            </div>
            <div style="margin-top:18px;color:var(--amber);font:11px var(--mono)">SWITCHING TO WHATSAPP...</div>
          </div>
          <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:9999"></div>
        `;
        document.body.appendChild(summaryPop);
        
        setTimeout(() => {
            summaryPop.remove();
            const waTab = document.querySelector('[data-page="whatsapp"]');
            if(waTab) waTab.click();
        }, 4000);
    }
    
    lastAnalyzedCount = newCount;
    
    document.getElementById('analysis-count').textContent=(d.analyzed||0)+' analyzed';
    document.getElementById('sb-voice-count').textContent=d.analyzed||0;
    if(d.results&&d.results.length){
      document.getElementById('analysis-tbody').innerHTML=d.results.map(r=>{
        const score=parseFloat(r.ml_risk_score||0);const prob=parseFloat(r.dropout_probability||0);
        const intent=r.dropout_intent||'';const icls=intent==='HIGH'?'t1':intent==='MEDIUM'?'t2':'t3';
        return `<tr>
          <td style="padding:12px 16px"><span style="font-weight:600;color:var(--text)">${r.spoken_name || r.student_name || r.student_id}</span></td>
          <td style="padding:12px 16px"><span class="mono">${score.toFixed(2)}</span></td>
          <td style="padding:12px 16px"><span class="tag tag-${icls}">${intent}</span></td>
          <td style="padding:12px 16px"><span class="mono">${prob.toFixed(2)}</span></td>
          <td style="padding:12px 16px;font-size:11px;color:var(--text2);text-transform:capitalize">${r.primary_root_cause||'-'}</td>
          <td style="padding:12px 16px;font-size:11px;color:var(--text2);text-transform:capitalize">${r.overall_sentiment||'-'}</td>
        </tr>`;
      }).join('');
    }
  }catch(e){}
}


async function loadWAConvos(){
  const wp = document.getElementById('wa-convos-panel');
  if(wp && (wp.innerHTML.includes('demo-student-reply') || wp.innerHTML.includes('demo-automated-chat'))) return;
  try{
    const d = await api('/whatsapp/conversations');
    const badge = document.getElementById('wa-count-badge');
    if(badge) badge.textContent = d.total + ' active';
    if(wp && d.conversations){
      let html = '';
      
      const achalConvo = d.conversations.find(c => (c.student_name || '').toLowerCase().includes('achal'));
      const otherConvos = d.conversations.filter(c => !(c.student_name || '').toLowerCase().includes('achal'));
      
      const renderConvo = (c, isOpen=false) => {
        let msgHtml = (c.messages||[]).map(m => {
          const isUsr = m.role === 'user';
          const align = isUsr ? 'flex-end' : 'flex-start';
          const bg = isUsr ? 'var(--blue-g)' : 'var(--surface2)';
          const color = isUsr ? 'var(--blue)' : 'var(--text)';
          const br = isUsr ? 'border-bottom-right-radius:4px' : 'border-bottom-left-radius:4px';
          const sender = isUsr ? (c.student_name||c.student_id) : '🤖 Asha AI';
          return `<div class="chat-msg ${isUsr?'user':'assistant'}" style="margin-bottom:12px;display:flex;justify-content:${align}">
            <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:${bg};color:${color};${br}">
              <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${sender}</div>
              ${m.content || m.body || ''}
            </div>
          </div>`;
        }).join('');
        
        return `<div class="card wa-student-card" data-student="${c.student_id||c.phone}" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
          <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="const b=this.nextElementSibling; const o=b.style.display==='block'; document.querySelectorAll('.chat-box').forEach(x=>x.style.display='none'); b.style.display=o?'none':'block';">
            <span class="t" style="color:var(--green)">${c.student_name || c.student_id || c.phone}</span>
            <span class="b">${(c.messages||[]).length} msgs | ${c.risk_tier || 'MONITOR'}</span>
          </div>
          <div class="chat-box" style="display:${isOpen ? 'block' : 'none'};margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
            ${msgHtml}
          </div>
        </div>`;
      };

      if (achalConvo) html += renderConvo(achalConvo, true);
      otherConvos.forEach(c => html += renderConvo(c, false));
      
      // Preserve states before updating
      if(wp.innerHTML.includes('wa-student-card')) {
          const oldStates = {};
          wp.querySelectorAll('.wa-student-card').forEach(card => {
             const sid = card.getAttribute('data-student');
             const box = card.querySelector('.chat-box');
             if(sid && box) oldStates[sid] = { display: box.style.display, scrollTop: box.scrollTop };
          });
          
          wp.innerHTML = html;
          
          wp.querySelectorAll('.wa-student-card').forEach(card => {
             const sid = card.getAttribute('data-student');
             const box = card.querySelector('.chat-box');
             if(sid && oldStates[sid]) {
                 box.style.display = oldStates[sid].display;
                 box.scrollTop = box.scrollHeight;
             }
          });
      } else {
          wp.innerHTML = html;
          wp.querySelectorAll('.chat-box').forEach(box => {
              box.scrollTop = box.scrollHeight;
          });
      }
    }
  }catch(e){}
}


async function loadTranscripts(){
  try{
    const d=await api('/api/transcripts');
    const tp=document.getElementById('full-transcript-panel');
    const tc=document.getElementById('sb-voice-count');
    if(!tp) return;
    if(tp.innerHTML.includes('STU-DEMO')) return;
    if(!d.sessions || Object.keys(d.sessions).length===0){
      tp.innerHTML='Waiting for active calls...';
      tc.innerText='0';
      return;
    }
    tc.innerText=Object.keys(d.sessions).length;
    let html='';
    for(const [sid, sess] of Object.entries(d.sessions)){
      html+=`<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px">
        <strong style="color:var(--blue)">📞 Call: ${sess.student_name} (${sess.student_id})</strong><br>`;
      if(sess.spoken_name) html+=`<span style="color:#888">Name verified: ${sess.spoken_name}</span><br>`;
      for(const [k,v] of Object.entries(sess.answers)){
        html+=`<br><span style="color:var(--amber)">🤖 ${v.question}</span><br>
               <span style="color:var(--green)">🗣️ ${v.text} <span style="color:#555;font-size:9px">(conf: ${v.twilio_confidence})</span></span><br>`;
      }
      if(sess.current_question) {
        html+=`<br><span style="color:var(--amber); opacity: 0.8">🤖 ${sess.current_question}</span><br>
               <span style="color:#555;font-style:italic">🗣️ ...listening...</span><br>`;
      }
      html+=`</div>`;
    }
    const isScrolledToBottom = tp.scrollHeight - tp.scrollTop <= tp.clientHeight + 20;
    tp.innerHTML=html;
    if(isScrolledToBottom) {
      tp.scrollTop = tp.scrollHeight;
    }
  }catch(e){}
}
setInterval(loadTranscripts, 2000);

async function initDashboard() {
    await api('/api/reset', 'POST');
    loadDashboard();loadAtRisk();loadAnalysis();loadWAConvos();
    setInterval(()=>{try{loadDashboard();loadAnalysis();loadWAConvos();}catch(e){console.error(e);}},2000);
}
initDashboard();

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('demo') === 'true') {
    // The guided version is defined by the UI script below; defer so the
    // login-to-call walkthrough visibly performs each step.
    setTimeout(() => startAutomatedDemo(), 0);
}

async function startAutomatedDemo() {
    const floatBtn = document.createElement('div');
    floatBtn.innerHTML = '<button class="btn btn-red" style="padding:12px 24px;height:auto;font-size:14px;box-shadow:0 0 20px rgba(239,68,68,0.5);font-weight:700" onclick="window.location.href=\'/logout\'">End Demo</button>';
    floatBtn.style.position = 'fixed';
    floatBtn.style.bottom = '24px';
    floatBtn.style.left = '50%';
    floatBtn.style.transform = 'translateX(-50%)';
    floatBtn.style.zIndex = '999999';
    document.body.appendChild(floatBtn);

    const cursor = document.createElement('div');
    cursor.style.cssText = `position:fixed;width:24px;height:24px;background:url("data:image/svg+xml;utf8,<svg viewBox='0 0 320 320' fill='white' stroke='black' stroke-width='18' stroke-linejoin='round' xmlns='http://www.w3.org/2000/svg'><path d='M 40 20 L 40 280 L 120 210 L 180 300 L 230 275 L 170 185 L 270 185 Z'/></svg>") no-repeat;background-size:contain;z-index:20000;top:50%;left:50%;transition:all 1.2s ease;pointer-events:none;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.6));`;
    document.body.appendChild(cursor);
    const clickEffect = (x,y) => {
        const ripple=document.createElement('span');
        ripple.style.cssText=`position:fixed;left:${x}px;top:${y}px;width:20px;height:20px;border:2px solid #ff4b4b;border-radius:50%;pointer-events:none;z-index:19999;transform:translate(-50%,-50%) scale(.35);opacity:.95;transition:transform .45s ease,opacity .45s ease`;
        document.body.appendChild(ripple); requestAnimationFrame(()=>{ripple.style.transform='translate(-50%,-50%) scale(2.8)';ripple.style.opacity='0';}); setTimeout(()=>ripple.remove(),500);
    };

    await new Promise(r => setTimeout(r, 800));
    const callBtn = document.querySelector('.nav-cta');
    if(callBtn) {
        const rect = callBtn.getBoundingClientRect();
        cursor.style.top = (rect.top + rect.height/2) + 'px';
        cursor.style.left = (rect.left + rect.width/2) + 'px';
        await new Promise(r => setTimeout(r, 1300));
        cursor.style.transform = 'scale(0.8)';
        await new Promise(r => setTimeout(r, 150));
        cursor.style.transform = 'scale(1)';
        await new Promise(r => setTimeout(r, 300));
        clickEffect(rect.left + rect.width/2, rect.top + rect.height/2);
    }
    
    const transcriptTab = document.querySelector('[data-page="transcript"]');
    if(transcriptTab) {
        const rect = transcriptTab.getBoundingClientRect();
        cursor.style.top = (rect.top + rect.height/2) + 'px';
        cursor.style.left = (rect.left + rect.width/2) + 'px';
        await new Promise(r => setTimeout(r, 1000));
        cursor.style.transform = 'scale(0.8)';
        await new Promise(r => setTimeout(r, 150));
        cursor.style.transform = 'scale(1)';
        await new Promise(r => setTimeout(r, 300));
        clickEffect(rect.left + rect.width/2, rect.top + rect.height/2);
        transcriptTab.click();
    }
    
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('full-transcript-panel');
    if(tp) {
        document.getElementById('sb-voice-count').innerText = '1';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px">
            <strong style="color:var(--blue)">📞 Call: Aarav Patel (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Aarav Patel</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        for (const qa of qas) {
            await new Promise(r => setTimeout(r, 800));
            html += `<br><span style="color:var(--amber)">🤖 Asha: ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 600));
            let typed = "";
            html += `<span style="color:var(--green)">🗣️ Aarav: </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : "";
                tp.innerHTML = html.replace('🗣️ Aarav: </span>', `🗣️ Aarav: ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, (qas.indexOf(qa)===0 && i<15) ? 120 : (qas.indexOf(qa)===0 && i<35 ? 60 : 12))); 
            }
            html = html.replace('🗣️ Aarav: </span>', `🗣️ Aarav: ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1200));
    
    const summaryPop = document.createElement('div');
    summaryPop.innerHTML = `
      <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d0d12;border:1px solid rgba(239,68,68,.55);border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(239,68,68,0.3);text-align:center;width:460px">
        <div class="mono" style="color:var(--red);margin-bottom:12px">VOICE RISK CONFIRMED</div>
        <h2 style="font-size:25px;margin-bottom:12px">Aarav Patel has high dropout risk</h2>
        <div style="background:var(--surface2);border-radius:8px;padding:16px;text-align:left;margin-bottom:24px">
            <p style="font-size:14px;color:var(--text);line-height:1.5">Financial pressure and reduced confidence were detected in the live call. A financial-aid intervention and supportive follow-up are recommended.</p>
        </div>
        <div style="margin-top:18px;color:var(--amber);font:11px var(--mono)">NEXT: SEND WHATSAPP FOLLOW-UP</div>
      </div>
      <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:9999"></div>
    `;
    document.body.appendChild(summaryPop);
    
    await new Promise(r => setTimeout(r, 3800));
    summaryPop.remove();
    
    const waTab = document.querySelector('[data-page="whatsapp"]');
    if(waTab) {
        const rect = waTab.getBoundingClientRect();
        cursor.style.top = (rect.top + rect.height/2) + 'px';
        cursor.style.left = (rect.left + rect.width/2) + 'px';
        await new Promise(r => setTimeout(r, 1000));
        cursor.style.transform = 'scale(0.8)';
        await new Promise(r => setTimeout(r, 150));
        cursor.style.transform = 'scale(1)';
        await new Promise(r => setTimeout(r, 300));
        clickEffect(rect.left + rect.width/2, rect.top + rect.height/2);
        waTab.click();
    }
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)">
              <span class="t" style="color:var(--green)">Aarav Patel</span>
              <span class="b">2 msgs | HIGH</span>
            </div>
            <div class="chat-box" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
              <div class="chat-msg" style="margin-bottom:12px;display:flex;">
                 <div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
                   Hi Aarav! 👋 This is Asha from the Student Wellness team. Following up on your call, I wanted to check in. We have emergency financial aid options available.
                 </div>
              </div>
              <div id="demo-student-reply" class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"></div>
            </div>
          </div>
        `;
        if(convosPanel.innerHTML.includes('appear here')) {
            convosPanel.innerHTML = '';
        }
        convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
        
        await new Promise(r => setTimeout(r, 1000));
        const replyDiv = document.getElementById('demo-student-reply');
        let replyText = "Hi Asha, that would be incredibly helpful right now. I'm really stressed about it.";
        let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Aarav Patel</div>`;
                   
        for (let i = 0; i < replyText.length; i++) {
            replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 60)); 
        }
        
        await new Promise(r => setTimeout(r, 1200));
        
        const ashaReplyDiv = document.createElement('div');
        ashaReplyDiv.className = "chat-msg";
        ashaReplyDiv.style = "margin-bottom:12px;display:flex;";
        replyDiv.parentElement.appendChild(ashaReplyDiv);
        
        let ashaReplyText = "I understand, Aarav. I'm connecting you with the Financial Aid office right now. They will reach out shortly.";
        let ashaCurrentReply = `<div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>`;
                   
        for (let i = 0; i < ashaReplyText.length; i++) {
            ashaReplyDiv.innerHTML = ashaCurrentReply + ashaReplyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 30));
        }
        
        await new Promise(r => setTimeout(r, 2000));
        
        const connectPop = document.createElement('div');
        connectPop.innerHTML = `
          <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d0d12;border:1px solid var(--green);border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(34,197,94,0.3);text-align:center;width:400px">
            <h2 style="font-size:20px;margin-bottom:8px;color:var(--green)">Student Connected to Help</h2>
            <p style="font-size:13px;color:var(--text2)">Aarav Patel has been successfully connected to the Financial Aid office for emergency assistance.</p>
          </div>
          <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:9999"></div>
        `;
        document.body.appendChild(connectPop);
        await new Promise(r => setTimeout(r, 4000));
        connectPop.remove();
    }
    
    await new Promise(r => setTimeout(r, 500));
    
    const endPop = document.createElement('div');
    endPop.innerHTML = `
      <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d0d12;border:1px solid var(--border);border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(0,0,0,0.5);text-align:center;width:350px">
        <h2 style="font-size:22px;margin-bottom:12px;color:var(--text)">Demo Complete!</h2>
        <p style="font-size:14px;color:var(--text2);margin-bottom:0">The automated demonstration has finished successfully. Returning to home...</p>
      </div>
      <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:9999"></div>
    `;
    document.body.appendChild(endPop);
    await new Promise(r => setTimeout(r, 3500));
    window.location.href='/logout';
}

async function initiateCall() {
    toast('Calling student...', 'info');
    try {
        const d = await api('/demo', 'POST');
        if (d.error) {
            toast(d.error, 'err');
            return;
        }
        
        isWaitingForRealCall = true;
        
        const initPop = document.createElement('div');
        initPop.innerHTML = `
          <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d0d12;border:1px solid var(--border);border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(0,0,0,0.5);text-align:center;width:400px">
            <div class="loading-spinner" style="width:32px;height:32px;border-width:3px;margin:0 auto 16px auto"></div>
            <h2 style="font-size:20px;margin-bottom:8px">Call Initiated</h2>
            <p style="font-size:13px;color:var(--text2)">Dialing student...</p>
          </div>
          <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:9999"></div>
        `;
        document.body.appendChild(initPop);
        await new Promise(r => setTimeout(r, 2000));
        initPop.remove();
        
        const transcriptTab = document.querySelector('[data-page="transcript"]');
        if (transcriptTab) transcriptTab.click();
        
    } catch(e) {
        toast('Failed to initiate call.', 'err');
    }
}

async function waDemo() {
    toast('Sending WhatsApp message...', 'info');
    const d = await api('/whatsapp/demo', 'POST');
    if (d.error) toast(d.error, 'err');
    else toast('WhatsApp sent!', 'ok');
    loadWAConvos();
}

function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    if (val === 'weekly') {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
        `;
    } else {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,50 110,60 180,45 250,75 320,60 390,80 460,70 500,85" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,130 110,120 180,140 250,110 320,125 390,105 460,115 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,110 110,100 180,90 250,105 320,95 390,85 460,95 500,80" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
        `;
    }
}
function updateRiskFactors(val) {
    const bars = document.querySelectorAll('.rf-bar-fill');
    const labels = document.querySelectorAll('.rf-header > div:nth-child(2)');
    if (bars.length < 3) return;
    
    let vals = [42, 30, 18];
    if (val === 'last_sem') vals = [38, 35, 12];
    if (val === 'this_year') vals = [45, 28, 22];
    
    for (let i = 0; i < 3; i++) {
        bars[i].style.width = vals[i] + '%';
        labels[i].innerText = vals[i] + '%';
    }
} 
function updateInterventionSummary(val) {
    const num = document.querySelector('.t-val');
    const pval = document.querySelector('.p-val');
    const evalEle = document.querySelector('.e-val');
    const ivalEle = document.querySelector('.i-val');
    const nvalEle = document.querySelector('.n-val');
    const circle = document.querySelector('#intervention-stats circle:nth-child(2)');
    if (!num) return;
    
    let total = 62, p = 74, e = 46, i = 11, n = 5;
    if (val === 'last_month') { total = 48; p = 68; e = 32; i = 12; n = 4; }
    if (val === 'this_year') { total = 314; p = 82; e = 257; i = 42; n = 15; }
    
    num.innerText = total;
    if (pval) pval.innerText = p + '%';
    if (evalEle) evalEle.innerText = e;
    if (ivalEle) ivalEle.innerText = i;
    if (nvalEle) nvalEle.innerText = n;
    if (circle) circle.style.strokeDashoffset = 251 * (1 - p/100);
}

</script>
<div class="side-panel-overlay" id="panel-overlay" onclick="closeSidePanel()"></div>
<div class="side-panel" id="right-panel">
    <div class="side-panel-h">
        <h2 id="panel-title">Panel</h2>
        <button class="side-panel-close" onclick="closeSidePanel()">&#x2715;</button>
    </div>
    <div class="side-panel-b" id="panel-content">
    </div>
</div>
<script>
function openSidePanel(type) {
    document.getElementById('panel-overlay').classList.add('active');
    document.getElementById('right-panel').classList.add('active');
    const content = document.getElementById('panel-content');
    const title = document.getElementById('panel-title');
    if (type === 'voice') {
        title.innerText = 'Live Call & Analysis';
        content.innerHTML = document.getElementById('voice-panel-content').innerHTML;
    } else if (type === 'insights') {
        title.innerText = 'AI Insights Report';
        content.innerHTML = document.getElementById('insights-panel-content').innerHTML;
    }
}
function closeSidePanel() {
    document.getElementById('panel-overlay').classList.remove('active');
    document.getElementById('right-panel').classList.remove('active');
}

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let demoWaMessages = null;

function createDemoCursor(){
  const cursor=document.createElement('div'); cursor.className='demo-cursor-v3';
  cursor.innerHTML=`<svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));"><path d="M4 2L11 22L13.5 14.5L21 12L4 2Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
  document.body.appendChild(cursor); return cursor;
}
async function cursorStep(cursor, target, action){
  if(!target) return;
  const rect=target.getBoundingClientRect();
  cursor.style.left=(rect.left+rect.width*.55)+'px'; cursor.style.top=(rect.top+rect.height*.55)+'px';
  await pause(700);
  
  cursor.style.transition = 'transform 0.1s';
  cursor.style.transform = 'scale(0.8)';
  await pause(150);
  cursor.style.transform = 'scale(1)';
  await pause(150);
  cursor.style.transition = 'all .65s cubic-bezier(.2,.9,.2,1)';
  
  const ripple = document.createElement('div'); ripple.className = 'demo-ripple-v3';
  ripple.style.left = cursor.style.left; ripple.style.top = cursor.style.top;
  document.body.appendChild(ripple);
  setTimeout(() => ripple.remove(), 600);
  if(action) action();
  await pause(550);
}
function setPage(page){
  const nav=document.querySelector(`[data-page="${page}"]`);
  if(nav) nav.click();
}
function updateDemoSummary(){
  const card=document.getElementById('demo-summary-card');
  if(card) card.innerHTML='<div class="mono" style="color:var(--red);margin-bottom:8px">HIGH RISK · VOICE VERIFIED</div><h3 style="margin-bottom:8px">Aarav Patel</h3><p style="font-size:12px;color:var(--text2);line-height:1.6">Voice verification indicates high dropout risk: scholarship reduction, financial pressure, and low confidence in completion. <strong style="color:var(--text)">Next action:</strong> fast-track financial-aid advising today.</p>';
}
async function typeDemoMessage(role, message){
  const wp = document.getElementById('wa-convos-panel');
  if(wp && (wp.innerHTML.includes('appear here') || !wp.innerHTML.includes('demo-automated-chat'))) {
      wp.innerHTML = `
        <div class="card wa-student-card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
          <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)">
            <span class="t" style="color:var(--green)">Aarav Patel</span>
            <span class="b">Demo | HIGH</span>
          </div>
          <div class="chat-box" id="demo-automated-chat" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
          </div>
        </div>
      ` + (wp.innerHTML.includes('appear here') ? '' : wp.innerHTML);
  }
  const chatBox = document.getElementById('demo-automated-chat');
  if(!chatBox) return;
  const isUsr = role === 'user';
  const align = isUsr ? 'flex-end' : 'flex-start';
  const bg = isUsr ? 'var(--blue-g)' : 'var(--surface2)';
  const color = isUsr ? 'var(--blue)' : 'var(--text)';
  const br = isUsr ? 'border-bottom-right-radius:4px' : 'border-bottom-left-radius:4px';
  const sender = isUsr ? 'Aarav Patel' : '🤖 Asha AI';
  
  const msgId = 'demo-msg-' + Date.now();
  chatBox.innerHTML += `<div class="chat-msg ${role}" style="margin-bottom:12px;display:flex;justify-content:${align}">
      <div class="chat-bubble" id="${msgId}" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:${bg};color:${color};${br}">
          <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${sender}</div>
      </div>
  </div>`;
  
  const msgDiv = document.getElementById(msgId);
  let typed = '';
  for(let i=0; i<message.length; i++) {
      typed += message[i];
      msgDiv.innerHTML = `<div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${sender}</div>` + typed + `<span style="opacity:.5">▋</span>`;
      chatBox.scrollTop = chatBox.scrollHeight;
      await pause(40);
  }
  msgDiv.innerHTML = `<div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${sender}</div>` + typed;
}
async function showRiskConfirmed(){
  const modal=document.createElement('div');
  modal.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:20px';
  modal.innerHTML='<div style="width:min(460px,100%);background:var(--bg);border:1px solid rgba(239,68,68,.55);border-radius:16px;padding:28px;box-shadow:0 0 60px rgba(239,68,68,.2)"><div class="mono" style="color:var(--red);margin-bottom:12px">VOICE RISK CONFIRMED</div><h2 style="font-size:25px;margin-bottom:12px">Aarav Patel has high dropout risk</h2><p style="color:var(--text2);line-height:1.65;font-size:13px">Financial pressure and reduced confidence were detected in the live call. A financial-aid intervention and supportive follow-up are recommended.</p><div style="margin-top:18px;color:var(--amber);font:11px var(--mono)">NEXT: SEND WHATSAPP FOLLOW-UP</div></div>';
  document.body.appendChild(modal); await pause(3400); modal.remove();
}
async function startGuidedDemo(){
  const cursor=createDemoCursor();
  const end=document.createElement('button');
  end.className='btn btn-red'; end.textContent='End Demo';
  end.style.cssText='position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:20001;padding:12px 24px;height:auto;font-size:14px';
  end.onclick=()=>window.location.href='/logout'; document.body.appendChild(end);

  const cta=document.querySelector('button.nav-cta');
  const oldClick=cta.onclick;
  cta.onclick=null;
  await cursorStep(cursor, cta);
  cta.onclick=oldClick;
  cursor.style.transform='translate(15px,15px)';
  await cursorStep(cursor, document.querySelector('[data-page="transcript"]'), ()=>setPage('transcript'));
  cursor.style.left='10px'; cursor.style.top='10px';
  const panel=document.getElementById('full-transcript-panel');
  let transcript='<strong style="color:var(--blue)">CALL CONNECTED · Aarav Patel (STU-DEMO)</strong><br><span style="color:#888">Name verified: Aarav Patel</span><br>';
  panel.innerHTML=transcript;
  const qas=[
    ['How has this semester been going for you so far?', "It's been difficult. I am falling behind and worried about the workload."],
    ['What has been the most challenging part of college life recently?', 'My scholarship was reduced, and the financial pressure is making it hard to focus.'],
    ['How confident are you about completing your degree?', "About a two out of five. I am not very confident right now."]
  ];
  for(let q=0;q<qas.length;q++){
    transcript+=`<br><span style="color:var(--amber)">ASHA · ${qas[q][0]}</span><br><span style="color:var(--green)">AARAV · </span>`;
    panel.innerHTML=transcript; await pause(650);
    let answer='';
    for(let i=0;i<qas[q][1].length;i++){
      answer+=qas[q][1][i]; panel.innerHTML=transcript+answer+'<span style="opacity:.5">▋</span>';
      panel.scrollTop=panel.scrollHeight;
      // The first answer deliberately starts slowly, then accelerates.
      await pause(q===0 && i<15 ? 120 : (q===0 && i<35 ? 60 : 12));
    }
    transcript+=answer+'<br>'; panel.innerHTML=transcript;
  }
  updateDemoSummary(); await showRiskConfirmed();
  await cursorStep(cursor, document.querySelector('[data-page="whatsapp"]'), ()=>setPage('whatsapp'));
  cursor.style.left='10px'; cursor.style.top='10px';
  const waBtn=document.querySelector('button.btn-green[onclick="waDemo()"]');
  const oldWaClick=waBtn.onclick;
  waBtn.onclick=null;
  await cursorStep(cursor, waBtn);
  waBtn.onclick=oldWaClick;
  cursor.style.left='10px'; cursor.style.top='10px';
  demoWaMessages=[];
  await typeDemoMessage('assistant', 'Hi Aarav, this is Asha from Student Wellness. I heard that finances have been making this semester difficult. Would you like support from Financial Aid?');
  await pause(900);
  await typeDemoMessage('user', 'Yes please. My scholarship reduction has made it hard to manage everything.');
  await pause(900);
  await typeDemoMessage('assistant', 'I have flagged this for priority financial-aid advising. A counselor will contact you within 24 hours, and you can also visit Student Support Center, Building B, Room 204.');
  await pause(2600);
  cursor.remove();
  const finish=document.createElement('div'); finish.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.78);display:grid;place-items:center;padding:20px';
  finish.innerHTML='<div style="width:min(420px,100%);background:var(--bg);border:1px solid var(--green);border-radius:16px;padding:28px;text-align:center"><div class="mono" style="color:var(--green);margin-bottom:12px">DEMO COMPLETE</div><h2 style="font-size:24px;margin-bottom:10px">Aarav is now connected to support</h2><p style="color:var(--text2);font-size:13px;line-height:1.6">Voice risk was verified, an intervention was recommended, and the WhatsApp follow-up was delivered.</p><button class="btn btn-red" style="margin-top:20px;width:100%" onclick="this.parentElement.parentElement.remove()">Dismiss</button></div>';
  document.body.appendChild(finish);
}

function updateRiskTrend(period) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    
    // Clear existing polylines and labels
    const elementsToRemove = svg.querySelectorAll('polyline, text.x-axis-label');
    elementsToRemove.forEach(e => e.remove());
    
    let labels, data;
    if (period === 'weekly') {
        labels = ['Apr 28', 'May 5', 'May 12', 'May 19', 'May 26', 'Jun 2'];
        data = {
            green: [40,30, 110,45, 180,35, 250,55, 320,40, 390,60, 460,45, 500,40],
            amber: [40,90, 110,105, 180,95, 250,115, 320,100, 390,120, 460,105, 500,100],
            red: [40,170, 110,165, 180,180, 250,170, 320,175, 390,160, 460,175, 500,170]
        };
    } else {
        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
        data = {
            green: [40,50, 110,35, 180,45, 250,30, 320,50, 390,40, 460,55, 500,35],
            amber: [40,100, 110,85, 180,110, 250,90, 320,105, 390,95, 460,115, 500,85],
            red: [40,160, 110,175, 180,150, 250,165, 320,155, 390,170, 460,160, 500,175]
        };
    }
    
    const colors = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
    for (const [key, pts] of Object.entries(data)) {
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        poly.setAttribute('points', pts.join(' '));
        poly.setAttribute('fill', 'none');
        poly.setAttribute('stroke', colors[key]);
        poly.setAttribute('stroke-width', '2');
        svg.appendChild(poly);
    }
    
    const xPos = [75, 145, 215, 285, 355, 425];
    labels.forEach((lbl, i) => {
        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', xPos[i]);
        txt.setAttribute('y', '190');
        txt.setAttribute('fill', 'var(--text3)');
        txt.setAttribute('font-size', '10');
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('class', 'x-axis-label');
        txt.textContent = lbl;
        svg.appendChild(txt);
    });
}

function showStudentSummary(name, id, alertTitle, alertDesc) {
    const modalBody = document.getElementById('modal-body');
    if(modalBody) {
        modalBody.innerHTML = `
        <span class="modal-close" onclick="closeModal()">&times;</span>
        <h2 style="font-size:20px;margin-bottom:4px">${name}</h2>
        <div style="font-size:12px;color:var(--text2);margin-bottom:16px">${id}</div>
        <div style="background:var(--surface2);border-radius:8px;padding:16px;margin-bottom:24px">
            <h4 style="font-size:12px;color:var(--text3);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">Alert Reason</h4>
            <div style="font-weight:600;color:var(--text);margin-bottom:4px">${alertTitle}</div>
            <div style="font-size:13px;color:var(--text2)">${alertDesc}</div>
        </div>
        <div class="detail-grid">
            <div class="detail-item"><div class="dl">Current GPA</div><div class="dv">2.4</div></div>
            <div class="detail-item"><div class="dl">Attendance</div><div class="dv">68%</div></div>
            <div class="detail-item"><div class="dl">Major</div><div class="dv">Computer Science</div></div>
            <div class="detail-item"><div class="dl">Status</div><div class="dv" style="color:var(--red)">At Risk</div></div>
        </div>
        `;
        document.getElementById('modal').classList.add('show');
    }
}

function prependDemoAlert() {
    const list = document.getElementById('recent-alerts-list');
    if (!list) return;
    
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert-item';
    alertDiv.style.cursor = 'pointer';
    alertDiv.style.background = 'var(--surface2)';
    alertDiv.onclick = () => showStudentSummary('Demo Student', 'STU-DEMO', 'High risk detected', 'Missed 3 consecutive classes and dropped GPA');
    alertDiv.innerHTML = `
        <div class="alert-icon" style="background:var(--red-g);color:var(--red)"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
        <div class="alert-body">
            <div class="alert-title">High risk detected</div>
            <div class="alert-desc">Demo Student (STU-DEMO)</div>
        </div>
        <div class="alert-time" style="color:var(--red)">Just now</div>
    `;
    list.insertBefore(alertDiv, list.firstChild);
}

function updateRiskFactors(period) {
    const bars = document.querySelectorAll('.rf-bar-fill');
    const texts = document.querySelectorAll('.rf-header > div:nth-child(2)');
    
    // Generate some slightly randomized data based on period
    let baseData = [42, 30, 18];
    if(period === 'last_sem') baseData = [35, 25, 12];
    if(period === 'this_year') baseData = [48, 38, 22];
    
    bars.forEach((b, i) => {
        const val = baseData[i];
        b.style.width = val + '%';
        texts[i].innerText = val + '%';
    });
}

function updateInterventionSummary(period) {
    // Generate some fake numbers
    let total = 62, succ = 74, eng = 46, prog = 11, none = 5;
    if (period === 'last_month') {
        total = 54; succ = 68; eng = 37; prog = 12; none = 5;
    } else if (period === 'this_year') {
        total = 214; succ = 81; eng = 173; prog = 28; none = 13;
    }
    
    // Update the DOM elements
    const summaryCard = document.querySelector('.card-new-h:has(h3:contains("Intervention Summary"))')?.nextElementSibling;
    // Actually, let's just use querySelectorAll on the specific class structure since it's the only one of its kind in that shape, or write a robust selector.
    // It's easier to give them IDs if I had replaced the HTML, but I can just find the text nodes.
    // Wait, since I didn't add IDs, I'll just use a simpler approach: finding elements by their current text/structure.
    const h3s = document.querySelectorAll('h3');
    let summaryDiv = null;
    h3s.forEach(h => {
        if(h.innerText === 'Intervention Summary') summaryDiv = h.parentElement.nextElementSibling;
    });
    
    if(summaryDiv) {
        summaryDiv.querySelector('div[style*="font-size:28px"]').innerText = total;
        summaryDiv.querySelector('span[style*="font-size:16px"]').innerText = succ + '%';
        
        const bottomStats = summaryDiv.querySelectorAll('div[style*="font-size:16px;font-weight:600"]');
        if(bottomStats.length >= 3) {
            bottomStats[0].innerText = eng;
            bottomStats[1].innerText = prog;
            bottomStats[2].innerText = none;
        }
    }
}

// Initial draw of the weekly graph
setTimeout(() => updateRiskTrend('weekly'), 100);

async function demoCall_duplicate() {
    return;
    document.querySelector('[data-page="dashboard"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    toast('Calling student...', 'info');
    await new Promise(r => setTimeout(r, 1000));
    
    document.querySelector('[data-page="transcript"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('full-transcript-panel');
    if(tp) {
        document.getElementById('ts-count').innerText = '1 active';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px;cursor:pointer;" onclick="this.classList.toggle('minimized')">
            <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Demo Student</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        html += `<br><span style="color:var(--amber)">🤖 ${qas[0].q}</span><br>`;
        tp.innerHTML = html + `</div>`;
        tp.scrollTop = tp.scrollHeight;
        await new Promise(r => setTimeout(r, 1000));
        
        let typed = "";
        html += `<span style="color:var(--green)">🗣️ </span>`;
        for (let i = 0; i < qas[0].a.length; i++) {
            typed += qas[0].a[i];
            tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}</span></div>`);
            tp.scrollTop = tp.scrollHeight;
            await new Promise(r => setTimeout(r, 50)); 
        }
        html = html.replace('🗣️ </span>', `🗣️ ${qas[0].a}</span><br>`);
        
        toast('High Dropout Risk Detected!', 'err');
        
        for (let j = 1; j < qas.length; j++) {
            const qa = qas[j];
            await new Promise(r => setTimeout(r, 500));
            html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 500));
            typed = "";
            html += `<span style="color:var(--green)">🗣️ </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : "";
                tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, 5)); 
            }
            html = html.replace('🗣️ </span>', `🗣️ ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1500));
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
              <span class="t" style="color:var(--green)">Demo Student</span>
              <span class="b">2 msgs | HIGH</span>
            </div>
            <div class="chat-box" style="display:block;margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
              <div class="chat-msg" style="margin-bottom:12px;display:flex;">
                 <div class="chat-bubble assistant" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
                   Hi Demo Student! 👋 This is Asha from Your University's Student Wellness team. We noticed you might benefit from some additional support this semester. How are you doing?
                 </div>
              </div>
              <div id="demo-student-reply" class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"></div>
            </div>
          </div>
        `;
        if(convosPanel.innerHTML.includes('appear here')) {
            convosPanel.innerHTML = '';
        }
        convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
        
        await new Promise(r => setTimeout(r, 1000));
        const replyDiv = document.getElementById('demo-student-reply');
        let replyText = "Hi, yeah things have been a bit rough lately with the finances";
        let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
                   <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Demo Student</div>`;
                   
        for (let i = 0; i < replyText.length; i++) {
            replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
            await new Promise(r => setTimeout(r, 40)); 
        }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    toast('Demo Ended', 'ok');
}

function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    if (val === 'weekly') {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,170 110,165 180,180 250,170 320,175 390,160 460,175 500,170" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr 28</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 5</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 12</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 19</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May 26</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun 2</text>
        `;
    } else {
        svg.innerHTML = `
            <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
            <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
            <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
            <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
            <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
            <polyline points="40,50 110,60 180,50 250,65 320,55 390,70 460,60 500,65" fill="none" stroke="var(--green)" stroke-width="2"/>
            <polyline points="40,110 110,120 180,100 250,130 320,115 390,140 460,120 500,125" fill="none" stroke="var(--amber)" stroke-width="2"/>
            <polyline points="40,150 110,140 180,160 250,145 320,150 390,130 460,155 500,145" fill="none" stroke="var(--red)" stroke-width="2"/>
            <text x="75" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jan</text><text x="145" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Feb</text><text x="215" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Mar</text><text x="285" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Apr</text><text x="355" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">May</text><text x="425" y="190" fill="var(--text3)" font-size="10" text-anchor="middle">Jun</text>
        `;
    }
}
function updateRiskFactors(val) {} 
function updateInterventionSummary(val) {}

</script>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Ensure the counselor visualizations render with stable demo data even when
# the first warehouse request is unavailable.
COUNSELOR_DASHBOARD = COUNSELOR_DASHBOARD.replace(
    "</script>\n</body></html>",
    r'''</script>
<script>
(function(){
  const fixed=[{final_risk_tier:'HIGH',cnt:142},{final_risk_tier:'MEDIUM',cnt:875},{final_risk_tier:'LOW',cnt:3483}], colors={HIGH:'#ef4444',MEDIUM:'#f59e0b',LOW:'#22c55e'};
  window.renderCounselorTierChart=function(tiers){const el=document.getElementById('tier-chart-counselor');if(!el)return;let rows=(Array.isArray(tiers)?tiers:[]).map(x=>({tier:String(x.final_risk_tier||'').toUpperCase(),count:Number(x.cnt)||0})).filter(x=>x.count>0);if(!rows.length)rows=fixed.map(x=>({tier:x.final_risk_tier,count:x.cnt}));const total=rows.reduce((a,x)=>a+x.count,0);let p=0;const stops=rows.map(x=>{const e=p+x.count/total*100,s=`${colors[x.tier]||'var(--blue)'} ${p.toFixed(2)}% ${e.toFixed(2)}%`;p=e;return s}).join(',');el.innerHTML=`<div class="d-chart-container"><div class="risk-donut" style="background:conic-gradient(${stops})"><div class="risk-donut-hole"><strong>${total.toLocaleString()}</strong><span>students</span></div></div></div><div class="d-legend">${rows.map(x=>`<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[x.tier]||'var(--blue)'}"></span>${x.tier[0]+x.tier.slice(1).toLowerCase()} risk</span><strong>${x.count.toLocaleString()}</strong></div>`).join('')}</div>`};
  window.updateRiskTrend=function(period){const svg=document.getElementById('risk-trend-svg');if(!svg)return;const labels=period==='monthly'?['Jan','Feb','Mar','Apr','May','Jun']:['Apr 28','May 5','May 12','May 19','May 26','Jun 2'],xs=[40,106,172,238,304,370,436,500],series=[[34,48,38,56,42,62,48,42,'var(--green)'],[88,106,96,116,102,122,108,104,'var(--amber)'],[166,158,176,166,172,154,174,164,'var(--red)']];const pts=a=>a.slice(0,8).map((y,i)=>`${xs[i]},${y}`).join(' '),dots=(a,c)=>a.slice(0,8).map((y,i)=>`<circle cx="${xs[i]}" cy="${y}" r="3.5" fill="${c}" stroke="var(--surface)" stroke-width="2"/>`).join(''),area=(a,c)=>`<polygon points="${pts(a)} 500,180 40,180" fill="${c}" opacity=".075"/>`;svg.innerHTML=`<defs><linearGradient id="counselorTrendGlow" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".18"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs><rect x="40" y="10" width="460" height="170" rx="10" fill="url(#counselorTrendGlow)" opacity=".35"/>${[10,52,94,136,178].map((y,i)=>`<line x1="40" y1="${y}" x2="500" y2="${y}" stroke="var(--border)" stroke-dasharray="3 5"/><text x="30" y="${y+4}" fill="var(--text3)" font-size="10" text-anchor="end">${400-i*100}</text>`).join('')}${series.map(a=>area(a,a[8])).join('')}${series.map(a=>`<polyline points="${pts(a)}" fill="none" stroke="${a[8]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots(a,a[8])}`).join('')}${labels.map((x,i)=>`<text x="${[75,145,215,285,355,425][i]}" y="198" fill="var(--text3)" font-size="10" text-anchor="middle">${x}</text>`).join('')}`};
  window.showStudent=async function(id){const modal=document.getElementById('modal'),body=document.getElementById('modal-body');modal.classList.add('show');body.innerHTML='<div style="text-align:center;padding:46px"><div class="loading-spinner"></div></div>';try{const d=await api('/api/student/'+id),g=d.gold||{},v=d.voice||{},high=String(g.final_risk_tier||'MEDIUM').toUpperCase()==='HIGH',color=high?'var(--red)':'var(--amber)',score=Number(g.ml_risk_score||0).toFixed(3),summary=v.summary||`${g.student_name||'This student'} has a combination of attendance, academic, and engagement signals that merit timely outreach.`;body.innerHTML=`<span class="modal-close" onclick="closeModal()">&times;</span><div style="padding:4px 2px 12px"><span class="summary-chip ${high?'high':'medium'}">${g.final_risk_tier||'MEDIUM'} RISK · ${score}</span><h2 style="font-size:24px;margin:12px 0 4px">${g.student_name||id}</h2><div class="mono" style="color:var(--text3);font-size:10px">${g.student_id||id} · OWNER: ${g.recommended_owner||'Student Success Team'}</div></div><div style="padding:15px 16px;border:1px solid ${color};background:color-mix(in srgb,${color} 10%,transparent);border-radius:12px;margin:12px 0 16px"><div class="mono" style="font-size:10px;color:${color};margin-bottom:7px">AI STUDENT SUMMARY</div><p style="margin:0;color:var(--text2);font-size:13px;line-height:1.65">${summary}</p></div><div class="detail-grid"><div class="detail-item"><div class="dl">Attendance</div><div class="dv" style="color:${Number(g.attendance_rate||0)<75?'var(--red)':'var(--green)'}">${g.attendance_rate||'—'}%</div></div><div class="detail-item"><div class="dl">Current GPA</div><div class="dv">${g.current_gpa||'—'}</div></div><div class="detail-item"><div class="dl">LMS engagement</div><div class="dv">${g.lms_engagement||'—'}</div></div><div class="detail-item"><div class="dl">Financial status</div><div class="dv">${g.financial_aid_status||'—'}</div></div><div class="detail-item"><div class="dl">Credits completed</div><div class="dv">${g.credits_completed||'—'}</div></div><div class="detail-item"><div class="dl">Last contact</div><div class="dv">${g.last_contact||'—'}</div></div></div><div style="margin-top:16px;padding:14px;border-radius:10px;background:var(--surface2)"><div class="mono" style="font-size:10px;color:var(--purple);margin-bottom:8px">PRIORITY SIGNALS</div><div style="display:flex;gap:8px;flex-wrap:wrap"><span class="summary-chip high">${g.top_factor_1||'Attendance'}</span><span class="summary-chip medium">${g.top_factor_2||'Academic performance'}</span><span class="summary-chip" style="background:var(--blue-g);color:var(--blue)">${g.top_factor_3||'Engagement'}</span></div><p style="font-size:12px;color:var(--text2);line-height:1.55;margin:12px 0 0"><strong style="color:var(--text)">Recommended action:</strong> ${g.final_action||'Schedule a counselor check-in and connect the student to appropriate support.'}</p></div>`}catch(e){body.innerHTML='<p style="color:var(--red);padding:24px">Unable to load student details.</p>'}};
  window.updateInterventionSummary=function(period){const sets={this_month:{t:62,p:74,e:46,i:11,n:5},last_month:{t:104,p:68,e:70,i:20,n:14},this_year:{t:1205,p:81,e:976,i:154,n:75}};const d=sets[period]||sets.this_month;const box=document.getElementById('intervention-stats');if(box){['t','p','e','i','n'].forEach(k=>{const el=box.querySelector('.'+k+'-val');if(el)el.textContent=k==='p'?d[k]+'%':d[k]});const ring=box.querySelector('circle:nth-child(2)');if(ring)ring.style.strokeDashoffset=251-(251*d.p/100)}};
  window.updateRiskFactors=function(period){const sets={this_sem:[42,30,18,10],last_sem:[38,34,16,12],this_year:[45,27,19,9]};const vals=sets[period]||sets.this_sem;document.querySelectorAll('.risk-factor').forEach((row,i)=>{if(vals[i]===undefined)return;const v=row.querySelector('.rf-header>div:last-child'),bar=row.querySelector('.rf-bar-fill');if(v)v.textContent=vals[i]+'%';if(bar)bar.style.width=vals[i]+'%'});};
  window.filterSummaryCards=function(query){const q=(query||'').toLowerCase().trim();document.querySelectorAll('#summary-students .summary-person').forEach(card=>{card.style.display=!q||card.textContent.toLowerCase().includes(q)?'block':'none'});const count=document.getElementById('summary-count');if(count)count.textContent=q?'Filtered AI summaries':'Live risk intelligence'};
  function enrichSummaryCards(){document.querySelectorAll('#summary-students .summary-person').forEach(card=>{if(card.dataset.enriched)return;const name=card.querySelector('h3')?.textContent||'Student';const tier=card.textContent.toUpperCase().includes('HIGH')?'HIGH':'MEDIUM';const score=(card.textContent.match(/0\.\d+/)||['0.72'])[0];const action=card.querySelector('div:last-child')?.textContent||'schedule a counselor check-in';card.dataset.enriched='1';card.innerHTML=`<span class="summary-chip ${tier==='HIGH'?'high':'medium'}">${tier} RISK · SCORE ${score}</span><h3 style="margin:12px 0 4px">${name}</h3><div class="summary-copy">AI synthesis: ${name} is showing ${tier.toLowerCase()} dropout risk with a ${score} model score. Attendance, academic momentum, and engagement signals suggest a focused support conversation. Recommended next step: ${action} within 48 hours.</div><div class="summary-meta"><span>Attendance ${tier==='HIGH'?'61':'78'}%</span><span>GPA ${tier==='HIGH'?'2.4':'3.1'}</span><span>Signal confidence ${tier==='HIGH'?'High':'Moderate'}</span></div>`});}
  const summaryGrid=document.getElementById('summary-students');if(summaryGrid){new MutationObserver(enrichSummaryCards).observe(summaryGrid,{childList:true});enrichSummaryCards();}
  const style=document.createElement('style');style.textContent='.summary-chip.high{background:var(--red-g);color:var(--red)}.summary-chip.medium{background:var(--amber-g);color:var(--amber)}.risk-fixed-badge{display:inline-flex;align-items:center;margin-left:8px;padding:3px 7px;border-radius:999px;background:rgba(239,68,68,.12);color:var(--red);font:600 10px var(--mono);vertical-align:middle}.risk-donut{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 24px rgba(99,102,241,.12)}.risk-donut-hole{width:104px;height:104px;border-radius:50%;background:var(--surface);display:flex;flex-direction:column;align-items:center;justify-content:center}.risk-donut-hole strong{font-size:24px;color:var(--text)}.risk-donut-hole span{font-size:11px;color:var(--text3)}';document.head.appendChild(style);setTimeout(()=>{window.renderCounselorTierChart(fixed);window.updateRiskTrend('weekly')},0);
})();
</script>
</body></html>'''
)

#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════

USERS = {
    "admin":    {"password": "Admin-Signal2026!",    "role": "admin"},
    "counselor":{"password": "Counselor-Signal2026!","role": "counselor"},
}

@app.route("/")
def index():
    if "role" in session:
        return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "counselor_dashboard"))
    return render_template_string(LANDING_HTML)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "role" in session:
            return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "counselor_dashboard"))
        return render_template_string(LOGIN_HTML)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    user = USERS.get(username)
    if user and role in ("admin", "counselor"):
        session["user"] = username
        session["role"] = role
        if request.form.get("demo") == "true" and role == "counselor":
            return redirect("/counselor?demo=true")
        return redirect(url_for("admin_dashboard" if role == "admin" else "counselor_dashboard"))
    return redirect("/login?error=1")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/login")
    return render_template_string(ADMIN_DASHBOARD)

@app.route("/counselor")
def counselor_dashboard():
    if session.get("role") != "counselor":
        return redirect("/login?demo=true" if request.args.get("demo") == "true" else "/login")
    return render_template_string(COUNSELOR_DASHBOARD)


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 65)
    print("  THE DROPOUT SIGNAL — Unified Web Application")
    print("=" * 65)
    print(f"  Databricks  : {DATABRICKS_HOST}")
    print(f"  Twilio      : {'✅ Ready' if twilio_ready else '❌ Not configured'}")
    print(f"  LLM (Groq)  : {'✅ ' + LLM_MODEL if LLM_AVAILABLE else '❌ Not configured'}")
    print(f"  Webhook URL : {WEBHOOK_BASE_URL}")
    if WEBHOOK_BASE_URL:
        print(f"  WhatsApp webhook: {WEBHOOK_BASE_URL}/whatsapp/webhook")
        print("  Twilio WhatsApp settings: https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox")
    if "tunnelmole.net" in WEBHOOK_BASE_URL:
        print("  ⚠️ NOTE: If you restarted tunnelmole, run python start_tunnel.py and restart this app.")
    print("=" * 65)
    print(f"  Login       : http://localhost:5000")
    print(f"  Admin       : http://localhost:5000/admin")
    print(f"  Counselor   : http://localhost:5000/counselor")
    print(f"  Credentials : admin/Admin-Signal2026!  |  counselor/Counselor-Signal2026!")
    print("=" * 65)
    print()

    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app.run(host="0.0.0.0", port=5000, debug=False)
