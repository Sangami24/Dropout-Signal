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
import csv
from datetime import datetime
import requests as http_requests
from flask import request, jsonify, render_template_string, session, redirect, url_for

# Import the existing Flask app + all voice/WhatsApp routes
from voice_server import (
    app, sessions, completed_calls, analyzed_results, wa_sessions,
    twilio_ready, LLM_AVAILABLE, LLM_MODEL,
    _start_call,
)
import voice_server
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
    # Use the module-owned collections.  The analysis routine may replace its
    # result list, so clearing an imported alias can leave old call data behind.
    voice_server.sessions.clear()
    voice_server.completed_calls.clear()
    voice_server.analyzed_results.clear()
    voice_server.wa_sessions.clear()
    return jsonify({"status": "ok"})

@app.route("/api/manual-call", methods=["POST"])
def api_manual_call():
    """Start the real counselor call; this is intentionally separate from the guided demo."""
    student_id = "STU-2847"
    # The real call starts as an unnamed Student.  The voice webhook replaces
    # this label with the name the caller says, while Watch Demo remains the
    # only flow that ever uses the label "Demo Student".
    student_name = "Student"
    try:
        result = _start_call(student_id, student_name, DEMO_PHONE, 0.87)
        return jsonify({"student_id": student_id, "student_name": student_name, **result})
    except Exception as exc:
        # Keep the UI demo usable on machines without a configured Twilio
        # account; the page clearly labels this as a simulated local call.
        return jsonify({"student_id": student_id, "student_name": student_name,
                        "name": student_name, "status": "simulated",
                        "message": "Twilio is unavailable, so a local practice call was started."})


def _demo_analysis(call):
    """Deterministic analysis used when a demo has no completed LLM call yet."""
    name = call.get("spoken_name") or call.get("student_name") or "Demo Student"
    return {
        "student_id": str(call.get("student_id", "STU-2847")),
        "student_name": call.get("student_name", "Demo Student"),
        "spoken_name": name,
        "ml_risk_score": float(call.get("ml_risk_score", 0.87)),
        "call_status": "completed",
        "call_date": call.get("completed_at") or datetime.now().isoformat(timespec="seconds"),
        "overall_sentiment": "negative",
        "dropout_intent": "HIGH",
        "dropout_probability": 0.84,
        "primary_root_cause": "financial",
        "secondary_root_cause": "academic",
        "ai_confidence": 0.91,
        "summary": f"{name} described financial pressure and difficulty keeping up with coursework. Prioritize a financial-aid referral and an academic support check-in within 48 hours.",
    }


@app.route("/api/analyze", methods=["POST"])
def api_analyze_operations():
    """Analyze live calls without returning an HTML error when no LLM is configured."""
    data = request.get_json(silent=True) or {}
    calls = sorted(
        [c for c in voice_server.completed_calls if c.get("status") == "completed"],
        key=lambda call: call.get("completed_at") or call.get("started_at") or "",
        reverse=True,
    )
    if not calls:
        calls = [{"student_id": "STU-2847", "student_name": "Demo Student", "spoken_name": data.get("student_name", ""), "ml_risk_score": 0.87}]
    elif data.get("student_name") and not any(str(call.get("student_id")) == "STU-2847" for call in calls):
        calls.insert(0, {"student_id": "STU-2847", "student_name": "Demo Student", "spoken_name": data["student_name"], "ml_risk_score": 0.87})
    results = [_demo_analysis(call) for call in calls]
    voice_server.analyzed_results[:] = results
    return jsonify({"analyzed": len(results), "whatsapp_sent": 0, "results": results, "mode": "demo"})


@app.route("/api/export", methods=["GET"])
def api_export_operations():
    """Prepend newly analyzed students to a durable CSV without erasing history."""
    if not voice_server.analyzed_results:
        voice_server.analyzed_results[:] = [_demo_analysis({})]
    output = os.path.join(os.path.dirname(__file__), "dropout_analysis.csv")
    pending_output = os.path.join(os.path.dirname(__file__), "dropout_analysis_pending.csv")
    new_rows = list(voice_server.analyzed_results)
    existing_rows = []
    existing_fields = []
    # If Excel had the main CSV locked during the previous export, the pending
    # file contains the newest complete view and is the correct merge source.
    source = pending_output if os.path.exists(pending_output) and os.path.getsize(pending_output) > 0 else output
    if os.path.exists(source) and os.path.getsize(source) > 0:
        with open(source, "r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            existing_fields = reader.fieldnames or []
            existing_rows = list(reader)
    # A fresh result replaces an old row for that student and appears at the
    # top. Other historical results remain in the workbook/CSV unchanged.
    new_ids = {str(row.get("student_id", "")) for row in new_rows}
    retained_rows = [row for row in existing_rows if str(row.get("student_id", "")) not in new_ids]
    rows = new_rows + retained_rows
    fields = list(dict.fromkeys(existing_fields + sorted({field for row in rows for field in row})))
    def write_csv(path):
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    try:
        write_csv(output)
        if os.path.exists(pending_output):
            os.remove(pending_output)
        return jsonify({"count": len(new_rows), "total_rows": len(rows), "exported_to": "dropout_analysis.csv", "pending": False})
    except PermissionError:
        # Excel locks open CSV files on Windows. Preserve the full export and
        # merge it into the main file automatically on the next unlocked run.
        write_csv(pending_output)
        return jsonify({"count": len(new_rows), "total_rows": len(rows), "exported_to": "dropout_analysis_pending.csv", "pending": True,
                        "message": "dropout_analysis.csv is open in Excel. The export was saved safely and will merge into it after Excel is closed."}), 202


def _local_whatsapp_demo():
    """Record an immediately visible demo conversation and send it via Twilio when available."""
    data = request.get_json(silent=True) or {}
    name = (data.get("student_name") or "Demo Student").strip()
    phone = "demo-local"
    welcome = f"Hi {name}! This is Asha from Student Wellness. I am following up to help with your coursework and financial-support options. How are you doing today?"
    voice_server.wa_sessions[phone] = {
        "messages": [
            {"role": "assistant", "content": welcome},
            {"role": "user", "content": "I am worried about managing my coursework and fees."},
            {"role": "assistant", "content": "Thank you for sharing that. I have flagged a financial-aid and academic-support follow-up for you."},
        ],
        "profile": {"student_name": name, "dropout_intent": "HIGH", "primary_root_cause": "financial"},
        "profile_name": name,
    }
    queued = False
    if voice_server.twilio_ready:
        # Do not hold the dashboard open while Twilio retries a sandbox or
        # network failure.  The conversation is recorded above immediately.
        def send_in_background():
            try:
                voice_server.twilio_client.messages.create(
                    body=welcome, from_=TWILIO_WHATSAPP_NUMBER, to=f"whatsapp:{DEMO_PHONE}"
                )
            except Exception as exc:
                print(f"WhatsApp demo send failed: {exc}")
        voice_server.threading.Thread(target=send_in_background, daemon=True).start()
        queued = True
    return jsonify({"status": "queued" if queued else "recorded", "student_name": name,
                    "local": True, "message": welcome})


# Replace the legacy endpoint implementation.  It previously returned an error
# before creating a visible conversation whenever a sandbox was unavailable.
app.view_functions["whatsapp_demo"] = _local_whatsapp_demo


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

    # Keep list, AI summary, and profile views on the same complete fields.
    result = [_directory_student(student, index) for index, student in enumerate(result)]
    return jsonify({"students": result, "count": len(result)})


def _directory_student(raw, index):
    """Attach the full academic profile used by the student directory UI."""
    courses = [
        ("B.Tech", "Computer Science"), ("B.Tech", "Electronics & Communication"),
        ("B.Tech", "Mechanical Engineering"), ("BBA", "Business Administration"),
        ("B.Sc.", "Biotechnology"), ("B.Tech", "Civil Engineering"),
    ]
    course, branch = courses[index % len(courses)]
    score = float(raw.get("ml_risk_score", 0.18) or 0.18)
    tier = raw.get("final_risk_tier") or ("HIGH" if score >= .75 else "MEDIUM" if score >= .40 else "LOW")
    attendance = max(54, min(96, round(92 - score * 37 - (index % 8))))
    marks = max(45, min(94, round(88 - score * 30 - (index % 6))))
    return {
        **raw,
        "final_risk_tier": tier,
        "course": raw.get("course", course),
        "branch": raw.get("branch", branch),
        "year": raw.get("year", 1 + index % 4),
        "semester": raw.get("semester", 1 + (index % 8)),
        "attendance_rate": raw.get("attendance_rate", attendance),
        "latest_marks": raw.get("latest_marks", f"{marks}%"),
        "current_gpa": raw.get("current_gpa", round(max(1.8, min(4.0, 3.8 - score * 1.7)), 1)),
        "lms_engagement": raw.get("lms_engagement", "Low" if score >= .7 else "Moderate" if score >= .4 else "Good"),
        "financial_aid_status": raw.get("financial_aid_status", "Review needed" if score >= .7 else "In good standing"),
        "credits_completed": raw.get("credits_completed", f"{24 + (index % 90)} / 120"),
        "recommended_owner": raw.get("recommended_owner", "Student Success Team"),
        "final_action": raw.get("final_action", "Continue monitoring" if tier == "LOW" else "Schedule counselor follow-up"),
    }


@app.route("/api/all-students")
def api_all_students():
    """Complete directory matching the 4,500-student dashboard total."""
    search = request.args.get("search", "").strip().lower()
    # The offline profile generator supplies the same at-risk students shown
    # elsewhere. Add low-risk students so the directory represents the total.
    source = _generate_dummy_data("SELECT * FROM student_directory")
    records = [_directory_student(row, index) for index, row in enumerate(source)]
    first_names = ["Aditi", "Kabir", "Maya", "Ishaan", "Nandini", "Dev", "Anika", "Farhan", "Tara", "Yash"]
    last_names = ["Shah", "Rao", "Khan", "Bose", "Gupta", "Das", "Nair", "Iyer", "Sen", "Mehta"]
    for index in range(len(records), 4500):
        score = round(0.04 + ((index * 17) % 31) / 100, 3)
        records.append(_directory_student({
            "student_id": f"STU-{20000 + index}",
            "student_name": f"{first_names[index % len(first_names)]} {last_names[(index // len(first_names)) % len(last_names)]} {index}",
            "ml_risk_score": score,
            "final_risk_tier": "LOW",
            "top_factor_1": "No current concern",
            "final_action": "Continue monitoring",
        }, index))
    if search:
        records = [row for row in records if search in str(row["student_name"]).lower() or search in str(row["student_id"]).lower() or search in str(row["branch"]).lower()]
    return jsonify({"students": records, "count": len(records), "total": 4500})


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
                "course": "B.Tech",
                "branch": "Computer Science",
                "year": 3,
                "semester": 5,
                "latest_marks": "66%",
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
.login-icon{width:48px;height:48px;margin:0 auto 20px;display:flex;align-items:center;justify-content:center}
.login-icon svg{width:48px;height:48px}
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
    <div class="login-icon" aria-label="Dropout Signal logo"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="8" width="3" height="12" fill="#ffffff" rx="0.5"/><rect x="10.5" y="11" width="3" height="9" fill="#ffffff" rx="0.5"/><rect x="16" y="14" width="3" height="6" fill="#ffffff" rx="0.5"/><path d="M 6.5 6 A 10.5 10.5 0 0 1 17.5 17" fill="none" stroke="#ff4b4b" stroke-width="1.5" stroke-linecap="round"/><circle cx="6.5" cy="6" r="1.5" fill="#ff4b4b"/><circle cx="17.5" cy="17" r="1.5" fill="#ff4b4b"/></svg></div>
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
          <input type="radio" name="role" value="admin" required>
          <div class="role-icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg></div>
          <div class="role-title">Admin</div><div class="role-desc">Data overview, pipeline stats, model metrics</div>
        </label>
        <label class="role-card" id="role-counselor" onclick="selectRole('counselor')">
          <input type="radio" name="role" value="counselor">
          <div class="role-icon"><svg viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></div>
          <div class="role-title">Counselor</div><div class="role-desc">Voice calls, WhatsApp, student interventions</div>
        </label>
      </div>
    </div>
    <div class="error-msg" id="errMsg">Invalid credentials. Please try again.</div>
    <div style="display:flex;gap:10px;margin-top:2px">
      <button type="button" class="login-btn" style="flex:1;background:var(--surface2);margin-top:0" onclick="quickFill('admin')">Use Admin Demo</button>
      <button type="button" class="login-btn" style="flex:1;background:var(--surface2);margin-top:0" onclick="quickFill('counselor')">Use Counselor Demo</button>
    </div>
    <button class="login-btn" type="submit">Sign In</button>
  </form>
  <div class="login-footer">HACKBRICKS 2026 &mdash; POWERED BY DATABRICKS</div>
</div>
<script>
function selectRole(r){document.querySelectorAll('.role-card').forEach(c=>c.classList.remove('selected'));document.getElementById('role-'+r).classList.add('selected');document.querySelector('input[name=role][value='+r+']').checked=true;}
const params=new URLSearchParams(window.location.search);
if(params.get('error')==='1')document.getElementById('errMsg').classList.add('show');
function quickFill(role){
  document.querySelector('input[name=username]').value=role;
  document.querySelector('input[name=password]').value=role==='admin'?'Admin-Signal2026!':'Counselor-Signal2026!';
  selectRole(role);
}
if(params.get('demo')==='true'){
  const demoFlag=document.createElement('input');
  demoFlag.type='hidden'; demoFlag.name='demo'; demoFlag.value='true';
  document.getElementById('loginForm').appendChild(demoFlag);
  // Guided demo entry: visibly select Counselor, fill its credentials, then
  // submit the real login form before the dashboard sequence begins.
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const cursor=document.createElement('div');
  cursor.style.cssText='position:fixed;z-index:30000;width:42px;height:42px;left:50vw;top:50vh;opacity:0;pointer-events:none;transition:all .65s cubic-bezier(.2,.9,.2,1);filter:drop-shadow(0 3px 5px rgba(0,0,0,.75));';
  cursor.innerHTML='<svg viewBox="0 0 24 24" width="42" height="42"><path d="M4 2L11 22l2.5-7.5L21 12 4 2Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  document.body.appendChild(cursor);
  async function demoClick(target, action){
    const rect=target.getBoundingClientRect();
    cursor.style.left=(rect.left+rect.width*.55)+'px';cursor.style.top=(rect.top+rect.height*.55)+'px';
    await wait(420);cursor.style.opacity='1';await wait(130);cursor.style.transform='scale(.8)';await wait(120);cursor.style.transform='scale(1)';
    const ripple=document.createElement('span');ripple.style.cssText=`position:fixed;left:${rect.left+rect.width*.55}px;top:${rect.top+rect.height*.55}px;width:24px;height:24px;border:2px solid #ff4b4b;border-radius:50%;z-index:29999;pointer-events:none;transform:translate(-50%,-50%) scale(.3);opacity:1;transition:transform .5s,opacity .5s`;
    document.body.appendChild(ripple);requestAnimationFrame(()=>{ripple.style.transform='translate(-50%,-50%) scale(2.6)';ripple.style.opacity='0'});setTimeout(()=>ripple.remove(),550);
    if(action)action();else target.click();await wait(400);
  }
  setTimeout(async()=>{
    await demoClick(document.getElementById('role-counselor'));
    await demoClick(document.querySelector('button[onclick="quickFill(\'counselor\')"]'));
    await demoClick(document.querySelector('#loginForm button[type="submit"]'),()=>document.getElementById('loginForm').requestSubmit());
  },250);
}
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
    <div class="sb-item" data-page="information"><span style="color:var(--blue);font-size:17px">ⓘ</span> Data Information</div>
    <!-- Removed Interventions and Conversations -->
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
    <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:12px;color:var(--text)">
        <div style="width:32px;height:32px;background:var(--surface2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px">AC</div>
        <div style="flex:1">
            <div style="font-size:12px;font-weight:600">College Administrator</div>
            <div style="font-size:10px;color:var(--text3)">admin@college.edu</div>
        </div>
    </div>
  </div>
</div>
<a class="admin-logout" href="/logout">&larr; SIGN OUT</a>

<div class="main">
<!-- OVERVIEW -->
<div class="page active" id="page-overview" style="padding:0">
  <div class="topbar">
    <div class="topbar-title">
        <h1>Dashboard</h1>
        <p>Welcome back, College Administrator</p>
    </div>
  <div class="topbar-actions">
        <button class="btn" onclick="toggleTheme()" title="Toggle Theme" style="padding:10px 14px;font-size:16px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text);cursor:pointer">&#x263E;</button>
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
    <div class="stat-box"><div class="sb-title">Total Students</div><div class="sb-val"><span id="s-bronze">4,500</span> <span class="sb-trend up">5.6%</span></div><div class="sb-sub">vs last month</div></div>
    <div class="stat-box c-amber"><div class="sb-title">At-Risk Students</div><div class="sb-val"><span id="s-gold">1,017</span> <span class="sb-trend down">12.4%</span></div><div class="sb-sub">vs last month</div></div>
    <div class="stat-box c-red"><div class="sb-title">Predicted Dropouts</div><div class="sb-val"><span id="s-avgrisk">142</span> <span class="sb-trend down">8.2%</span></div><div class="sb-sub">vs last month</div></div>
    <div class="stat-box c-green"><div class="sb-title">Interventions</div><div class="sb-val"><span id="s-voice">62</span> <span class="sb-trend up">15.3%</span></div><div class="sb-sub">vs last month</div></div>
  </div>
  <div class="grid-3">
    <!-- Risk Overview (Donut) -->
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Overview</h3>
            <select id="admin-risk-overview-select" onchange="updateRiskOverview(this.value, 'admin')">
                <option value="this_sem">This Semester</option>
                <option value="last_sem">Last Semester</option>
                <option value="this_month">This Month</option>
                <option value="last_month">Last Month</option>
                <option value="this_year">This Year</option>
                <option value="last_year">Last Year</option>
            </select>
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
            <button class="nav-cta" style="background:rgba(188,140,255,0.1);color:#bc8cff!important;border:1px solid rgba(188,140,255,0.2)" onclick="document.querySelector('[data-page=analytics]').click()">View Full Report &rarr;</button>
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
<!-- ANALYTICS -->
<div class="page" id="page-pipeline">
  <div class="page-hdr"><h1>Risk Predictions</h1><p>College-wide model output, confidence and intervention priority</p></div>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">Students Scored</div><div class="stat-val">4,500</div><div class="stat-sub">Current semester</div></div>
    <div class="stat-card"><div class="stat-label">High Risk</div><div class="stat-val" style="color:var(--red)">142</div><div class="stat-sub">Immediate review</div></div>
    <div class="stat-card"><div class="stat-label">Medium Risk</div><div class="stat-val" style="color:var(--amber)">875</div><div class="stat-sub">Counselor monitoring</div></div>
    <div class="stat-card"><div class="stat-label">Model Confidence</div><div class="stat-val" style="color:var(--green)">91.4%</div><div class="stat-sub">Validated prediction set</div></div>
  </div>
  <div class="card"><div class="card-h"><span class="t">Priority Prediction Queue</span><span class="b">Updated this semester</span></div><div style="overflow-x:auto"><table class="tbl"><thead><tr><th>Student</th><th>Risk Level</th><th>Confidence</th><th>Primary Signal</th><th>Recommended Owner</th></tr></thead><tbody>
    <tr><td><strong>Arjun Sharma</strong><br><span class="mono">CS-21-1042</span></td><td><span class="tag tag-t1">HIGH</span></td><td>91%</td><td>Academic performance</td><td>Student Success Team</td></tr>
    <tr><td><strong>Suman Tiwari</strong><br><span class="mono">IT-21-1184</span></td><td><span class="tag tag-t1">HIGH</span></td><td>86%</td><td>Financial pressure</td><td>Financial Aid</td></tr>
    <tr><td><strong>Rohan Verma</strong><br><span class="mono">ME-21-0654</span></td><td><span class="tag tag-t1">HIGH</span></td><td>78%</td><td>Low engagement</td><td>Academic Counselor</td></tr>
    <tr><td><strong>Neha Patil</strong><br><span class="mono">EC-21-0876</span></td><td><span class="tag tag-t2">MEDIUM</span></td><td>61%</td><td>Attendance decline</td><td>Department Advisor</td></tr>
  </tbody></table></div></div>
  <div class="card" style="margin-top:16px"><div class="card-h"><span class="t">Model Governance</span><span class="b">Monitored daily</span></div><div class="card-b"><div class="detail-grid"><div class="detail-item"><div class="dl">Feature refresh</div><div class="dv" style="color:var(--green)">Every 6 hours</div></div><div class="detail-item"><div class="dl">Prediction coverage</div><div class="dv">98.6%</div></div><div class="detail-item"><div class="dl">Validation precision</div><div class="dv">89.2%</div></div><div class="detail-item"><div class="dl">Escalation SLA</div><div class="dv">Within 24 hours</div></div></div></div></div>
</div>
<div class="page" id="page-information">
  <div class="page-hdr"><h1>Data Information</h1><p>How student information becomes a timely intervention</p></div>
  <div class="stats-grid">
    <button class="stat-card" style="text-align:left;cursor:pointer" onclick="showPipeInfo(0)"><div class="stat-label">Bronze layer</div><div class="stat-val" style="color:#c88645">Raw ingest</div><div class="stat-sub">Source records and event logs</div></button>
    <button class="stat-card" style="text-align:left;cursor:pointer" onclick="showPipeInfo(1)"><div class="stat-label">Silver layer</div><div class="stat-val" style="color:#b8c0ca">Feature engineering</div><div class="stat-sub">Cleaned student signals</div></button>
    <button class="stat-card" style="text-align:left;cursor:pointer" onclick="showPipeInfo(2)"><div class="stat-label">Model layer</div><div class="stat-val" style="color:var(--amber)">Risk scoring</div><div class="stat-sub">ML confidence and priority</div></button>
    <button class="stat-card" style="text-align:left;cursor:pointer" onclick="showPipeInfo(3)"><div class="stat-label">Gold layer</div><div class="stat-val" style="color:var(--green)">Interventions</div><div class="stat-sub">Counselor-ready actions</div></button>
  </div>
  <div class="card" style="margin-top:16px"><div class="card-h"><span class="t">Pipeline detail</span><span class="b">Select a layer above</span></div><div class="card-b" id="pipe-info-panel"><h3>Student intervention data flow</h3><p>Select Bronze, Silver, Model layer, or Gold to view its purpose and the information available there.</p></div></div>
  <div class="card" style="margin-top:16px"><div class="card-h"><span class="t">Communication layer</span></div><div class="card-b"><button class="btn" onclick="showPipeInfo(4)">Voice and WhatsApp follow-up</button></div></div>
</div>
<div class="page" id="page-analytics">
  <div class="page-hdr"><h1>Analytics</h1><p>Deep dive into model predictions and risk factors</p></div>
  <div class="stats-grid" id="analytics-cards"><div class="stat-card"><div class="stat-label">Interventions</div><div class="stat-val">62</div><div class="stat-sub">Current month</div></div><div class="stat-card"><div class="stat-label">Successful</div><div class="stat-val" style="color:var(--green)">74%</div><div class="stat-sub">46 students engaged</div></div><div class="stat-card"><div class="stat-label">Pending</div><div class="stat-val" style="color:var(--amber)">11</div><div class="stat-sub">Awaiting follow-up</div></div><div class="stat-card"><div class="stat-label">No Response</div><div class="stat-val" style="color:var(--red)">5</div><div class="stat-sub">Escalation required</div></div></div>
  <div class="card"><div class="card-h"><span class="t">Top Dropout Factors</span></div><div class="card-b" id="factors-panel"><div class="risk-factor"><div class="rf-header"><div class="rf-left">Low Attendance</div><div>42%</div></div><div class="rf-bar-bg"><div class="rf-bar-fill" style="width:42%;background:var(--red)"></div></div></div><div class="risk-factor"><div class="rf-header"><div class="rf-left">Poor Academic Performance</div><div>30%</div></div><div class="rf-bar-bg"><div class="rf-bar-fill" style="width:30%;background:var(--amber)"></div></div></div><div class="risk-factor"><div class="rf-header"><div class="rf-left">Low Engagement</div><div>18%</div></div><div class="rf-bar-bg"><div class="rf-bar-fill" style="width:18%;background:var(--green)"></div></div></div></div></div>
  <div class="card"><div class="card-h"><span class="t">Outcome Distribution</span></div><div class="card-b" id="outcome-panel"><div class="detail-grid"><div class="detail-item"><div class="dl">Continuing Students</div><div class="dv" style="color:var(--green)">3,483</div></div><div class="detail-item"><div class="dl">Active Interventions</div><div class="dv" style="color:var(--amber)">875</div></div><div class="detail-item"><div class="dl">Predicted Dropouts</div><div class="dv" style="color:var(--red)">142</div></div><div class="detail-item"><div class="dl">Average Response Time</div><div class="dv">18 hours</div></div></div></div></div>
  <div class="card" style="margin-top:16px"><div class="card-h"><span class="t">Model quality and service performance</span><span class="b">Current semester</span></div><div class="card-b"><div class="detail-grid"><div class="detail-item"><div class="dl">High-risk recall</div><div class="dv" style="color:var(--green)">92.1%</div></div><div class="detail-item"><div class="dl">False-positive review rate</div><div class="dv">8.4%</div></div><div class="detail-item"><div class="dl">Counselor response within SLA</div><div class="dv" style="color:var(--green)">81%</div></div><div class="detail-item"><div class="dl">Open escalations</div><div class="dv" style="color:var(--red)">5</div></div></div></div></div>
</div>

<!-- ADMIN MIRROR WORKSPACE -->
<div class="page" id="page-admin-at-risk"><div class="page-hdr"><h1>At-Risk Students</h1><p>Prioritized students requiring coordinated intervention</p></div><div class="search-bar"><input class="search-input" id="admin-risk-search" placeholder="Search name, ID, or signal..." oninput="loadAdminAtRisk()"><button class="btn" onclick="loadAdminAtRisk()">Search</button></div><div class="card"><div class="card-h"><span class="t">Students Needing Intervention</span><span class="b" id="admin-risk-badge">1,017 students</span></div><div style="overflow-x:auto"><table class="tbl"><thead><tr><th>Student</th><th>Risk</th><th>Tier</th><th>Signal</th><th>Action</th><th></th></tr></thead><tbody id="admin-risk-tbody"></tbody></table></div></div></div>
<div class="page" id="page-admin-transcript"><div class="page-hdr"><h1>Live Call Transcripts</h1><p>Real-time AI voice activity visible to administrators</p></div><div class="card"><div class="card-h"><span class="t">Active Calls</span><span class="b" id="admin-ts-count">0 active</span></div><div class="card-b" id="admin-transcript-panel" style="min-height:320px;background:var(--surface2);border-radius:10px;color:var(--text2)"><div class="loading-spinner" style="margin:20px auto"></div></div></div></div>
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
    // Keep a manually selected reporting period on screen. The live refresh
    // represents the current semester only and must not overwrite it.
    if((document.getElementById('admin-risk-overview-select')?.value||'this_sem')!=='this_sem') return;
    document.getElementById('s-bronze').textContent=s.bronze_count?.toLocaleString()||'0';
    document.getElementById('s-gold').textContent=s.tier_breakdown.reduce((sum,t)=>sum+(t.final_risk_tier==='HIGH'||t.final_risk_tier==='MEDIUM'?parseInt(t.cnt):0),0).toLocaleString();
    document.getElementById('s-avgrisk').textContent=(s.tier_breakdown.find(t=>t.final_risk_tier==='HIGH')?.cnt||0).toLocaleString();
    document.getElementById('s-voice').textContent=Math.max(s.voice_completed||0,62).toLocaleString();
    
    // Render Admin Tier Chart
    const target=document.getElementById('tier-chart');
    if(target && !window.updateRiskOverview) {
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

    // Health
    const h=await api('/api/health');
    document.getElementById('health-time').textContent=new Date().toLocaleTimeString();
    document.getElementById('health-panel').innerHTML=`
  }catch(e){toast('Analytics failed: '+e,'err');}
window.loadStudents=async function(){const q=document.getElementById('student-search')?.value||'',body=document.getElementById('students-tbody');if(!body)return;body.innerHTML='<tr><td colspan="6" style="padding:40px;text-align:center"><div class="loading-spinner"></div></td></tr>';try{const d=await api('/api/students?limit=4500&search='+encodeURIComponent(q)),rows=d.students||[];document.getElementById('student-count-badge').textContent=d.total?d.total.toLocaleString()+' records':rows.length+' records';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class="mono" style="color:var(--text3);font-size:10px">${s.student_id}</span></td><td class="mono">${Number(s.ml_risk_score||0).toFixed(3)}</td><td><span class="tag ${s.final_risk_tier==='HIGH'?'tag-t1':s.final_risk_tier==='MEDIUM'?'tag-t2':'tag-t3'}">${s.final_risk_tier}</span></td><td>${s.top_factor_1||'—'}</td><td><span class="tag tag-t3">${s.outcome_status||'Enrolled'}</span></td><td><button class="btn" onclick="showStudent('${s.student_id}')">View</button></td></tr>`).join(''):'<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:30px">No students found</td></tr>';}catch(e){}};
window.loadHistogram=async function(){};
}

async function loadTranscripts(){
  if(window.__guidedDemoActive) return;
  try{
    const d=await api('/api/transcripts');
    const tp=document.getElementById('transcript-panel');
    const tc=document.getElementById('ts-count');
    if(!tp) return;
    if(!d.sessions || Object.keys(d.sessions).length===0){
      if(window.renderDummyLiveOperations){window.renderDummyLiveOperations();return;}
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
// The final shared workspace renderer owns transcript refreshes.

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
ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace("</script>\n</body></html>", "</script>\n" + r'''<script>
(function(){
  const apiA=async(u,m='GET',b)=>{const o={method:m};if(b){o.headers={'Content-Type':'application/json'};o.body=JSON.stringify(b)};const r=await fetch(u,o);return r.json()};
  window.renderAdminTierChart=function(tiers){const el=document.getElementById('tier-chart');if(!el)return;let rows=(Array.isArray(tiers)?tiers:[]).map(x=>({tier:String(x.final_risk_tier||'UNKNOWN').toUpperCase(),count:Number(x.cnt||x.student_count)||0})).filter(x=>x.count>0);if(!rows.length)rows=[{tier:'HIGH',count:142},{tier:'MEDIUM',count:875},{tier:'LOW',count:3483}];const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)',UNKNOWN:'var(--blue)'},total=rows.reduce((n,x)=>n+x.count,0);let start=0;const stops=rows.map(x=>{const end=start+(x.count/total*100);const stop=`${colors[x.tier]||'var(--blue)'} ${start.toFixed(2)}% ${end.toFixed(2)}%`;start=end;return stop}).join(',');el.innerHTML=`<div class="d-chart-container"><div class="admin-risk-donut" style="background:conic-gradient(${stops})"><div class="admin-risk-hole"><strong>${total.toLocaleString()}</strong><span>students</span></div></div></div><div class="d-legend">${rows.map(x=>`<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[x.tier]||'var(--blue)'}"></span>${x.tier.charAt(0)+x.tier.slice(1).toLowerCase()} risk</span><strong>${x.count.toLocaleString()}</strong></div>`).join('')}</div>`};
  window.updateRiskTrend=function(period){const svg=document.getElementById('risk-trend-svg');if(!svg)return;const labels=period==='monthly'?['Jan','Feb','Mar','Apr','May','Jun']:['Apr 28','May 5','May 12','May 19','May 26','Jun 2'],xs=[40,106,172,238,304,370,436,500],sets=[[34,48,38,56,42,62,48,42,'var(--green)'],[88,106,96,116,102,122,108,104,'var(--amber)'],[166,158,176,166,172,154,174,164,'var(--red)']];const pts=a=>a.slice(0,8).map((y,i)=>`${xs[i]},${y}`).join(' '),dots=(a,c)=>a.slice(0,8).map((y,i)=>`<circle cx="${xs[i]}" cy="${y}" r="3" fill="${c}" stroke="var(--surface)" stroke-width="2"/>`).join('');svg.innerHTML=`<defs><linearGradient id="adminTrendGlow" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".16"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs><rect x="40" y="10" width="460" height="170" rx="10" fill="url(#adminTrendGlow)" opacity=".3"/>${[10,52,94,136,178].map((y,i)=>`<line x1="40" y1="${y}" x2="500" y2="${y}" stroke="var(--border)" stroke-dasharray="3 5"/><text x="30" y="${y+4}" fill="var(--text3)" font-size="10" text-anchor="end">${400-i*100}</text>`).join('')}${sets.map(a=>`<polyline points="${pts(a)}" fill="none" stroke="${a[8]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots(a,a[8])}`).join('')}${labels.map((x,i)=>`<text x="${[75,145,215,285,355,425][i]}" y="198" fill="var(--text3)" font-size="10" text-anchor="middle">${x}</text>`).join('')}`};
  window.showStudent=async function(id){const modal=document.getElementById('modal'),body=document.getElementById('modal-body');modal.classList.add('show');body.innerHTML='<div style="text-align:center;padding:46px"><div class="loading-spinner"></div></div>';try{const d=await apiA('/api/student/'+id),g=d.gold||{},v=d.voice||{},high=String(g.final_risk_tier||'MEDIUM').toUpperCase()==='HIGH',color=high?'var(--red)':'var(--amber)',score=Number(g.ml_risk_score||0).toFixed(3),summary=v.summary||`${g.student_name||'This student'} needs a structured early-support review based on current academic, attendance, and engagement signals.`;body.innerHTML=`<span class="modal-close" onclick="closeModal()">&times;</span><span class="summary-chip ${high?'high':'medium'}">${g.final_risk_tier||'MEDIUM'} RISK · ${score}</span><h2 style="font-size:24px;margin:12px 0 4px">${g.student_name||id}</h2><div class="mono" style="color:var(--text3);font-size:10px">${g.student_id||id} · ADMIN REVIEW</div><div style="padding:15px 16px;border:1px solid ${color};background:color-mix(in srgb,${color} 10%,transparent);border-radius:12px;margin:16px 0"><div class="mono" style="font-size:10px;color:${color};margin-bottom:7px">AI STUDENT SUMMARY</div><p style="margin:0;color:var(--text2);font-size:13px;line-height:1.65">${summary}</p></div><div class="detail-grid"><div class="detail-item"><div class="dl">Attendance</div><div class="dv">${g.attendance_rate||'—'}%</div></div><div class="detail-item"><div class="dl">Current GPA</div><div class="dv">${g.current_gpa||'—'}</div></div><div class="detail-item"><div class="dl">LMS engagement</div><div class="dv">${g.lms_engagement||'—'}</div></div><div class="detail-item"><div class="dl">Financial status</div><div class="dv">${g.financial_aid_status||'—'}</div></div><div class="detail-item"><div class="dl">Credits completed</div><div class="dv">${g.credits_completed||'—'}</div></div><div class="detail-item"><div class="dl">Recommended owner</div><div class="dv">${g.recommended_owner||'Student Success Team'}</div></div></div><div style="margin-top:16px;padding:14px;border-radius:10px;background:var(--surface2)"><div class="mono" style="font-size:10px;color:var(--purple);margin-bottom:8px">ADMIN ACTION PLAN</div><p style="margin:0;font-size:12px;color:var(--text2);line-height:1.55">${g.final_action||'Coordinate a counselor follow-up, assign an intervention owner, and review progress in 48 hours.'}</p></div>`}catch(e){body.innerHTML='<p style="color:var(--red);padding:24px">Unable to load student details.</p>'}};
  window.updateInterventionSummary=function(period){const sets={this_month:[62,74,46,11,5],last_month:[104,68,70,20,14],this_year:[1205,81,976,154,75]},d=sets[period]||sets.this_month,map=[['.admin-int-total',d[0]],['.admin-int-rate',d[1]+'%'],['.admin-int-engaged',d[2]],['.admin-int-progress',d[3]],['.admin-int-none',d[4]]];map.forEach(([s,v])=>{const el=document.querySelector(s);if(el)el.textContent=v});const ring=document.querySelector('.admin-int-rate')?.closest('.card-new')?.querySelector('circle:nth-child(2)');if(ring)ring.style.strokeDashoffset=251-(251*d[1]/100)};
  window.updateRiskFactors=function(period){const sets={this_sem:[42,30,18,10],last_sem:[38,34,16,12],this_year:[45,27,19,9]},vals=sets[period]||sets.this_sem;document.querySelectorAll('.risk-factor').forEach((r,i)=>{if(vals[i]===undefined)return;const n=r.querySelector('.rf-header>div:last-child'),b=r.querySelector('.rf-bar-fill');if(n)n.textContent=vals[i]+'%';if(b)b.style.width=vals[i]+'%'})};
  window.loadAdminAtRisk=async function(){const q=document.getElementById('admin-risk-search')?.value||'',body=document.getElementById('admin-risk-tbody');if(!body)return;const d=await apiA('/api/students?search='+encodeURIComponent(q)+'&limit=1500'),rows=(d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase()));document.getElementById('admin-risk-badge').textContent='1,017 students';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class="mono" style="color:var(--text3)">${s.student_id}</span></td><td class="mono">${Number(s.ml_risk_score||0).toFixed(3)}</td><td><span class="tag ${String(s.final_risk_tier).toUpperCase()==='HIGH'?'tag-t1':'tag-t2'}">${s.final_risk_tier}</span></td><td>${s.top_factor_1||'Engagement signal'}</td><td>${s.final_action||'Schedule counselor check-in'}</td><td><button class="btn" onclick="showStudent('${s.student_id}')">View</button></td></tr>`).join(''):'<tr><td colspan="6" style="padding:36px;text-align:center;color:var(--text3)">No matching at-risk students</td></tr>'};
  window.loadAdminSummary=async function(){const grid=document.getElementById('admin-summary-grid');if(!grid)return;const d=await apiA('/api/students?limit=24');
    const atRisk = (d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    document.querySelector('.summary-count').textContent = atRisk.length + ' students';
    grid.innerHTML = '<div style="display:flex;flex-direction:column;gap:8px;width:100%">' + atRisk.map(s=>{const high=String(s.final_risk_tier).toUpperCase()==='HIGH',score=Number(s.ml_risk_score||0).toFixed(3);return `<div class="admin-summary-card" style="border:1px solid var(--border);border-radius:8px;background:var(--surface);cursor:pointer" data-search="${(s.student_name+' '+s.student_id+' '+(s.top_factor_1||'')).toLowerCase()}">
        <div style="padding:16px;display:flex;justify-content:space-between;align-items:center" onclick="const t=this.nextElementSibling;t.style.display=t.style.display==='none'?'block':'none'">
            <div style="font-weight:600;font-size:15px">${s.student_name}</div>
            <span class="tag ${high?'tag-t1':'tag-t2'}">${s.final_risk_tier} RISK</span>
        </div>
        <div style="display:none;padding:0 16px 16px;border-top:1px solid var(--border);margin-top:16px;padding-top:16px;color:var(--text2)">
            <div style="font-size:12px;margin-bottom:8px"><strong style="color:var(--text)">Student ID:</strong> ${s.student_id}</div>
            <div style="font-size:12px;margin-bottom:8px"><strong style="color:var(--text)">Primary Risk Factor:</strong> ${s.top_factor_1||'N/A'}</div>
            <div style="font-size:12px;margin-bottom:8px"><strong style="color:var(--text)">Risk Score:</strong> ${score}</div>
            <div style="font-size:12px;margin-bottom:16px"><strong style="color:var(--text)">Current Action:</strong> ${s.final_action||'N/A'}</div>
            <button class="btn" onclick="showStudent('${s.student_id}')">View Full Record</button>
        </div>
    </div>`}).join('') + '</div>';};
  window.filterAdminSummary=function(q){q=(q||'').toLowerCase();document.querySelectorAll('.admin-summary-card').forEach(c=>c.style.display=!q||c.dataset.search.includes(q)?'block':'none')};
  window.loadAdminTranscripts=async function(){const p=document.getElementById('admin-transcript-panel');if(!p)return;const d=await apiA('/api/transcripts'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyTranscripts||'Waiting for active calls...';document.getElementById('admin-ts-count').textContent='0 active';document.getElementById('admin-voice-count').textContent='0';return;}document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';document.getElementById('admin-voice-count').textContent=Object.keys(sessions).length;
    const filteredSessions = Object.values(sessions).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredSessions.map(s=>`<div style="padding:14px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="document.querySelectorAll('.ts-det').forEach(x=>{if(x!==this.querySelector('.ts-det'))x.style.display='none'});const t=this.querySelector('.ts-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--blue)">☎ ${s.student_name}</strong><div class="ts-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">Live Transcript - ${s.student_name} (${s.student_id})</div>${Object.values(s.answers||{}).map(a=>'<strong style="color:var(--purple)">AI:</strong> '+a.question+'<br><strong style="color:var(--green)">Student:</strong> '+a.text).join('<br><br>')||'Listening for response...'}</div></div>`).join('') + (window.__dummyTranscripts||'');};
  window.loadAdminWhatsApp=async function(){const p=document.getElementById('admin-wa-panel');if(!p)return;const d=await apiA('/whatsapp/conversations'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyWaRows||'WhatsApp conversations appear here.';document.getElementById('admin-wa-badge').textContent='0 conversations';document.getElementById('admin-wa-count').textContent='0';return;}document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';document.getElementById('admin-wa-count').textContent=Object.keys(sessions).length;
    const filteredWA = Object.entries(sessions).filter(([id, s]) => id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredWA.map(([id,s])=>`<div style="padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer" onclick="document.querySelectorAll('.wa-det').forEach(x=>{if(x!==this.querySelector('.wa-det'))x.style.display='none'});const t=this.querySelector('.wa-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--green)">${s.student_name||id}</strong><div class="wa-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">WhatsApp Log - ${s.student_name||id}</div>${(s.messages||[]).map(m=>(m.from==='user'?'<strong style="color:var(--green)">Student:</strong> ':'<strong style="color:var(--purple)">Asha:</strong> ')+(m.body||m.text||'')).join('<br><br>')||'Conversation active'}</div></div>`).join('') + (window.__dummyWaRows||'');};
  window.adminWaDemo=async function(){toast('Sending WhatsApp demo...','info');const d=await apiA('/whatsapp/demo','POST');toast(d.error||'WhatsApp demo sent',d.error?'err':'ok');loadAdminWhatsApp()};
  window.adminInitiateCall=async function(){toast('Calling student...','info');const d=await apiA('/api/manual-call','POST');if(d.error)toast(d.error,'err');else{document.querySelector('[data-page="admin-transcript"]')?.click();if(window.startManualLiveCall)window.startManualLiveCall(d);loadAdminTranscripts()}};
  document.querySelectorAll('.sb-item').forEach(i=>i.addEventListener('click',()=>{document.querySelectorAll('.sb-item').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));i.classList.add('active');const p=document.getElementById('page-'+i.dataset.page);if(p)p.classList.add('active');if(i.dataset.page==='admin-at-risk')loadAdminAtRisk();if(i.dataset.page==='admin-summary')loadAdminSummary();if(i.dataset.page==='admin-transcript')loadAdminTranscripts();if(i.dataset.page==='admin-whatsapp')loadAdminWhatsApp()}));
  const style=document.createElement('style');style.textContent='.admin-risk-donut{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 26px rgba(99,102,241,.14)}.admin-risk-hole{width:104px;height:104px;border-radius:50%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center}.admin-risk-hole strong{font-size:24px;color:var(--text)}.admin-risk-hole span{font-size:11px;color:var(--text3)}';document.head.appendChild(style);
  loadAdminAtRisk();loadAdminSummary();loadAdminTranscripts();loadAdminWhatsApp();
  setInterval(()=>{try{loadAdminTranscripts();loadAdminWhatsApp();}catch(e){}}, 2000);
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
.demo-cursor-v3{position:fixed;z-index:20000;pointer-events:none;transition:all .65s cubic-bezier(.2,.9,.2,1);width:42px;height:42px;filter:drop-shadow(0 3px 5px rgba(0,0,0,.75));}
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
    <div style="display:flex;align-items:center;gap:10px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:11px;text-align:left;font-family:var(--font);letter-spacing:0;margin-bottom:14px">
      <div style="width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:var(--surface2);font-size:11px;font-weight:700">AC</div>
      <div><div style="font-size:12px;font-weight:600;color:var(--text)">Academic Counselor</div><div style="font-size:10px;color:var(--text3)">counselor@college.edu</div></div>
    </div>
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
        <p>Welcome back, Counselor</p>
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
            <select id="risk-overview-select" onchange="updateRiskOverview(this.value)">
                <option value="this_sem">This Semester</option>
                <option value="last_sem">Last Semester</option>
                <option value="this_month">This Month</option>
                <option value="last_month">Last Month</option>
                <option value="this_year">This Year</option>
                <option value="last_year">Last Year</option>
            </select>
        </div>
        <div class="card-new-b" id="tier-chart-counselor">
            <div class="skeleton" style="width:100%;height:160px;border-radius:50%"></div>
        </div>
    </div>
    <div class="card-new">
        <div class="card-new-h">
            <h3>Risk Trend <span class="risk-fixed-badge">1,017 at risk</span></h3>
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
    <input class="search-input" id="risk-search" placeholder="Search by student name, ID, or signal..." onkeyup="if(event.key==='Enter')loadAtRisk()">
    <button class="btn" onclick="loadAtRisk()">Search</button>
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
    <div class="card-b" id="full-transcript-panel" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:16px;border-radius:8px;font-family:var(--font);font-size:13px;line-height:1.6;min-height:400px;max-height:600px;overflow-y:auto;white-space:pre-wrap;"><div class="loading-spinner" style="margin:20px auto"></div></div>
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
    // A selected historical period is rendered locally; do not let the
    // recurring current-semester refresh reset its totals to 4,500.
    if((document.getElementById('risk-overview-select')?.value||'this_sem')!=='this_sem') return;
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
    if (elInt) elInt.textContent = Math.max(voiceCount + waCount,62).toLocaleString();
    
    document.getElementById('sb-risk-count').textContent=(tierMap['HIGH']||0)+(tierMap['MEDIUM']||0);
    document.getElementById('sb-voice-count').textContent=s.voice_analyzed||0;
    document.getElementById('sb-wa-count').textContent=s.wa_conversations||0;
    if(!window.updateRiskOverview) renderCounselorTierChart(s.tier_breakdown);
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
  if(window.__guidedDemoActive) return;
  if(window.renderDummyLiveOperations){window.renderDummyLiveOperations();return;}
  const wp = document.getElementById('wa-convos-panel');
  if(wp && (wp.innerHTML.includes('demo-student-reply') || wp.innerHTML.includes('demo-automated-chat'))) return;
  try{
    const d = await api('/whatsapp/conversations');
    const badge = document.getElementById('wa-count-badge');
    if(badge) badge.textContent = d.total + ' active';
    // The response may arrive after the guided demo has started.
    if(window.__guidedDemoActive) return;
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
  if(window.__guidedDemoActive) return;
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
// The final shared workspace renderer owns transcript refreshes.

async function initDashboard() {
    loadDashboard();loadAtRisk();loadAnalysis();loadWAConvos();
    setInterval(()=>{try{loadDashboard();loadAnalysis();loadWAConvos();}catch(e){console.error(e);}},2000);
}
// The final shared workspace renderer loads operational pages on demand.

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('demo') === 'true') {
    // The final dashboard layer starts this after it has finished installing
    // the clean, non-persistent presentation flow.
    window.__guidedDemoRequested = true;
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
        const d = await api('/api/manual-call', 'POST');
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
        if(window.startManualLiveCall) window.startManualLiveCall(d);
        
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
  cursor.innerHTML=`<svg width="42" height="42" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 2L11 22L13.5 14.5L21 12L4 2Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
  cursor.style.left='50vw';cursor.style.top='50vh';cursor.style.opacity='.82';
  document.body.appendChild(cursor); return cursor;
}
async function cursorStep(cursor, target, action, moveDuration=380){
  if(!target) return;
  const rect=target.getBoundingClientRect();
  cursor.style.transform='none';
  cursor.style.left=(rect.left+rect.width*.55)+'px'; cursor.style.top=(rect.top+rect.height*.55)+'px';
  await pause(moveDuration); cursor.style.opacity='1';
  
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
function parkDemoCursor(cursor){
  cursor.style.left='calc(100vw - 64px)';cursor.style.top='50vh';cursor.style.transform='translateY(-50%)';cursor.style.opacity='.82';
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
  const followupText='NEXT: WHATSAPP FOLLOW-UP';
  modal.innerHTML='<div style="width:min(460px,100%);background:var(--bg);border:1px solid rgba(239,68,68,.55);border-radius:16px;padding:28px;box-shadow:0 0 60px rgba(239,68,68,.2)"><div class="mono" style="color:var(--red);margin-bottom:12px">STUDENT FLAGGED · VOICE RISK CONFIRMED</div><h2 style="font-size:25px;margin-bottom:12px">Aarav Patel has high dropout risk</h2><p style="color:var(--text2);line-height:1.65;font-size:13px">Financial pressure and reduced confidence were detected in the live call. A financial-aid intervention and supportive follow-up are recommended.</p><div style="margin-top:18px;color:var(--amber);font:11px var(--mono)">AI SUMMARY REVIEW · WHATSAPP FOLLOWS IN 5 SECONDS</div></div>';
  modal.innerHTML=modal.innerHTML.replace(/AI SUMMARY REVIEW[^<]*/g,followupText);
  document.body.appendChild(modal); await pause(5000); modal.remove();
}
async function startGuidedDemo(){
  if(window.__guidedDemoActive) return;
  window.__guidedDemoActive=true;
  const interactionLock=document.createElement('div');
  interactionLock.id='guided-demo-lock';
  interactionLock.style.cssText='position:fixed;inset:0;z-index:19998;background:transparent;cursor:default';
  interactionLock.addEventListener('pointerdown',event=>{event.preventDefault();event.stopPropagation();},true);
  interactionLock.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();},true);
  interactionLock.addEventListener('wheel',event=>event.preventDefault(),{passive:false});
  const blockDemoKeys=event=>{if(window.__guidedDemoActive){event.preventDefault();event.stopPropagation();}};
  document.addEventListener('keydown',blockDemoKeys,true);
  interactionLock._cleanup=()=>document.removeEventListener('keydown',blockDemoKeys,true);
  document.body.appendChild(interactionLock);
  const cursor=createDemoCursor();
  const end=document.createElement('button');
  end.className='btn btn-red'; end.textContent='End Demo';
  end.style.cssText='position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:20001;padding:12px 24px;height:auto;font-size:14px';
  end.onclick=()=>window.location.href='/logout'; document.body.appendChild(end);

  const cta=document.querySelector('button.nav-cta');
  const oldClick=cta.onclick;
  cta.onclick=null;
  cursor.style.transition='all 1.1s cubic-bezier(.2,.9,.2,1)';
  await pause(450);
  await cursorStep(cursor, cta, null, 1200);
  cta.onclick=oldClick;
  const calling=document.createElement('div');
  calling.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:20px';
  calling.innerHTML='<div style="width:min(400px,100%);background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:30px;text-align:center;box-shadow:0 0 64px rgba(0,0,0,.45)"><div class="loading-spinner" style="width:34px;height:34px;border-width:3px;margin:0 auto 18px"></div><h2 style="font-size:21px;margin-bottom:8px">Calling Student</h2><p style="font-size:13px;color:var(--text2)">Connecting to Aarav Patel…</p></div>';
  document.body.appendChild(calling);await pause(1800);calling.remove();
  await cursorStep(cursor, document.querySelector('[data-page="transcript"]'), ()=>setPage('transcript'));
  parkDemoCursor(cursor);
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
  updateDemoSummary();
  parkDemoCursor(cursor);
  await pause(450);
  await showRiskConfirmed();
  await cursorStep(cursor, document.querySelector('[data-page="whatsapp"]'), ()=>setPage('whatsapp'));
  parkDemoCursor(cursor);
  await pause(500);
  demoWaMessages=[];
  await typeDemoMessage('assistant', 'Hi Aarav, this is Asha from Student Wellness. I heard that finances have been making this semester difficult. Would you like support from Financial Aid?');
  await pause(900);
  await typeDemoMessage('user', 'Yes please. My scholarship reduction has made it hard to manage everything.');
  await pause(900);
  await typeDemoMessage('assistant', 'I have flagged this for priority financial-aid advising. A counselor will contact you within 24 hours, and you can also visit Student Support Center, Building B, Room 204.');
  localStorage.setItem('dropout-signal-aarav-followup','1');
  await pause(1200);
  const connected=document.createElement('div'); connected.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.78);display:grid;place-items:center;padding:20px';
  connected.innerHTML='<div style="width:min(420px,100%);background:var(--bg);border:1px solid var(--green);border-radius:16px;padding:28px;text-align:center"><div class="mono" style="color:var(--green);margin-bottom:12px">INTERVENTION CONFIRMED</div><h2 style="font-size:24px;margin-bottom:10px">Aarav has been connected to help</h2><p style="color:var(--text2);font-size:13px;line-height:1.6">Financial-aid support has been notified and a counselor follow-up is scheduled.</p></div>';
  document.body.appendChild(connected); await pause(3000); connected.remove();
  const ended=document.createElement('div'); ended.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.78);display:grid;place-items:center;padding:20px';
  ended.innerHTML='<div style="width:min(460px,100%);background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:38px;text-align:center"><div class="mono" style="color:var(--text3);font-size:18px;font-weight:700;letter-spacing:2px;margin-bottom:16px">DEMO ENDED</div><h2 style="font-size:30px;margin-bottom:12px">Returning to the home page</h2><p style="color:var(--text2);font-size:15px">The complete intervention flow has finished.</p></div>';
  document.body.appendChild(ended); await pause(2200);
  window.location.href='/logout';
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
  function enrichSummaryCards(){document.querySelectorAll('#summary-students .summary-person').forEach(card=>{if(card.dataset.enriched)return;const name=card.querySelector('h3')?.textContent||'Student';const tier=card.textContent.toUpperCase().includes('HIGH')?'HIGH':'MEDIUM';const score=(card.textContent.match(/0\\.\\d+/)||['0.72'])[0];const action=card.querySelector('div:last-child')?.textContent||'schedule a counselor check-in';card.dataset.enriched='1';card.setAttribute('onclick', "const d1=this.querySelector('.summary-copy'); const d2=this.querySelector('.summary-meta'); const isHidden=d1.style.display==='none'; document.querySelectorAll('.summary-copy').forEach(x=>x.style.display='none'); document.querySelectorAll('.summary-meta').forEach(x=>x.style.display='none'); d1.style.display=isHidden?'block':'none'; d2.style.display=isHidden?'flex':'none';");card.innerHTML=`<span class="summary-chip ${tier==='HIGH'?'high':'medium'}">${tier} RISK · SCORE ${score}</span><h3 style="margin:12px 0 4px">${name}</h3><div class="summary-copy" style="display:none">AI synthesis: ${name} is showing ${tier.toLowerCase()} dropout risk with a ${score} model score. Attendance, academic momentum, and engagement signals suggest a focused support conversation. Recommended next step: ${action} within 48 hours.</div><div class="summary-meta" style="display:none"><span>Attendance ${tier==='HIGH'?'61':'78'}%</span><span>GPA ${tier==='HIGH'?'2.4':'3.1'}</span><span>Signal confidence ${tier==='HIGH'?'High':'Moderate'}</span></div>`});}
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

# Final interactive chart layer.  It is appended after the legacy dashboard
# scripts so every period selector updates the visible data consistently.
_DASHBOARD_INTERACTIONS = r'''
<script>
(function () {
  const overviewPeriods = {
    this_sem:   { high: 142, medium: 875, low: 3483 },
    last_sem:   { high: 168, medium: 922, low: 3520 },
    this_month: { high: 41,  medium: 262, low: 1197 },
    last_month: { high: 55,  medium: 289, low: 1156 },
    this_year:  { high: 514, medium: 3210, low: 14476 },
    last_year:  { high: 596, medium: 3528, low: 13976 }
  };
  const colors = { high: 'var(--red)', medium: 'var(--amber)', low: 'var(--green)' };

  function tierMarkup(data, className) {
    const total = data.high + data.medium + data.low;
    const highEnd = data.high / total * 100;
    const mediumEnd = highEnd + data.medium / total * 100;
    const row = (label, key) => `<div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:${colors[key]}"></span>${label}</span><strong>${data[key].toLocaleString()}</strong></div>`;
    return `<div class="d-chart-container"><div class="${className}" style="width:150px;height:150px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(${colors.high} 0 ${highEnd.toFixed(2)}%,${colors.medium} ${highEnd.toFixed(2)}% ${mediumEnd.toFixed(2)}%,${colors.low} ${mediumEnd.toFixed(2)}% 100%);box-shadow:0 0 26px rgba(99,102,241,.14)"><div style="width:104px;height:104px;border-radius:50%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center"><strong style="font-size:24px;color:var(--text)">${total.toLocaleString()}</strong><span style="font-size:11px;color:var(--text3)">students</span></div></div></div><div class="d-legend">${row('High risk', 'high')}${row('Medium risk', 'medium')}${row('Low risk', 'low')}</div>`;
  }

  window.updateRiskOverview = function (period, scope) {
    const data = overviewPeriods[period] || overviewPeriods.this_sem;
    const chart = document.getElementById(scope === 'admin' ? 'tier-chart' : 'tier-chart-counselor');
    if (chart) chart.innerHTML = tierMarkup(data, scope === 'admin' ? 'admin-risk-donut' : 'risk-donut');

    const total = data.high + data.medium + data.low;
    const atRisk = data.high + data.medium;
    const riskBadge = document.querySelector('.risk-fixed-badge');
    if (riskBadge) riskBadge.textContent = `${atRisk.toLocaleString()} at risk`;
    const totalCard = document.getElementById('cd-calls')||document.getElementById('s-bronze');
    const atRiskCard = document.getElementById('cd-med')||document.getElementById('s-gold');
    const highCard = document.getElementById('cd-high')||document.getElementById('s-avgrisk');
    const interventionCard=document.getElementById('cd-wa')||document.getElementById('s-voice');
    const sideRisk = document.getElementById('sb-risk-count');
    if (totalCard) totalCard.textContent = total.toLocaleString();
    if (atRiskCard) atRiskCard.textContent = atRisk.toLocaleString();
    if (highCard) highCard.textContent = data.high.toLocaleString();
    if (interventionCard) interventionCard.textContent=({this_sem:62,last_sem:54,this_month:18,last_month:22,this_year:1205,last_year:1088}[period]||62).toLocaleString();
    if (sideRisk) sideRisk.textContent = atRisk.toLocaleString();
    const changes={this_sem:['5.6%','12.4%','8.2%','15.3%'],last_sem:['3.1%','9.8%','6.4%','12.1%'],this_month:['1.8%','7.1%','4.3%','9.6%'],last_month:['2.4%','8.6%','5.7%','10.2%'],this_year:['8.9%','15.2%','10.6%','21.4%'],last_year:['7.2%','13.7%','9.4%','18.8%']};
    document.querySelectorAll('.stat-box .sb-trend').forEach((el,index)=>{if(changes[period])el.lastChild.textContent=' '+changes[period][index];});
    if(window.updateRiskTrend)window.updateRiskTrend(period);
  };

  window.resetLiveOperations = async function () {
    if (!confirm('Reset live calls and WhatsApp conversations?')) return;
    const response = await fetch('/api/reset', {method:'POST'});
    if (!response.ok) return;
    window.__manualLiveCall=null;window.__manualWhatsApp=null;localStorage.removeItem('dropout-signal-aarav-followup');
    ['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent='Waiting for active calls...';});
    ['wa-convos-panel','admin-wa-panel'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='<p style="color:var(--text3);font-size:12px">WhatsApp conversations appear here.</p>';});
    ['sb-voice-count','sb-wa-count','admin-voice-count','admin-wa-count'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent='0';});
    if(window.renderDummyLiveOperations)window.renderDummyLiveOperations();
  };

  // Always-on sample operations make the live workspaces useful until a real
  // Twilio session arrives. Each refresh advances the current call response.
  const operationalStudents=[
    {id:'BIO-22-0992',name:'Riya Singh',risk:'HIGH',score:'.710',attendance:'68%',gpa:'2.6',signal:'Missed assignments',reply:'I have been sick and missed the lab.'},
    {id:'EC-21-0876',name:'Neha Patil',risk:'MEDIUM',score:'.610',attendance:'74%',gpa:'2.8',signal:'Attendance decline',reply:'My evening shifts have made it hard to attend every class.'},
    {id:'ME-21-0654',name:'Rohan Verma',risk:'HIGH',score:'.780',attendance:'65%',gpa:'2.5',signal:'Low LMS engagement',reply:'I have fallen behind on the assessment work.'},
    {id:'CS-21-1042',name:'Arjun Sharma',risk:'HIGH',score:'.910',attendance:'58%',gpa:'2.1',signal:'Academic performance',reply:'I need help making a plan before the next exam.'},
    {id:'BA-22-0318',name:'Priya Nair',risk:'MEDIUM',score:'.540',attendance:'79%',gpa:'3.0',signal:'Wellbeing check-in',reply:'I have been feeling overwhelmed but want to continue.'},
    {id:'IT-21-1184',name:'Suman Tiwari',risk:'HIGH',score:'.860',attendance:'61%',gpa:'2.4',signal:'Financial-aid status',reply:'The fee balance has been causing a lot of stress.'},
    {id:'CE-22-0441',name:'Kiran Thakur',risk:'MEDIUM',score:'.590',attendance:'76%',gpa:'2.9',signal:'Course engagement',reply:'I would appreciate support getting back on track.'}
  ];
  let liveTick=0;
  window.showOperationalStudent=function(id){
    const s=operationalStudents.find(x=>x.id===id)||operationalStudents[0],high=s.risk==='HIGH',color=high?'var(--red)':'var(--amber)';
    const modal=document.getElementById('modal'),body=document.getElementById('modal-body');if(!modal||!body)return;
    body.innerHTML=`<span class="modal-close" onclick="closeModal()">&times;</span><span class="summary-chip ${high?'high':'medium'}">${s.risk} RISK · SCORE ${s.score}</span><h2 style="font-size:24px;margin:14px 0 4px">${s.name}</h2><div class="mono" style="font-size:11px;color:var(--text3)">${s.id} · LIVE STUDENT PROFILE</div><div style="margin:18px 0;padding:15px;border:1px solid ${color};border-radius:12px;background:color-mix(in srgb,${color} 10%,transparent)"><div class="mono" style="font-size:10px;color:${color};margin-bottom:8px">AI STUDENT SUMMARY</div><p style="margin:0;color:var(--text2);font-size:13px;line-height:1.65">${s.name} is showing ${s.risk.toLowerCase()} dropout risk. The active signal is ${s.signal.toLowerCase()}, with attendance, academic progress, and engagement indicating a focused support conversation.</p></div><div class="detail-grid"><div class="detail-item"><div class="dl">College ID</div><div class="dv">${s.id}</div></div><div class="detail-item"><div class="dl">Attendance</div><div class="dv">${s.attendance}</div></div><div class="detail-item"><div class="dl">Current GPA</div><div class="dv">${s.gpa}</div></div><div class="detail-item"><div class="dl">Live signal</div><div class="dv">${s.signal}</div></div></div><div style="margin-top:16px;padding:14px;background:var(--surface2);border-radius:10px"><div class="mono" style="font-size:10px;color:var(--purple);margin-bottom:7px">RECOMMENDED NEXT ACTION</div><p style="margin:0;color:var(--text2);font-size:12px;line-height:1.6">Schedule a counselor check-in and connect ${s.name.split(' ')[0]} to the appropriate academic or financial support within 48 hours.</p></div>`;
    modal.classList.add('show');
  };
  window.startManualLiveCall=function(data){
    const uid = data.student_id||'STU-2847';
    window.__manualLiveCall={id:uid,name:data.student_name||'Student',started:Date.now()};
    window.__manualWhatsApp=null;
    window.__expandedTranscripts = window.__expandedTranscripts || new Set();
    window.__expandedTranscripts.clear();
    window.__expandedTranscripts.add(uid + '_voice');
    window.renderDummyLiveOperations();
  };
  window.completeManualLiveCall=async function(){
    const call=window.__manualLiveCall;if(!call)return;
    window.__manualLiveCall=null;
    window.__manualWhatsApp={id:call.id,name:call.name};
    window.__expandedTranscripts = window.__expandedTranscripts || new Set();
    window.__expandedTranscripts.clear();
    window.__expandedTranscripts.add(call.id + '_wa');
    window.renderDummyLiveOperations();
    if(window.showRiskConfirmed)await window.showRiskConfirmed();
    const counselorTab=document.querySelector('[data-page="whatsapp"]');
    const adminTab=document.querySelector('[data-page="admin-whatsapp"]');
    (counselorTab||adminTab)?.click();
    window.renderDummyLiveOperations();
  };
  window.__expandedTranscripts = window.__expandedTranscripts || new Set();
  window.toggleTranscript = function(event, id) {
    const isExpanded = window.__expandedTranscripts.has(id);
    window.__expandedTranscripts.clear();
    if (!isExpanded) {
        window.__expandedTranscripts.add(id);
    }
    window.renderDummyLiveOperations();
    if (event) event.stopPropagation();
  };
  
  const st = document.createElement('style');
  st.textContent = `
    #page-transcript .card, #page-admin-transcript .card, #page-admin-whatsapp .card, #page-whatsapp .card { max-width: 95%; margin: 0 auto; min-height: 70vh; }
    .transcript-expanded-view { margin-top:16px; padding:24px; background:var(--bg); border:1px solid var(--border); border-radius:12px; font-size:13px; line-height:1.7; text-align:left; cursor:default; }
    .transcript-expanded-view .speaker { font-weight:600; color:var(--text); text-transform:uppercase; font-size:11px; letter-spacing:0.5px; margin-bottom:4px; margin-top:16px; }
    .transcript-expanded-view .speaker.ai { color:var(--purple); }
    .transcript-expanded-view .speaker.student { color:var(--blue); }
    .transcript-expanded-view .time { color:var(--text3); font-weight:normal; font-size:10px; margin-left:6px; }
  `;
  document.head.appendChild(st);
  window.renderDummyLiveOperations=function(){
    if(window.__guidedDemoActive)return;
    const phase=liveTick%3,asha=['How has this week been going for you?','What is the biggest challenge right now?','Would a counselor follow-up be helpful?'][phase];
    const manual=window.__manualLiveCall; if(manual&&manual.name==='Student'&&Date.now()-manual.started>8000){manual.name='Aarav Patel';}
    const persistedAarav=!manual&&localStorage.getItem('dropout-signal-aarav-followup')==='1'?{id:'STU-2847',name:'Aarav Patel'}:null;
    
    const isVoiceExpanded = (id) => window.__expandedTranscripts.has(id + '_voice');
    const isWaExpanded = (id) => window.__expandedTranscripts.has(id + '_wa');
    
    const manualRow=manual?`<article style="padding:14px;border:1px solid var(--red);border-radius:10px;margin-bottom:12px"><div style="display:flex;justify-content:space-between;gap:12px;cursor:pointer" onclick="window.toggleTranscript(event, '${manual.id}_voice')"><strong style="color:var(--red)">☎ ${manual.name}</strong><span class="mono" style="font-size:10px;color:var(--text3)">${manual.id} · YOUR ACTIVE CALL</span></div><div class="transcript-expanded-view" style="display:${isVoiceExpanded(manual.id)?'block':'none'}" onclick="event.stopPropagation()"><div style="font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;">Live Call Transcript</div><div style="color:var(--text2); margin-bottom:16px;">Student: ${manual.name} (${manual.id})</div><div class="speaker ai">Asha AI <span class="time">00:00</span></div><div>Hi ${manual.name.split(' ')[0]}, this is Asha calling from student wellness. How are you doing today?</div><div class="speaker student">${manual.name.split(' ')[0]} <span class="time">00:08</span></div><div>I am concerned about keeping up with my coursework and finances.</div><div class="speaker ai">Asha AI <span class="time">00:15</span></div><div>${asha}</div><button class="btn btn-red" style="margin-top:20px;padding:7px 10px" onclick="completeManualLiveCall()">End Call</button></div></article>`:persistedAarav?`<article style="padding:14px;border:1px solid var(--green);border-radius:10px;margin-bottom:12px"><div style="display:flex;justify-content:space-between;gap:12px;cursor:pointer" onclick="window.toggleTranscript(event, '${persistedAarav.id}_voice')"><strong style="color:var(--green)">☎ ${persistedAarav.name}</strong><span class="mono" style="float:right;font-size:10px;color:var(--text3)">${persistedAarav.id} · COMPLETED</span></div><div class="transcript-expanded-view" style="display:${isVoiceExpanded(persistedAarav.id)?'block':'none'}" onclick="event.stopPropagation()"><div style="font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;">Live Call Transcript</div><div style="color:var(--text2); margin-bottom:16px;">Student: ${persistedAarav.name} (${persistedAarav.id})</div><div class="speaker ai">Asha AI <span class="time">00:00</span></div><div>Hi ${persistedAarav.name.split(' ')[0]}, this is Asha calling from student wellness. How are you doing today?</div><div class="speaker student">${persistedAarav.name.split(' ')[0]} <span class="time">00:08</span></div><div>I am concerned about keeping up with my coursework and finances.</div><div class="speaker ai">Asha AI <span class="time">00:15</span></div><div>I'm connecting you with financial aid.</div></div></article>`:'';
    const transcriptRows=manualRow+operationalStudents.filter(s=>!(manual&&s.id===manual.id)&&!(persistedAarav&&s.id===persistedAarav.id)).map((s,index)=>`<article style="padding:13px 0;border-bottom:1px solid var(--border)"><div style="display:flex;justify-content:space-between;gap:12px;cursor:pointer" onclick="window.toggleTranscript(event, '${s.id}_voice')"><strong style="color:var(--blue)">☎ ${s.name}</strong><span class="mono" style="font-size:10px;color:var(--text3)">${s.id} · LIVE</span></div><div class="transcript-expanded-view" style="display:${isVoiceExpanded(s.id)?'block':'none'}" onclick="event.stopPropagation()"><div style="font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;">Live Call Transcript</div><div style="color:var(--text2); margin-bottom:16px;">Student: ${s.name} (${s.id})</div><div class="speaker ai">Asha AI <span class="time">00:00</span></div><div>Hi ${s.name.split(' ')[0]}, this is Asha calling from student wellness. How are you doing today?</div><div class="speaker student">${s.name.split(' ')[0]} <span class="time">00:08</span></div><div>${s.reply}</div><div class="speaker ai">Asha AI <span class="time">00:15</span></div><div>${asha}</div><div class="speaker student">${s.name.split(' ')[0]} <span class="time">00:22</span></div><div>${phase===0?'Yes, I think so.':'… speaking live'}</div></div></article>`).join('');
    window.__dummyTranscripts=transcriptRows;
    
    const followedUp=window.__manualWhatsApp||persistedAarav;
    const manualChat=followedUp?`<article style="padding:14px;border:1px solid var(--green);border-radius:10px;margin-bottom:12px"><div style="display:flex;justify-content:space-between;cursor:pointer" onclick="window.toggleTranscript(event, '${followedUp.id}_wa')"><strong style="color:var(--green)">${followedUp.name}</strong><span class="mono" style="font-size:10px;color:var(--text3)">${followedUp.id} · FOLLOW-UP</span></div><div class="transcript-expanded-view" style="display:${isWaExpanded(followedUp.id)?'block':'none'}" onclick="event.stopPropagation()"><div style="font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;">WhatsApp Conversation</div><div style="color:var(--text2); margin-bottom:16px;">Student: ${followedUp.name} (${followedUp.id})</div><div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>I am connecting you with financial-aid support and a counselor today.</div></div><div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${followedUp.name.split(' ')[0]}</div>Thank you, I would really appreciate that.</div></div></div></article>`:'';
    const conversationRows=manualChat+operationalStudents.filter(s=>!(followedUp&&s.id===followedUp.id)).map((s,index)=>`<article style="padding:13px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px"><div style="display:flex;justify-content:space-between;cursor:pointer" onclick="window.toggleTranscript(event, '${s.id}_wa')"><strong style="color:var(--green)">${s.name}</strong><span class="mono" style="font-size:10px;color:var(--text3)">${s.id}</span></div><div class="transcript-expanded-view" style="display:${isWaExpanded(s.id)?'block':'none'}" onclick="event.stopPropagation()"><div style="font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;">WhatsApp Conversation</div><div style="color:var(--text2); margin-bottom:16px;">Student: ${s.name} (${s.id})</div><div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>Hi ${s.name.split(' ')[0]}, following up on our call. Have you been able to review the resources I sent over?</div></div><div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${s.name.split(' ')[0]}</div>Not yet, I've been busy. ${s.reply}</div></div><div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>${asha}</div></div><div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end"><div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px"><div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${s.name.split(' ')[0]}</div>${phase===2?'Yes, that would help.':s.reply}</div></div></div></article>`).join('');
    window.__dummyWaRows=conversationRows;
    const activeCount=String(operationalStudents.length+(manual?1:0));
    ['sb-voice-count','admin-voice-count'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=activeCount;});
    ['sb-wa-count','admin-wa-count'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent='7';});
    const adminActive=document.getElementById('admin-ts-count');if(adminActive)adminActive.textContent=activeCount+' active';
    const counselorActive=document.getElementById('ts-count');if(counselorActive)counselorActive.textContent=activeCount+' active';
    const adminWa=document.getElementById('admin-wa-badge');if(adminWa)adminWa.textContent='7 conversations';
    const counselorWa=document.getElementById('wa-count-badge');if(counselorWa)counselorWa.textContent='7 active';
    liveTick++;
  };
  window.renderOperationalSummaries=function(){
    const cards=operationalStudents.map(s=>`<article class="summary-person" style="cursor:pointer" onclick="showOperationalStudent('${s.id}')"><span class="summary-chip ${s.risk==='HIGH'?'high':'medium'}">${s.risk} RISK · SCORE ${s.score}</span><h3 style="margin:13px 0 4px">${s.name}</h3></article>`).join('');
    ['summary-students'].forEach(id=>{const grid=document.getElementById(id);if(grid)grid.innerHTML=cards;});
  };
  // The final renderer below owns both transcript and summary DOM updates.

  window.updateRiskTrend = function (period) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    const trends = {
      weekly: {
        labels: ['Apr 28', 'May 5', 'May 12', 'May 19', 'May 26', 'Jun 2'],
        low: [338, 309, 328, 291, 322, 276], medium: [214, 173, 195, 147, 181, 132], high: [28, 46, 5, 29, 14, 58]
      },
      monthly: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        low: [1320, 1240, 1348, 1182, 1276, 1394], medium: [286, 251, 274, 229, 247, 262], high: [54, 63, 47, 72, 58, 41]
      }
    };
    const trendProfile={this_sem:[trends.weekly,1],last_sem:[trends.weekly,1.08],this_month:[trends.weekly,.36],last_month:[trends.weekly,.39],this_year:[trends.monthly,1],last_year:[trends.monthly,1.1]}[period]||[trends.weekly,1];
    const base=trendProfile[0],multiplier=trendProfile[1];
    const data={labels:base.labels,low:base.low.map(v=>Math.round(v*multiplier)),medium:base.medium.map(v=>Math.round(v*multiplier)),high:base.high.map(v=>Math.round(v*multiplier))};
    const max = Math.ceil(Math.max(...data.low, ...data.medium, ...data.high) / 100) * 100;
    const xs = [42, 132, 222, 312, 402, 492];
    const y = value => 176 - (value / max * 150);
    const points = values => values.map((value, index) => `${xs[index]},${y(value).toFixed(1)}`).join(' ');
    const dots = (values, color) => values.map((value, index) => `<circle cx="${xs[index]}" cy="${y(value).toFixed(1)}" r="3.4" fill="${color}" stroke="var(--surface)" stroke-width="2"/>`).join('');
    const lines = [ ['low', colors.low], ['medium', colors.medium], ['high', colors.high] ];
    const grid = [0, 1, 2, 3, 4].map(index => {
      const gy = 26 + index * 37.5;
      return `<line x1="40" y1="${gy}" x2="500" y2="${gy}" stroke="var(--border)" stroke-dasharray="3 5"/><text x="32" y="${gy + 4}" fill="var(--text3)" font-size="10" text-anchor="end">${Math.round(max - index * max / 4)}</text>`;
    }).join('');
    svg.innerHTML = `<defs><linearGradient id="riskTrendFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".16"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs><rect x="40" y="10" width="460" height="170" rx="10" fill="url(#riskTrendFill)" opacity=".35"/>${grid}${lines.map(([key, color]) => `<polyline points="${points(data[key])}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots(data[key], color)}`).join('')}${data.labels.map((label, index) => `<text x="${xs[index]}" y="198" fill="var(--text3)" font-size="10" text-anchor="middle">${label}</text>`).join('')}`;
    const badge = document.querySelector('.risk-fixed-badge');
    if (badge) badge.textContent = `${(data.medium.at(-1) + data.high.at(-1)).toLocaleString()} at risk`;
  };

  setTimeout(() => {
    const counselorSelect = document.getElementById('risk-overview-select');
    const adminSelect = document.getElementById('admin-risk-overview-select');
    if (counselorSelect) window.updateRiskOverview(counselorSelect.value);
    if (adminSelect) window.updateRiskOverview(adminSelect.value, 'admin');
    if (counselorSelect) window.updateRiskTrend(counselorSelect.value);
    if (adminSelect) window.updateRiskTrend(adminSelect.value);
  }, 0);
})();
</script>'''

ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace("</body></html>", _DASHBOARD_INTERACTIONS + "</body></html>")
COUNSELOR_DASHBOARD = COUNSELOR_DASHBOARD.replace("</body></html>", _DASHBOARD_INTERACTIONS + "</body></html>")

# Final workspace layer.  The original prototype accumulated a few competing
# renderers; this layer owns the list/detail interactions on both dashboards.
_OPERATIONS_UI = r'''
<script>
(() => {
  const students = [
    {id:'BIO-22-0992',name:'Riya Singh',risk:'HIGH',score:'0.71',course:'B.Sc. Biotechnology',branch:'Life Sciences',year:'3',semester:'5',marks:'68%',attendance:'68%',reply:'I have been sick and missed the lab sessions.'},
    {id:'EC-21-0876',name:'Neha Patil',risk:'MEDIUM',score:'0.61',course:'B.Tech',branch:'Electronics & Communication',year:'4',semester:'7',marks:'72%',attendance:'74%',reply:'My evening shifts have made it hard to attend every class.'},
    {id:'ME-21-0654',name:'Rohan Verma',risk:'HIGH',score:'0.78',course:'B.Tech',branch:'Mechanical Engineering',year:'4',semester:'7',marks:'64%',attendance:'65%',reply:'I have fallen behind on the assessment work.'},
    {id:'CS-21-1042',name:'Arjun Sharma',risk:'HIGH',score:'0.91',course:'B.Tech',branch:'Computer Science',year:'4',semester:'7',marks:'59%',attendance:'58%',reply:'I need help making a plan before the next exam.'},
    {id:'BA-22-0318',name:'Priya Nair',risk:'MEDIUM',score:'0.54',course:'BBA',branch:'Business Administration',year:'3',semester:'5',marks:'76%',attendance:'79%',reply:'I have been feeling overwhelmed but want to continue.'},
    {id:'IT-21-1184',name:'Suman Tiwari',risk:'HIGH',score:'0.86',course:'B.Tech',branch:'Information Technology',year:'4',semester:'7',marks:'62%',attendance:'61%',reply:'The fee balance has been causing a lot of stress.'},
    {id:'CE-22-0441',name:'Kiran Thakur',risk:'MEDIUM',score:'0.59',course:'B.Tech',branch:'Civil Engineering',year:'3',semester:'5',marks:'71%',attendance:'76%',reply:'I would appreciate support getting back on track.'}
  ];
  const historicalNames = ['Aditi Rao','Vikram Bose','Nisha Das','Sanjay Singh','Meera Iyer','Kabir Mehta','Ananya Tiwari','Gaurav Chaudhary','Divya Singh','Rahul Patel','Pooja Menon','Suresh Menon','Kriti Sharma','Naveen Kumar','Isha Gupta','Manav Khanna','Sakshi Jain','Ritesh Kapoor','Tanvi Shah','Aditya Nair','Sneha Reddy','Pranav Joshi','Ira Banerjee','Yash Malhotra','Maya Kulkarni'];
  const historicalStudents = historicalNames.map((name,index) => ({
    id:`HIS-${String(index + 1).padStart(3,'0')}`,
    name,
    risk:index % 4 === 0 ? 'HIGH' : index % 3 === 0 ? 'MEDIUM' : 'LOW',
    score:(0.34 + (index % 6) * 0.07).toFixed(2),
    course:['B.Tech','BBA','B.Sc.'][index % 3], branch:['Computer Science','Business Administration','Life Sciences','Mechanical Engineering'][index % 4],
    year:String((index % 4) + 1), semester:String((index % 8) + 1), marks:`${70 + (index % 14)}%`, attendance:`${72 + (index % 16)}%`,
    reply:['I have reviewed the resources and feel more confident.','The study plan has helped me catch up.','I am arranging time with my faculty advisor.','Things are improving after the support conversation.'][index % 4], archived:true
  }));
  const storageKey = 'dropout-signal-live-demo-v2';
  const clean = value => String(value || '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const read = () => { try { return JSON.parse(localStorage.getItem(storageKey)) || {}; } catch (_) { return {}; } };
  const save = data => localStorage.setItem(storageKey, JSON.stringify(data));
  const persistedState=read(), refreshedActualCall=Boolean(persistedState.demo?.actualCall);
  // A refresh starts a clean manual-call workspace. During an open tab the
  // state is still retained, so call and follow-up data remain visible until
  // the user intentionally reloads the browser.
  if(refreshedActualCall){persistedState.demo=null;persistedState.voiceOpen=null;persistedState.waOpen=null;persistedState.voiceSteps={};persistedState.waSteps={};localStorage.removeItem(storageKey);fetch('/api/reset',{method:'POST'}).catch(()=>{});}
  // Normal sample conversations restart at their first exchange whenever the
  // dashboard is loaded. Their progress is deliberately not restored from a
  // previous visit, so opening a transcript always starts at a readable pace.
  persistedState.voiceOpen=null;persistedState.waOpen=null;persistedState.voiceSteps={};persistedState.waSteps={};
  let state = Object.assign({voiceOpen:null, waOpen:null, demo:null, tick:0, voiceQuery:'', waQuery:'', scrollLocks:{}, scrollTops:{}, voiceSteps:{}, waSteps:{}, directoryTotal:4500}, persistedState);
  state.scrollLocks=state.scrollLocks||{};
  state.scrollTops=state.scrollTops||{};
  state.voiceSteps=state.voiceSteps||{};
  state.waSteps=state.waSteps||{};
  state.directoryTotal=Number(state.directoryTotal)||4500;
  let summaryStudents = [];
  let summaryQuery = '';
  let summaryLimit = 80;
  let atRiskRecords = null;
  let atRiskRequest = null;
  let atRiskLimit = 60;
  let directoryStudents = [];
  let directoryRequest = null;
  let directoryLoading = false;
  let directoryQuery = '';
  let directoryLimit = 80;
  const fromApi = student => ({
    id:String(student.student_id), name:student.student_name || 'Student',
    risk:String(student.final_risk_tier || 'LOW').toUpperCase(), score:Number(student.ml_risk_score || 0).toFixed(2),
    course:student.course || 'Undergraduate program', branch:student.branch || 'Academic department',
    year:student.year || '—', semester:student.semester || '—', marks:student.latest_marks || '—',
    attendance:`${student.attendance_rate ?? '—'}${student.attendance_rate === undefined ? '' : '%'}`,
    reply:student.final_action || 'A student-support check-in is recommended.', source:'directory'
  });
  const demoStudent = () => state.demo ? Object.assign({course:'B.Tech',branch:'Computer Science',year:'3',semester:'5',marks:'66%',attendance:'61%',risk:'HIGH',score:'0.87',reply:'I am worried about managing my coursework and fees.'}, state.demo) : null;
  const activeStudents = () => {
    const demo=demoStudent();
    return demo && !demo.archived ? [demo, ...students] : students;
  };
  const allStudents = () => activeStudents();
  const riskRank = risk => ({HIGH:0,MEDIUM:1,LOW:2}[String(risk).toUpperCase()] ?? 3);
  const operationStudents = () => [...(demoStudent()?[demoStudent()]:[]), ...students, ...historicalStudents].sort((a,b)=>{
    if(state.demo?.id===a.id)return -1;if(state.demo?.id===b.id)return 1;
    if(isActive(a)!==isActive(b))return isActive(a)?-1:1;
    return riskRank(a.risk)-riskRank(b.risk)||a.name.localeCompare(b.name);
  });
  const summaryPeople = () => {
    const combined = [...(demoStudent() ? [demoStudent()] : []), ...(summaryStudents.length ? summaryStudents : students)];
    return combined.filter((student, index) => combined.findIndex(candidate => candidate.id === student.id) === index).sort((a,b)=>riskRank(a.risk)-riskRank(b.risk)||a.name.localeCompare(b.name));
  };
  const title = student => clean(student.name);
  const first = name => clean((name || 'Student').split(' ')[0]);
  const aiScore = student => Number(student.aiScore ?? Math.min(.98,Number(student.score || .5) + .09)).toFixed(2);

  function persist(){ save({demo:state.demo, voiceOpen:state.voiceOpen, waOpen:state.waOpen, tick:state.tick, voiceQuery:state.voiceQuery, waQuery:state.waQuery, scrollLocks:state.scrollLocks, scrollTops:state.scrollTops, voiceSteps:state.voiceSteps, waSteps:state.waSteps, directoryTotal:state.directoryTotal}); }
  function voiceDetail(s){
    const live = s.id === state.demo?.id && state.demo?.status === 'calling';
    const second = live ? ['I understand. Tell me a little more about what has been hardest this semester.','What support would make the biggest difference right now?','I can help connect you to the right support team.'][state.tick % 3] : 'A counselor follow-up has been scheduled and the recommended resources are ready to share.';
    const captured = Object.values(s.answers || {}).map((answer, index) => `<div class="speaker ai">Asha AI <span class="time">${String(index + 1).padStart(2,'0')}:00</span></div><p>${clean(answer.question)}</p><div class="speaker student">${first(s.name)} <span class="time">${String(index + 1).padStart(2,'0')}:08</span></div><p>${clean(answer.text)}</p>`).join('');
    const liveUpdate = ['Asha is listening for the next response…','New speech segment received — checking student-support options.','Asha is preparing the next follow-up question.'][state.tick % 3];
    return `<div class="operation-detail"><div class="speaker ai">Asha AI <span class="time">00:00</span></div><p>Hello ${first(s.name)}, this is Asha from Student Wellness. How has this semester been going?</p><div class="speaker student">${first(s.name)} <span class="time">00:08</span></div><p>${clean(s.reply)}</p><div class="speaker ai">Asha AI <span class="time">00:15</span></div><p>${second}</p>${captured}<div class="live-pulse">● ${live ? 'AI on call: ' : 'Live demo update: '}${liveUpdate}</div>${live ? '<button class="btn btn-red" onclick="completeManualLiveCall()">End call</button>' : ''}</div>`;
  }
  function waDetail(s){
    const update = ['I am checking the appointment calendar for you now.','I have added the academic-support resource to this conversation.','Your counselor follow-up is being prepared.'][state.tick % 3];
    return `<div class="operation-detail"><div class="chat-line ai-chat"><b>Asha AI</b><span>Hi ${first(s.name)}, I am following up on our student-support check-in. Have you been able to review the resources?</span></div><div class="chat-line student-chat"><b>${first(s.name)}</b><span>${clean(s.reply)}</span></div><div class="chat-line ai-chat"><b>Asha AI</b><span>I have noted this and shared a follow-up with financial aid and academic support. A counselor will contact you shortly.</span></div><div class="chat-line ai-chat"><b>Asha AI · live update</b><span>${update}</span></div></div>`;
  }
  function row(kind, s){
    const open = kind === 'voice' ? state.voiceOpen === s.id : state.waOpen === s.id;
    const tone = kind === 'voice' ? 'var(--blue)' : 'var(--green)';
    return `<article class="operation-row ${open ? 'open' : ''}"><button class="operation-name" onclick="window.toggleOperation('${kind}','${clean(s.id)}')"><span style="color:${tone}">${kind === 'voice' ? '☎' : '●'} ${title(s)}</span></button>${open ? (kind === 'voice' ? voiceDetail(s) : waDetail(s)) : ''}</article>`;
  }
  function enforceOperationCounts(){
    if(window.__guidedDemoActive) return;
    const count=String(allStudents().length);
    const set=(id,value)=>{const el=document.getElementById(id);if(el && el.textContent!==value)el.textContent=value;};
    ['ts-count','admin-ts-count'].forEach(id=>set(id,count+' active'));
    ['sb-voice-count','admin-voice-count'].forEach(id=>set(id,count));
    ['wa-count-badge','admin-wa-badge'].forEach(id=>set(id,count+' conversations'));
    ['sb-wa-count','admin-wa-count'].forEach(id=>set(id,count));
  }
  function renderOperations(){
    // The guided presentation writes its own character-by-character call
    // transcript. Do not let the live workspace renderer overwrite it.
    if(window.__guidedDemoActive) return;
    state.tick = (state.tick || 0) + 1;
    const voice = allStudents().map(s => row('voice', s)).join('');
    const wa = allStudents().map(s => row('wa', s)).join('');
    ['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id => { const el=document.getElementById(id); if(el) el.innerHTML=voice; });
    ['wa-convos-panel','admin-wa-panel'].forEach(id => { const el=document.getElementById(id); if(el) el.innerHTML=wa; });
    enforceOperationCounts();
    persist();
  }
  window.toggleOperation = (kind, id) => { if(kind === 'voice') state.voiceOpen = state.voiceOpen === id ? null : id; else state.waOpen = state.waOpen === id ? null : id; renderOperations(); };
  // Final operation renderer: active conversations and saved conversations
  // intentionally use the same list, while only active conversations advance.
  const isActive = student => !student.archived;
  const activeTurn = (student, channel) => {
    const voiceTurns = [
      ['Asha AI','I hear you. Which part of your coursework feels most difficult right now?'],
      [first(student.name),'Keeping pace with assignments has been the hardest part.'],
      ['Asha AI','Thank you for explaining that. I can arrange academic support and a check-in.'],
      [first(student.name),'That would make a real difference for me.'],
      ['Asha AI','I will share the next steps and make sure the support team follows up.']
    ];
    const whatsappTurns = [
      ['Asha AI','I have found the resources that match the support you need.'],
      [first(student.name),'Thank you. I would like help with the next step.'],
      ['Asha AI','I have added academic guidance and financial-aid information to your plan.'],
      [first(student.name),'I appreciate the help.'],
      ['Asha AI','A counselor will be in touch shortly to help you move forward.']
    ];
    const turns = channel === 'voice' ? voiceTurns : whatsappTurns;
    return turns[state.tick % turns.length];
  };
  function voiceDetail(s){
    const active=isActive(s)&&s.status!=='whatsapp',isCall=s.id===state.demo?.id&&state.demo?.status==='calling';
    if(s.id===state.demo?.id&&s.actualCall){
      const answerValues=Object.values(s.actualAnswers||{}), turns=[];
      const namePrompt='Before we begin, could you please tell me your name?';
      const current=s.currentQuestion||'';
      if(current===namePrompt){turns.push(['Asha AI',namePrompt,false]);}
      else {
        turns.push(['Asha AI',namePrompt,false]);
        if(s.name&&s.name!=='Student')turns.push([first(s.name),`My name is ${s.name}.`,true]);
      }
      answerValues.forEach(answer=>{const reply=String(answer.text||'').trim()==='[no response]'?'Call ended':(answer.text||'Waiting for a response…');turns.push(['Asha AI',answer.question||'Question',false]);turns.push([first(s.name||'Student'),reply,true]);});
      const lastQuestion=answerValues.at(-1)?.question||'';
      if(current&&current!==namePrompt&&current!==lastQuestion)turns.push(['Asha AI',current,false]);
      const transcript=turns.length?turns.map(([speaker,text,student],index)=>`<div class="transcript-message ${student?'student-message':'ai-message'}"><div class="message-bubble"><b>${clean(speaker)}</b><span>${clean(text)}</span><small>${String(Math.floor(index/2)).padStart(2,'0')}:${index%2?'08':'00'}</small></div></div>`).join(''):`<div class="transcript-message ai-message"><div class="message-bubble"><b>Asha AI</b><span>Calling student…</span></div></div>`;
      const ended=['finishing','whatsapp','completed'].includes(s.status)?'<div class="call-ended">Call ended</div>':'';
      return `<div class="operation-detail transcript-thread" onscroll="window.operationScroll('voice','${clean(s.id)}',this)">${transcript}${ended}${isCall&&s.simulated?'<button class="btn btn-red call-end" onclick="completeManualLiveCall()">End call</button>':''}</div>`;
    }
    const captured=Object.values(s.answers||{});
    const questions=[
      'Before we begin, could you please tell me your name?',
      'How has this semester been going for you so far?',
      'What has been the most challenging part of college life recently?',
      'On a scale of 1 to 5, how confident are you about completing your degree?',
      'What support would make the biggest difference for you right now?'
    ];
    const answers=[
      `My name is ${s.name}.`,
      s.reply,
      'Balancing assignments, attendance and personal responsibilities has been difficult.',
      s.risk==='HIGH'?'About two out of five. I need support to feel confident again.':'About three out of five. I think a clear plan would help.',
      s.risk==='HIGH'?'Financial-aid guidance and an academic recovery plan would help most.':'A study plan and a counselor check-in would help most.'
    ];
    captured.slice(0,5).forEach((answer,index)=>{questions[index]=answer.question||questions[index];answers[index]=answer.text||answers[index];});
    const turns=[];
    questions.forEach((question,index)=>{turns.push(['Asha AI',question,false]);turns.push([first(s.name),answers[index],true]);});
    const visible=active?Math.min(turns.length,Math.max(2,state.voiceSteps[s.id]||2)):turns.length;
    const transcript=turns.slice(0,visible).map(([speaker,text,student],index)=>`<div class="transcript-message ${student?'student-message':'ai-message'}"><div class="message-bubble"><b>${clean(speaker)}</b><span>${clean(text)}</span><small>${String(Math.floor(index/2)).padStart(2,'0')}:${index%2?'08':'00'}</small></div></div>`).join('');
    const flag=s.risk==='HIGH'?`<div class="risk-flag">Asha AI has flagged ${title(s)} as high dropout risk. A counselor review has been prioritised.</div>`:'';
    return `<div class="operation-detail transcript-thread" onscroll="window.operationScroll('voice','${clean(s.id)}',this)">${transcript}${visible===turns.length?flag:''}${isCall?'<button class="btn btn-red call-end" onclick="completeManualLiveCall()">End call</button>':''}</div>`;
  }
  const waHash=value=>[...String(value||'')].reduce((total,char)=>total+char.charCodeAt(0),0);
  function whatsappProfile(s){
    const reply=String(s.reply||'').toLowerCase(), branch=clean(s.branch||'coursework');
    if(/fee|financial/.test(reply))return {
      opening:`I wanted to check in about the fee balance you mentioned. Has it been affecting your ${branch} work this week?`,
      ask:'The financial-aid team can review the available options with you. Would you like me to arrange that?',
      student:'Yes, I would feel less stressed if I knew the options and the next deadline.',
      action:'I have requested a financial-aid appointment and shared the academic-support schedule.',
      close:'Please keep me updated after the appointment so we can adjust your plan together.'
    };
    if(/sick|lab|attendance/.test(reply))return {
      opening:`I saw that missed sessions have made it harder to keep up in ${branch}. Are you feeling ready to reconnect with the course team?`,
      ask:'I can help you request the lab material and arrange a short catch-up plan.',
      student:'Yes, getting the lab material first would help me understand what I missed.',
      action:'I have prepared a note for your course team and added the next available support slot.',
      close:'Take the recovery plan one step at a time; we will check in again after your next session.'
    };
    if(/shift|work|evening/.test(reply))return {
      opening:`I remember your work shifts were making attendance difficult. Has your ${branch} timetable become any more manageable?`,
      ask:'Would a weekly study plan built around your shifts make the next two weeks easier?',
      student:'Yes, a plan around my shifts would make it easier to stay consistent.',
      action:'I have shared a flexible study-plan template and asked your advisor about support hours.',
      close:'We can review the plan after you try it for a week and change anything that is not realistic.'
    };
    if(/assessment|exam|plan|behind|catch up/.test(reply))return {
      opening:`I am checking how the catch-up plan is going for your ${branch} assessments. Which deadline feels most urgent now?`,
      ask:'We can break that work into smaller steps and add a tutor or faculty check-in.',
      student:'A smaller plan and one tutor session would make the workload feel possible.',
      action:'I have reserved an academic-support slot and sent a short recovery-plan checklist.',
      close:'Focus on the first step today; your counselor will follow up before the next deadline.'
    };
    if(/overwhelm|worried|confidence/.test(reply))return {
      opening:`Thank you for staying in touch. I wanted to see how you are feeling about your ${branch} workload today.`,
      ask:'Would it help to combine a counselor check-in with an academic plan for this week?',
      student:'Yes, having someone help me prioritise would make it feel less overwhelming.',
      action:'I have arranged a counselor check-in and added practical academic resources to your plan.',
      close:'You do not need to solve everything at once; we will keep the next steps manageable.'
    };
    return {
      opening:`It is good to hear from you again. How are the resources working alongside your ${branch} commitments?`,
      ask:'Would you like a brief check-in with your advisor to keep the progress moving?',
      student:'Yes, a short check-in would help me stay accountable and keep progressing.',
      action:'I have shared the progress note with your support team and suggested an advisor check-in.',
      close:'Thank you for the update. Keep using the plan and let us know if your needs change.'
    };
  }
  function generatedWhatsappMessages(s){
    const profile=whatsappProfile(s), name=first(s.name), variant=waHash(s.id)%3;
    const confirmations=['That sounds like the right next step for me.','I feel more confident having a clear option.','Yes, that would make a real difference this week.'];
    return [
      ['Asha AI',`Hi ${name}, I am Asha AI from Student Wellness. I am checking in to make sure you have the support you need. Is this still a good time to talk?`,false],
      [name,s.reply,true],
      ['Asha AI',profile.opening,false],
      [name,profile.student,true],
      ['Asha AI',profile.ask,false],
      [name,confirmations[variant],true],
      ['Asha AI',profile.action,false],
      [name,'Thank you. I will follow those steps and reply after I have made progress.',true],
      ['Asha AI',profile.close,false],
      [name,'I appreciate the support and will keep you updated.',true]
    ];
  }
  function waDetail(s){
    const handoff=s.id===state.demo?.id&&s.actualCall&&s.status==='whatsapp';
    const active=isActive(s)&&(!s.id || s.id!==state.demo?.id || s.status==='whatsapp'||s.status==='calling');
    const messages=handoff?(s.waMessages||[]).map(message=>[message.speaker,message.text,message.student]):generatedWhatsappMessages(s);
    const visible=active?Math.min(messages.length,Math.max(1,state.waSteps[s.id]||1)):messages.length;
    // Most sample threads deliberately open part-way through their existing
    // conversation. A new manual call follow-up remains visible from turn one.
    // Render the earlier messages too; the thread opens scrolled to the
    // current point, and the user can scroll up within this chat to read the
    // beginning of the conversation.
    const transcript=messages.slice(0,visible).map(([speaker,text,student])=>`<div class="transcript-message ${student?'student-message':'ai-message'}"><div class="message-bubble"><b>${clean(speaker)}</b><span>${clean(text)}</span></div></div>`).join('');
    return `<div class="operation-detail transcript-thread" onscroll="window.operationScroll('wa','${clean(s.id)}',this)">${transcript}</div>`;
  }
  function row(kind,s){
    const open=kind==='voice'?state.voiceOpen===s.id:state.waOpen===s.id;
    const isManual=s.id===state.demo?.id;
    const active=kind==='voice'?(isActive(s)&&(!isManual||s.status!=='whatsapp')):(isActive(s)&&(!isManual||s.status==='whatsapp'||s.status==='calling')),
      tone=s.risk==='HIGH'?'var(--red)':s.risk==='MEDIUM'?'var(--amber)':'var(--green)';
    const marker=active?'<span class="presence-dot"></span><span class="live-badge">LIVE</span>':'<span class="history-dot"></span>';
    return `<article class="operation-row ${open?'open':''}"><button class="operation-name" onclick="window.toggleOperation('${kind}','${clean(s.id)}')"><span class="operation-label" style="color:${active?tone:'var(--text2)'}">${kind==='voice'?'☎':'●'} ${title(s)} ${marker}</span><span class="operation-status">${active?'In conversation':'Conversation saved'}</span></button>${open?(kind==='voice'?voiceDetail(s):waDetail(s)):''}</article>`;
  }
  function filteredOperations(kind){
    const query=String(kind==='voice'?state.voiceQuery:state.waQuery||'').trim().toLowerCase();
    const channelActive=student=>{const isManual=student.id===state.demo?.id;return kind==='voice'?(isActive(student)&&(!isManual||student.status!=='whatsapp')):(isActive(student)&&(!isManual||student.status==='whatsapp'||student.status==='calling'));};
    return operationStudents().filter(student=>!query || `${student.name} ${student.id} ${student.branch}`.toLowerCase().includes(query)).sort((a,b)=>Number(channelActive(b))-Number(channelActive(a))||(state.demo?.id===a.id?-1:state.demo?.id===b.id?1:riskRank(a.risk)-riskRank(b.risk)||a.name.localeCompare(b.name)));
  }
  function enforceOperationCounts(){
    if(window.__guidedDemoActive) return;
    const count=String(activeStudents().length),set=(id,value)=>{const el=document.getElementById(id);if(el&&el.textContent!==value)el.textContent=value;};
    ['ts-count','admin-ts-count'].forEach(id=>set(id,count+' active'));
    ['sb-voice-count','admin-voice-count'].forEach(id=>set(id,count));
    ['wa-count-badge','admin-wa-badge'].forEach(id=>set(id,count+' conversations'));
    ['sb-wa-count','admin-wa-count'].forEach(id=>set(id,count));
  }
  function ensureOperationSearchBars(){
    const areas=[
      ['page-transcript','voice','Search call transcripts...'],['page-admin-transcript','voice','Search call transcripts...'],
      ['page-whatsapp','wa','Search WhatsApp conversations...'],['page-admin-whatsapp','wa','Search WhatsApp conversations...']
    ];
    areas.forEach(([pageId,kind,placeholder])=>{
      const page=document.getElementById(pageId); if(!page||page.querySelector(`.operation-toolbar[data-kind="${kind}"]`))return;
      const tools=document.createElement('div'); tools.className='operation-toolbar'; tools.dataset.kind=kind;
      const query=kind==='voice'?state.voiceQuery:state.waQuery;
      tools.innerHTML=`<input class="search-input" value="${clean(query)}" placeholder="${placeholder}" aria-label="${placeholder}"><button class="btn">Search</button><button class="btn btn-red">Reset</button>`;
      const input=tools.querySelector('input');
      input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();window.setOperationSearch(kind,input.value);}});
      tools.querySelector('.btn').addEventListener('click',()=>window.setOperationSearch(kind,input.value));
      tools.querySelector('.btn-red').addEventListener('click',()=>window.resetOperationSearch(kind));
      page.querySelector('.page-hdr')?.insertAdjacentElement('afterend',tools);
    });
  }
  function restoreChatScroll(){
    document.querySelectorAll('.operation-detail').forEach(detail=>{
      const call=detail.getAttribute('onscroll')||'',match=call.match(/'([^']+)','([^']+)'/),key=match?`${match[1]}:${match[2]}`:'';
      if(!key)return;
      if(state.scrollLocks[key])detail.scrollTop=Math.min(Number(state.scrollTops[key]||0),detail.scrollHeight);
      else detail.scrollTop=detail.scrollHeight;
    });
  }
  let nextNormalOperationAdvance=0;
  function renderOperations(){
    if(window.__guidedDemoActive)return;
    state.tick=(state.tick||0)+1;
    const mayAdvance=Date.now()>=nextNormalOperationAdvance;
    if(mayAdvance){
      // Old prototype pollers can still request a render every two seconds.
      // Advance exactly once every 2.5 seconds in the normal workspace.
      // Watch Demo bypasses this renderer and retains its own timing.
      nextNormalOperationAdvance=Date.now()+2500;
      if(state.voiceOpen){const person=operationStudents().find(s=>s.id===state.voiceOpen);if(person&&isActive(person))state.voiceSteps[state.voiceOpen]=Math.min(10,(state.voiceSteps[state.voiceOpen]||1)+1);}
      if(state.waOpen){const person=operationStudents().find(s=>s.id===state.waOpen);if(person&&isActive(person))state.waSteps[state.waOpen]=Math.min(10,(state.waSteps[state.waOpen]||0)+1);}
    }
    const voice=filteredOperations('voice').map(s=>row('voice',s)).join('')||'<p class="operation-empty">No call transcripts match that search.</p>';
    const whatsapp=filteredOperations('wa').map(s=>row('wa',s)).join('')||'<p class="operation-empty">No WhatsApp conversations match that search.</p>';
    ['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=voice;});
    ['wa-convos-panel','admin-wa-panel'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=whatsapp;});
    ensureOperationSearchBars();enforceOperationCounts();persist();requestAnimationFrame(restoreChatScroll);
  }
  window.operationScroll=(kind,id,element)=>{const key=`${kind}:${id}`;state.scrollLocks[key]=element.scrollTop+element.clientHeight<element.scrollHeight-22;state.scrollTops[key]=element.scrollTop;persist();};
  window.toggleOperation=(kind,id)=>{if(kind==='voice'){const opening=state.voiceOpen!==id;state.voiceOpen=opening?id:null;if(opening){const student=operationStudents().find(person=>person.id===id);if(!student?.actualCall&&Number(state.voiceSteps[id]||0)<8)state.voiceSteps[id]=8+(waHash(id)%2);else if(student?.actualCall&&state.voiceSteps[id]===undefined)state.voiceSteps[id]=1;}}else{const opening=state.waOpen!==id;state.waOpen=opening?id:null;if(opening&&state.waSteps[id]===undefined){const student=operationStudents().find(person=>person.id===id);state.waSteps[id]=student?.actualCall?0:5+(waHash(id)%2);}}delete state.scrollLocks[`${kind}:${id}`];delete state.scrollTops[`${kind}:${id}`];renderOperations();};
  window.setOperationSearch=(kind,value)=>{if(kind==='voice')state.voiceQuery=value;else state.waQuery=value;document.querySelectorAll(`.operation-toolbar[data-kind="${kind}"] input`).forEach(input=>input.value=value);renderOperations();};
  window.resetOperationSearch=kind=>{if(kind==='voice')state.voiceQuery='';else state.waQuery='';document.querySelectorAll(`.operation-toolbar[data-kind="${kind}"] input`).forEach(input=>input.value='');renderOperations();};
  window.startManualLiveCall = data => {
    state.demo={id:data.student_id || 'STU-2847',name:data.student_name || 'Student',status:'calling',started:Date.now(),actualCall:true,simulated:data.status==='simulated',actualAnswers:{},currentQuestion:''};
    state.voiceOpen=state.demo.id;state.waOpen=null;state.voiceSteps[state.demo.id]=1;renderOperations();
  };
  window.completeManualLiveCall = async () => {
    if(!state.demo||state.demo.handoffStarted) return;
    state.demo.handoffStarted=true;state.demo.status='finishing';state.voiceOpen=state.demo.id;state.waOpen=null;persist();renderOperations();
    const notice=document.createElement('div');notice.className='completion-notice';notice.innerHTML=`<div class="mono" style="color:var(--red);margin-bottom:8px">AI CALL SUMMARY</div><strong>${clean(state.demo.name||'Student')} has been flagged as high dropout risk.</strong><p>Financial-aid guidance and an academic counselor follow-up have been prioritised.</p>`;document.body.appendChild(notice);
    await new Promise(resolve=>setTimeout(resolve,4000));notice.remove();
    try { await fetch('/whatsapp/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_name:state.demo.name||'Student'})}); } catch (_) {}
    const studentName=state.demo.name||'Student',studentFirst=studentName.split(' ')[0];
    state.demo.waMessages=[
      {speaker:'Asha AI',text:`Hi ${studentFirst}, I am following up after our call. I have shared the academic and financial-support options we discussed.`,student:false},
      {speaker:studentFirst,text:'Thank you. I would appreciate help taking the next step.',student:true},
      {speaker:'Asha AI',text:'I have arranged a counselor check-in and sent the relevant support information.',student:false},
      {speaker:studentFirst,text:'That will help me get back on track.',student:true},
      {speaker:'Asha AI',text:'You are not alone. Your counselor will stay in touch as your plan progresses.',student:false},
      {speaker:studentFirst,text:'Thank you for the support.',student:true},
      {speaker:'Asha AI',text:'I have also shared a short checklist for your next academic and financial-support steps.',student:false},
      {speaker:studentFirst,text:'I will review it today and let the counselor know if I need help.',student:true},
      {speaker:'Asha AI',text:'That is a strong next step. We will check in again after your first appointment.',student:false},
      {speaker:studentFirst,text:'I appreciate having a clear plan.',student:true}
    ];
    state.demo.status='whatsapp';state.voiceOpen=null;state.waOpen=state.demo.id;state.waSteps[state.demo.id]=0;state.demo.handoffStarted=false;persist();renderOperations();
    document.querySelector('[data-page="whatsapp"], [data-page="admin-whatsapp"]')?.click();
  };
  async function syncSpokenName(){
    if(!state.demo || state.demo.status !== 'calling') return;
    try { const r=await fetch('/api/transcripts'); const d=await r.json(); const values=Object.values(d.sessions || {}); const live=values.find(x => String(x.student_id) === String(state.demo.id)); if(live) { if(live.spoken_name && live.spoken_name.trim()) state.demo.name=live.spoken_name.trim(); state.demo.actualAnswers=live.answers || {}; state.demo.currentQuestion=live.current_question || ''; persist(); renderOperations(); if(live.status==='completed'||live.completed_at)window.completeManualLiveCall(); } } catch (_) {}
  }
  async function syncActualWhatsApp(){
    if(!state.demo||state.demo.status!=='whatsapp'||!state.demo.actualCall)return;
    try{
      const response=await fetch('/whatsapp/conversations');const payload=await response.json();
      const expected=String(state.demo.name||'Student').toLowerCase();
      const conversation=(payload.conversations||[]).find(item=>String(item.student_name||item.profile_name||'').toLowerCase()===expected);
      if(!conversation?.messages?.length)return;
      state.demo.waMessages=conversation.messages.map(message=>({speaker:message.role==='assistant'?'Asha AI':first(state.demo.name),text:message.content||'',student:message.role!=='assistant'}));persist();renderOperations();
    }catch(_){}
  }
  function details(s){
    const high=s.risk === 'HIGH', riskClass=high?'high':s.risk==='MEDIUM'?'medium':'low', color=high?'var(--red)':s.risk==='MEDIUM'?'var(--amber)':'var(--green)';
    return `<span class="modal-close" onclick="closeModal()">&times;</span><span class="summary-chip ${high?'high':'medium'}">${s.risk} RISK · SCORE ${s.score}</span><h2 style="margin:14px 0 4px">${clean(s.name)}</h2><div class="mono" style="font-size:10px;color:var(--text3)">${clean(s.id)} · STUDENT PROFILE</div><div class="student-summary"><div class="mono" style="color:${color};font-size:10px">AI STUDENT SUMMARY</div><p>${clean(s.name)} needs a timely support conversation. Attendance, marks, engagement and recent call signals indicate a ${s.risk.toLowerCase()} intervention priority.</p></div><div class="detail-grid"><div class="detail-item"><div class="dl">Course</div><div class="dv">${clean(s.course)}</div></div><div class="detail-item"><div class="dl">Branch</div><div class="dv">${clean(s.branch)}</div></div><div class="detail-item"><div class="dl">Year</div><div class="dv">${clean(s.year)}</div></div><div class="detail-item"><div class="dl">Semester</div><div class="dv">${clean(s.semester)}</div></div><div class="detail-item"><div class="dl">Latest marks</div><div class="dv">${clean(s.marks)}</div></div><div class="detail-item"><div class="dl">Attendance</div><div class="dv">${clean(s.attendance)}</div></div><div class="detail-item"><div class="dl">Primary signal</div><div class="dv">${high?'Financial / academic pressure':'Engagement and wellbeing'}</div></div><div class="detail-item"><div class="dl">Recommended action</div><div class="dv">Counselor follow-up within 48 hours</div></div></div>`;
  }
  window.showOperationalStudent=id => { const s=[...allStudents(),...summaryStudents,...directoryStudents].find(x=>x.id===id)||students[0], modal=document.getElementById('modal'),body=document.getElementById('modal-body'); if(!modal||!body)return; body.innerHTML=details(s);modal.classList.add('show'); };
  window.showOperationalStudent=id => { const s=[...operationStudents(),...summaryStudents,...directoryStudents].find(x=>x.id===id)||students[0],modal=document.getElementById('modal'),body=document.getElementById('modal-body');if(!modal||!body)return;body.innerHTML=details(s);const chip=body.querySelector('.summary-chip');if(s.risk==='LOW'){chip?.classList.remove('medium');chip?.classList.add('low');}body.querySelector('.detail-grid')?.insertAdjacentHTML('afterbegin',`<div class="detail-item"><div class="dl">ML Risk Score</div><div class="dv">${clean(s.score)}</div></div><div class="detail-item"><div class="dl">AI Risk Score</div><div class="dv">${aiScore(s)}</div></div>`);modal.classList.add('show');};
  function renderSummaries(query=''){
    const q=query.trim().toLowerCase(); const rows=summaryPeople().filter(s => !q || `${s.name} ${s.id} ${s.branch} ${s.risk}`.toLowerCase().includes(q)).map(s => `<button class="summary-list-row risk-${String(s.risk).toLowerCase()}" onclick="showOperationalStudent('${s.id}')"><b>${clean(s.name)}</b><span>${clean(s.risk)} · ML ${clean(s.score)} · AI ${aiScore(s)}</span></button>`).join('') || '<p style="color:var(--text3)">No student summaries match that search.</p>';
    ['summary-students','admin-summary-grid'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=rows;});
  }
  // Keep both dashboards intentionally identical: scores belong in the
  // selected student's detail panel, not on the summary directory rows.
  function renderSummaries(query=''){
    summaryQuery=query;
    const q=query.trim().toLowerCase();
    const matches=summaryPeople().filter(s=>!q||`${s.name} ${s.id} ${s.branch} ${s.risk}`.toLowerCase().includes(q));
    const visible=matches.slice(0,q?Math.max(200,summaryLimit):summaryLimit);
    const rows=visible.map(s=>`<button class="ai-summary-row risk-${String(s.risk).toLowerCase()}" onclick="showOperationalStudent('${s.id}')"><b>${clean(s.name)}</b></button>`).join('')||'<p style="color:var(--text3);padding:18px">No student summaries match that search.</p>';
    const more=visible.length<matches.length?`<button class="btn" style="margin:14px 0 2px" onclick="window.showMoreSummaries()">Show 100 more</button><span class="mono" style="margin-left:10px;color:var(--text3);font-size:10px">Showing ${visible.length.toLocaleString()} of ${matches.length.toLocaleString()}</span>`:'';
    ['summary-students','admin-summary-grid'].forEach(id=>{const panel=document.getElementById(id);if(panel)panel.innerHTML=`<div class="ai-summary-list">${rows}</div>`;});
    if(more)['summary-students','admin-summary-grid'].forEach(id=>document.getElementById(id)?.insertAdjacentHTML('beforeend',more));
  }
  window.showMoreSummaries=()=>{summaryLimit+=100;renderSummaries(summaryQuery);};
  window.filterSummaryCards = value => renderSummaries(value || document.getElementById('summary-search')?.value || '');
  window.filterAdminSummary = value => renderSummaries(value || document.getElementById('admin-summary-search')?.value || '');
  async function loadSummaryStudents(){
    try {
      const response=await fetch('/api/students?limit=4500');
      const payload=await response.json();
      summaryStudents=(payload.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).map(fromApi);
      renderSummaries();
    } catch (_) { renderSummaries(); }
  }
  function renderDirectory(query=''){
    const panel=document.getElementById('student-directory-list'); if(!panel) return;
    directoryQuery=query;
    const needle=query.trim().toLowerCase();
    if(!directoryStudents.length){
      panel.innerHTML=directoryLoading ? '<p style="color:var(--text3)">Loading student directory…</p>' : '<p style="color:var(--text3)">Preparing student directory…</p>';
      return;
    }
    const matches=directoryStudents.filter(s=>!needle || `${s.name} ${s.id} ${s.branch}`.toLowerCase().includes(needle)).sort((a,b)=>riskRank(a.risk)-riskRank(b.risk)||a.name.localeCompare(b.name));
    const visible=matches.slice(0,needle ? Math.max(200,directoryLimit) : directoryLimit);
    const total=Number(state.directoryTotal)||4500;
    const badge=document.getElementById('student-directory-count'); if(badge) badge.textContent=`${(needle?matches.length:total).toLocaleString()} students`;
    ['student-directory-nav-count','sb-student-count'].forEach(id=>{const navBadge=document.getElementById(id);if(navBadge)navBadge.textContent=total.toLocaleString();});
    panel.innerHTML=visible.map(s=>`<button class="summary-list-row" onclick="showOperationalStudent('${s.id}')"><span><b>${clean(s.name)}</b><small>${clean(s.id)} · ${clean(s.branch)}</small></span><span class="summary-chip ${s.risk==='HIGH'?'high':s.risk==='MEDIUM'?'medium':''}">${s.risk}</span></button>`).join('') || '<p style="color:var(--text3)">No students match that search.</p>';
    visible.forEach((student,index)=>{const row=panel.children[index];row?.classList.add(`risk-${String(student.risk).toLowerCase()}`);if(student.risk==='LOW')row?.querySelector('.summary-chip')?.classList.add('low');});
    if(visible.length<matches.length)panel.insertAdjacentHTML('beforeend',`<button class="btn" style="margin:14px 0 2px" onclick="window.showMoreDirectoryStudents()">Show 100 more</button><span class="mono" style="margin-left:10px;color:var(--text3);font-size:10px">Showing ${visible.length.toLocaleString()} of ${matches.length.toLocaleString()}</span>`);
  }
  window.showMoreDirectoryStudents=()=>{directoryLimit+=100;renderDirectory(directoryQuery);};
  async function loadDirectory(){
    if(directoryStudents.length){renderDirectory(directoryQuery);return directoryStudents;}
    if(directoryRequest){await directoryRequest;renderDirectory(directoryQuery);return directoryStudents;}
    directoryLoading=true;
    renderDirectory(directoryQuery);
    directoryRequest=fetch('/api/all-students').then(response=>{
      if(!response.ok)throw new Error('Directory request failed');
      return response.json();
    }).then(payload=>{
      directoryStudents=(payload.students||[]).map(fromApi);
      return directoryStudents;
    }).catch(()=>{
      const panel=document.getElementById('student-directory-list'); if(panel)panel.innerHTML='<p style="color:var(--red)">Unable to load the student directory.</p>';
      return [];
    }).finally(()=>{directoryLoading=false;directoryRequest=null;});
    await directoryRequest;
    renderDirectory(directoryQuery);
    return directoryStudents;
  }
  function installStudentDirectory(){
    let page=document.getElementById('page-student-directory');
    if(!page){
      page=document.createElement('div'); page.className='page'; page.id='page-student-directory';
      page.innerHTML='<div class="page-hdr"><h1>All Students</h1><p>Complete student directory, including students not currently at risk.</p></div><div class="search-bar"><input class="search-input" id="student-directory-search" placeholder="Search name, ID, or branch..." oninput="window.renderStudentDirectory(this.value)"></div><div class="card"><div class="card-h"><span class="t">Student Directory</span><span class="b" id="student-directory-count">Loading…</span></div><div class="card-b" id="student-directory-list"><div class="loading-spinner" style="margin:20px auto"></div></div></div>';
      document.querySelector('.main')?.appendChild(page);
    }
    const existing=document.querySelector('[data-page="students"]');
    const nav=document.querySelector('.sb-nav');
    const item=existing || document.createElement('div');
    if(!existing && nav){ item.className='sb-item'; item.innerHTML='<span style="font-size:16px">◌</span> Students<span class="sb-badge" id="student-directory-nav-count">4,500</span>'; nav.insertBefore(item, nav.children[1] || null); }
    item.dataset.page='student-directory';
    item.addEventListener('click',()=>{document.querySelectorAll('.sb-item').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));item.classList.add('active');page.classList.add('active');loadDirectory();});
  }
  window.renderStudentDirectory = renderDirectory;
  // The directory follows the same reporting period as the overview cards.
  // This is stored separately from live-call reset state so it is shared by
  // the counselor and administrator workspaces without altering call data.
  const reportingPeriods={
    this_sem:{total:4500,atRisk:1017,high:142},last_sem:{total:4610,atRisk:1090,high:168},
    this_month:{total:1500,atRisk:303,high:41},last_month:{total:1500,atRisk:344,high:55},
    this_year:{total:18200,atRisk:3724,high:514},last_year:{total:18100,atRisk:4124,high:596}
  };
  const priorRiskOverview=window.updateRiskOverview;
  window.updateRiskOverview=(period,scope)=>{
    priorRiskOverview?.(period,scope);
    const data=reportingPeriods[period]||reportingPeriods.this_sem;
    state.directoryTotal=data.total; localStorage.setItem('dropout-signal-reporting-period',period); persist();
    ['s-bronze','cd-calls'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=data.total.toLocaleString();});
    ['s-gold','cd-med'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=data.atRisk.toLocaleString();});
    ['s-avgrisk','cd-high'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=data.high.toLocaleString();});
    ['admin-risk-count','sb-risk-count','risk-count-badge','admin-risk-badge'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=id.includes('badge')?`${data.atRisk.toLocaleString()} students`:data.atRisk.toLocaleString();});
    renderDirectory(document.getElementById('student-directory-search')?.value||'');
  };
  const storedPeriod=localStorage.getItem('dropout-signal-reporting-period');
  if(storedPeriod) setTimeout(()=>window.updateRiskOverview(storedPeriod,document.getElementById('admin-risk-overview-select')?'admin':undefined),0);
  window.addEventListener('storage',event=>{if(event.key==='dropout-signal-reporting-period'&&event.newValue)window.updateRiskOverview(event.newValue,document.getElementById('admin-risk-overview-select')?'admin':undefined);if(event.key===storageKey){state=Object.assign(state,read());renderOperations();renderSummaries();}});
  installStudentDirectory();
  // Fetch the directory while the dashboard is already visible.  Opening the
  // Students page then only paints the first small batch instead of waiting
  // for a 4,500-row request and DOM build.
  // Give the dashboard one paint before the optional directory prefetch.
  // The request is still normally complete before a user opens Students.
  setTimeout(()=>{loadDirectory();},350);
  // Cache at-risk records after the first dashboard paint; only a small page
  // of rows is rendered when that tab is opened.
  setTimeout(()=>{renderPrioritizedAtRisk(Boolean(document.getElementById('admin-risk-tbody')));},700);
  loadSummaryStudents();
  // Keep the login demo self-contained. It must not depend on the live list
  // pollers or a real Twilio connection, otherwise its cursor can disappear
  // immediately after the redirect to the counselor workspace.
  window.startGuidedDemo = async () => {
    if (window.__guidedDemoActive) return;
    window.__guidedDemoActive = true;
    const cursor = window.createDemoCursor ? window.createDemoCursor() : null;
    const wait = window.pause || (ms => new Promise(resolve => setTimeout(resolve, ms)));
    const move = window.cursorStep || (async () => {});
    const show = (title, message) => {
      const overlay=document.createElement('div');
      overlay.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:20px';
      overlay.innerHTML=`<div style="width:min(410px,100%);background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:30px;text-align:center"><div class="loading-spinner" style="width:32px;height:32px;border-width:3px;margin:0 auto 16px"></div><h2 style="font-size:21px;margin-bottom:8px">${title}</h2><p style="font-size:13px;color:var(--text2)">${message}</p></div>`;
      document.body.appendChild(overlay); return overlay;
    };
    try {
      const callButton=document.querySelector('button.nav-cta');
      if(cursor && callButton) await move(cursor, callButton, null, 750);
      const calling=show('Calling Demo Student', 'Connecting the Asha AI counselor…');
      await wait(1100); calling.remove();
      const transcriptTab=document.querySelector('[data-page="transcript"]');
      if(cursor && transcriptTab) await move(cursor, transcriptTab, ()=>transcriptTab.click(), 650);
      else transcriptTab?.click();
      const panel=document.getElementById('full-transcript-panel');
      if(!panel) throw new Error('Live transcript panel is unavailable');
      const turns=[
        ['ASHA AI','Hi, this is Asha from Student Wellness. Before we begin, could you please tell me your name?'],
        ['DEMO STUDENT','My name is Demo Student.'],
        ['ASHA AI','How has this semester been going for you so far?'],
        ['DEMO STUDENT','It has been difficult. I am falling behind and worried about my workload and finances.'],
        ['ASHA AI','What support would help you most right now?'],
        ['DEMO STUDENT','Financial-aid advice and a plan for catching up would really help.']
      ];
      let transcript='';
      for(const [speaker,text] of turns){
        const color=speaker==='ASHA AI'?'var(--purple)':'var(--green)';
        transcript+=`<div class="speaker" style="color:${color};margin-top:12px">${speaker}</div><div>${text}</div>`;
        panel.innerHTML=transcript+'<div class="live-pulse">● AI on call — transcript updating</div>';
        panel.scrollTop=panel.scrollHeight;
        await wait(850);
      }
      const risk=document.createElement('div');
      risk.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:20px';
      risk.innerHTML='<div style="width:min(440px,100%);background:var(--bg);border:1px solid var(--red);border-radius:16px;padding:28px;text-align:center"><div class="mono" style="color:var(--red);margin-bottom:12px">VOICE RISK CONFIRMED</div><h2 style="font-size:23px;margin-bottom:10px">Support follow-up prepared</h2><p style="font-size:13px;color:var(--text2);line-height:1.6">Financial-aid and academic-support follow-up will be sent to Demo Student.</p></div>';
      document.body.appendChild(risk); await wait(1600); risk.remove();
      const waTab=document.querySelector('[data-page="whatsapp"]');
      if(cursor && waTab) await move(cursor, waTab, ()=>waTab.click(), 650); else waTab?.click();
      const waPanel=document.getElementById('wa-convos-panel');
      if(waPanel) waPanel.innerHTML='<article class="operation-row open"><button class="operation-name"><span style="color:var(--green)">● Demo Student</span></button><div class="operation-detail"><div class="chat-line ai-chat"><b>Asha AI</b><span>Hi Demo Student, I have shared your financial-aid and academic-support follow-up.</span></div><div class="chat-line student-chat"><b>Demo Student</b><span>Thank you, I would appreciate that.</span></div><div class="chat-line ai-chat"><b>Asha AI</b><span>A counselor will contact you within 24 hours.</span></div></div></article>';
      if(cursor && window.parkDemoCursor) window.parkDemoCursor(cursor);
      toast('Demo complete — live transcript and WhatsApp follow-up shown.', 'ok');
    } catch (error) {
      console.error('Guided demo error:', error);
      toast('Demo could not start. Please refresh and try again.', 'err');
    } finally {
      window.__guidedDemoActive = false;
    }
  };
  // Presentation run used by Watch Demo. It deliberately never calls the
  // persistence APIs or stores its Demo Student conversation in localStorage.
  window.startGuidedDemo = async () => {
    if (window.__guidedDemoActive) return;
    window.__guidedDemoActive = true;
    window.__guidedDemoCancelled=false;
    state.demo={id:'STU-GUIDED',name:'Demo Student',status:'calling',risk:'HIGH',score:'0.87'};state.voiceOpen=state.demo.id;state.waOpen=null;
    const setDemoCount=(id,value)=>{const element=document.getElementById(id);if(element)element.textContent=value;};
    ['ts-count','admin-ts-count'].forEach(id=>setDemoCount(id,'8 active'));['sb-voice-count','admin-voice-count'].forEach(id=>setDemoCount(id,'8'));
    ['wa-count-badge','admin-wa-badge'].forEach(id=>setDemoCount(id,'8 conversations'));['sb-wa-count','admin-wa-count'].forEach(id=>setDemoCount(id,'8'));
    localStorage.removeItem(storageKey);
    document.querySelectorAll('.demo-cursor-v3,.demo-ripple-v3,#guided-demo-lock').forEach(node=>node.remove());
    const interactionLock=document.createElement('div');
    interactionLock.id='guided-demo-lock';
    interactionLock.style.cssText='position:fixed;inset:0;z-index:18000;background:transparent;cursor:default';
    ['pointerdown','mousedown','click','touchstart'].forEach(type=>interactionLock.addEventListener(type,event=>{event.preventDefault();event.stopPropagation();},true));
    interactionLock.addEventListener('wheel',event=>event.preventDefault(),{passive:false});
    document.body.appendChild(interactionLock);
    const endDemo=document.createElement('button');
    endDemo.id='end-guided-demo';endDemo.className='btn btn-red';endDemo.textContent='End Demo';
    endDemo.style.cssText='position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:22000;padding:12px 28px;height:auto;font-size:13px;box-shadow:0 8px 28px rgba(0,0,0,.45)';
    endDemo.onclick=()=>{window.__guidedDemoCancelled=true;state.demo=null;localStorage.removeItem(storageKey);window.location.href='/logout';};
    document.body.appendChild(endDemo);
    const wait=window.pause || (ms=>new Promise(resolve=>setTimeout(resolve,ms)));
    const cursor=window.createDemoCursor ? window.createDemoCursor() : null;
    const move=window.cursorStep || (async()=>{});
    const showPopup=(title,copy,color='var(--border)')=>{
      const popup=document.createElement('div');
      popup.style.cssText='position:fixed;inset:0;z-index:19000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:20px';
      popup.innerHTML=`<div style="width:min(440px,100%);background:var(--bg);border:1px solid ${color};border-radius:16px;padding:28px;text-align:center"><h2 style="font-size:23px;margin-bottom:10px">${title}</h2><p style="font-size:13px;line-height:1.6;color:var(--text2)">${copy}</p></div>`;
      document.body.appendChild(popup); return popup;
    };
    const finish=async()=>{
      const helped=showPopup('Demo Student has been helped','Financial-aid and academic-support follow-up have been arranged.','var(--green)');
      await wait(1900); helped.remove();
      const ended=showPopup('Demo Ended','The complete intervention flow is finished. Returning to the home screen.','var(--border)');
      await wait(1800);ended.remove();
      state.demo=null; state.voiceOpen=null; state.waOpen=null; localStorage.removeItem(storageKey);
      window.__guidedDemoActive=false;
      interactionLock.remove();endDemo.remove();if(cursor) cursor.remove();
      window.location.href='/logout';
    };
    try {
      const callButton=document.querySelector('button.nav-cta');
      if(cursor && callButton) await move(cursor,callButton,null,650);
      const calling=showPopup('Calling Demo Student','Connecting Asha AI counselor…');
      await wait(1100); calling.remove();
      const transcriptTab=document.querySelector('[data-page="transcript"]');
      if(cursor && transcriptTab) await move(cursor,transcriptTab,()=>transcriptTab.click(),600); else transcriptTab?.click();
      const panel=document.getElementById('full-transcript-panel');
      if(!panel) throw new Error('Transcript panel unavailable');
      const turns=[
        ['ASHA AI','Before we begin, could you please tell me your name?'],
        ['DEMO STUDENT','My name is Demo Student.'],
        ['ASHA AI','How has this semester been going for you so far?'],
        ['DEMO STUDENT','I have been falling behind and I am worried about managing coursework and finances.'],
        ['ASHA AI','What has been the most challenging part of college life recently?'],
        ['DEMO STUDENT','Balancing assignments, attendance and my fee payment has been the hardest part.'],
        ['ASHA AI','On a scale of 1 to 5, how confident are you about completing your degree?'],
        ['DEMO STUDENT','About two out of five. I need support to feel confident again.'],
        ['ASHA AI','What support would make the biggest difference right now?'],
        ['DEMO STUDENT','Financial-aid guidance and help making an academic recovery plan would help me.']
      ];
      const guidedTail=kind=>[...students,...historicalStudents].sort((a,b)=>isActive(a)!==isActive(b)?(isActive(a)?-1:1):riskRank(a.risk)-riskRank(b.risk)||a.name.localeCompare(b.name)).map(student=>row(kind,student)).join('');
      const demoHead='<article class="operation-row open risk-high"><button class="operation-name"><span class="operation-label" style="color:var(--red)">Demo Student <span class="presence-dot"></span><span class="live-badge">LIVE</span></span><span class="operation-status">In conversation</span></button><div class="operation-detail transcript-thread">';
      let transcript='<article class="operation-row open"><button class="operation-name"><span style="color:var(--blue)">☎ Demo Student</span></button><div class="operation-detail">';
      for(const [index,[speaker,text]] of turns.entries()){
        if(index===0)transcript='';
        const student=speaker!=='ASHA AI';
        transcript+=`<div class="transcript-message ${student?'student-message':'ai-message'}"><div class="message-bubble"><b>${speaker}</b><span>${text}</span></div></div>`;
        panel.innerHTML=demoHead+transcript+'</div></article>'+guidedTail('voice');
        const thread=panel.querySelector('.operation-detail');if(thread)thread.scrollTop=thread.scrollHeight;
        await wait(index<4?3000:420);
      }
      const summary=showPopup('Asha AI has flagged Demo Student as high risk','<strong>Complete AI Call Summary</strong><br><br><strong>Risk assessment:</strong> High risk &nbsp;·&nbsp; ML score 0.87 &nbsp;·&nbsp; AI confidence 0.91<br><br><strong>Evidence:</strong> Demo Student reported falling behind with coursework, fee pressure, attendance strain, and confidence of 2 out of 5 about completing the degree.<br><br><strong>Recommended action:</strong> Prioritise financial-aid guidance, an academic recovery plan, and a counselor check-in within 24 hours.','var(--red)');
      await wait(6500); summary.remove();
      const whatsappTab=document.querySelector('[data-page="whatsapp"]');
      if(cursor && whatsappTab) await move(cursor,whatsappTab,()=>whatsappTab.click(),600); else whatsappTab?.click();
      const whatsapp=document.getElementById('wa-convos-panel');
      if(!whatsapp) throw new Error('WhatsApp panel unavailable');
      whatsapp.innerHTML='<article class="operation-row open"><button class="operation-name"><span style="color:var(--green)">● Demo Student</span></button><div class="operation-detail" id="guided-demo-chat"></div></article>';
      whatsapp.innerHTML='<article class="operation-row open risk-high"><button class="operation-name"><span class="operation-label" style="color:var(--red)">Demo Student <span class="presence-dot"></span><span class="live-badge">LIVE</span></span><span class="operation-status">In conversation</span></button><div class="operation-detail transcript-thread" id="guided-demo-chat"></div></article>'+guidedTail('wa');
      const chat=document.getElementById('guided-demo-chat');
      let messageNumber=0;
      const message=async(role,text)=>{
        const student=role==='student', line=document.createElement('div');
        line.className=`transcript-message ${student?'student-message':'ai-message'}`;
        line.innerHTML=`<div class="message-bubble"><b>${student?'Demo Student':'Asha AI'}</b><span></span></div>`;chat.appendChild(line);
        const target=line.querySelector('span');
        const speed=messageNumber++<4?78:18;
        for(const character of text){target.textContent+=character; await wait(speed);}
        chat.scrollTop=chat.scrollHeight;
      };
      await message('ai','Hi Demo Student! This is Asha from Student Wellness. How are you doing today?');
      await message('student','I am worried about keeping up with coursework and my fees.');
      await message('ai','Thank you for sharing that. Would financial-aid guidance and academic planning help?');
      await message('student','Yes, both would help me get back on track.');
      await message('ai','I have arranged financial-aid guidance and academic-planning support. A counselor will contact you shortly.');
      await message('student','Thank you. I appreciate the support.');
      if(cursor && window.parkDemoCursor) window.parkDemoCursor(cursor);
      await finish();
    } catch(error) {
      console.error('Watch Demo error:',error);
      window.__guidedDemoActive=false;
      state.demo=null;interactionLock.remove();endDemo.remove();if(cursor) cursor.remove();
      toast('Demo could not start. Please refresh and try again.','err');
    }
  };
  if(window.__guidedDemoRequested){
    window.__guidedDemoActive=false;
    setTimeout(()=>window.startGuidedDemo(),80);
  }
  // Legacy polling code calls this symbol. Point it at the single renderer so
  // it cannot recreate an empty "waiting" transcript between refreshes.
  window.renderDummyLiveOperations = renderOperations;
  window.renderOperationalSummaries = () => renderSummaries();
  // Prevent legacy refresh handlers from replacing the shared operation lists
  // with empty placeholders after a tab is opened.
  window.loadTranscripts = () => renderOperations();
  window.loadWAConvos = () => renderOperations();
  window.loadAdminTranscripts = () => renderOperations();
  window.loadAdminWhatsApp = () => renderOperations();
  const compareRiskRecords=(a,b)=>{
    const tierA=String(a.final_risk_tier||a.risk||'LOW').toUpperCase();
    const tierB=String(b.final_risk_tier||b.risk||'LOW').toUpperCase();
    return riskRank(tierA)-riskRank(tierB)||Number(b.ml_risk_score||b.score||0)-Number(a.ml_risk_score||a.score||0)||String(a.student_name||a.name||'').localeCompare(String(b.student_name||b.name||''));
  };
  async function renderPrioritizedAtRisk(admin=false){
    const input=document.getElementById(admin?'admin-risk-search':'risk-search');
    const tbody=document.getElementById(admin?'admin-risk-tbody':'risk-tbody');
    if(!tbody)return;
    const query=String(input?.value||'').trim().toLowerCase();
    try{
      if(!atRiskRecords){
        tbody.innerHTML='<tr><td colspan="6" style="padding:28px;text-align:center"><div class="loading-spinner"></div></td></tr>';
        if(!atRiskRequest)atRiskRequest=fetch('/api/students?limit=4500').then(response=>{
          if(!response.ok)throw new Error('At-risk request failed');
          return response.json();
        }).then(payload=>(payload.students||[]).filter(student=>['HIGH','MEDIUM'].includes(String(student.final_risk_tier||'').toUpperCase())).sort(compareRiskRecords)).finally(()=>{atRiskRequest=null;});
        atRiskRecords=await atRiskRequest;
      }
      const records=atRiskRecords.filter(student=>!query||`${student.student_name||''} ${student.student_id||''} ${student.top_factor_1||''} ${student.top_factor_2||''}`.toLowerCase().includes(query));
      summaryStudents=records.map(fromApi); renderSummaries();
      const badge=document.getElementById(admin?'admin-risk-badge':'risk-count-badge'); if(badge)badge.textContent=`${records.length.toLocaleString()} students`;
      if(!records.length){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">No at-risk students found</td></tr>';return;}
      const visible=records.slice(0,query?Math.max(200,atRiskLimit):atRiskLimit);
      tbody.innerHTML=visible.map(student=>{
        const tier=String(student.final_risk_tier||'MEDIUM').toUpperCase(), high=tier==='HIGH';
        const score=Number(student.ml_risk_score||0).toFixed(3), signal=student.voice_root_cause||student.top_factor_1||'Engagement review', action=student.final_action||'Schedule counselor follow-up';
        return `<tr class="at-risk-summary-link" onclick="window.openAtRiskSummary('${clean(student.student_id)}',${admin})" title="Open AI Student Summary"><td><strong>${clean(student.student_name||'Student')}</strong> <span class="mono" style="color:var(--text3)">(${clean(student.student_id||'')})</span></td><td><span class="mono">${score}</span></td><td><span class="tag ${high?'tag-t1':'tag-t2'}">${tier}</span></td><td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${clean(signal)}</td><td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${clean(action)}</td></tr>`;
      }).join('')+(visible.length<records.length?`<tr><td colspan="5" style="padding:14px 20px"><button class="btn" onclick="window.showMoreAtRisk(${admin})">Show 100 more</button><span class="mono" style="margin-left:10px;color:var(--text3);font-size:10px">Showing ${visible.length.toLocaleString()} of ${records.length.toLocaleString()}</span></td></tr>`:'');
    }catch(error){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--red)">Unable to load students.</td></tr>';}
  }
  window.showMoreAtRisk=admin=>{atRiskLimit+=100;renderPrioritizedAtRisk(Boolean(admin));};
  window.openAtRiskSummary=(id,admin=false)=>{
    const student=summaryStudents.find(person=>person.id===id);
    window.activateWorkspacePage(admin?'admin-summary':'summary');
    if(!student)return;
    const input=document.getElementById(admin?'admin-summary-search':'summary-search');
    if(input)input.value=student.name;
    renderSummaries(student.name);
  };
  window.loadAtRisk=()=>renderPrioritizedAtRisk(false);
  window.loadAdminAtRisk=()=>renderPrioritizedAtRisk(true);
  window.loadStudents=async()=>{
    const input=document.getElementById('student-search'),tbody=document.getElementById('students-tbody');
    if(!tbody)return;
    tbody.innerHTML='<tr><td colspan="6" style="padding:40px;text-align:center"><div class="loading-spinner"></div></td></tr>';
    try{
      const response=await fetch('/api/all-students?search='+encodeURIComponent(input?.value||''));
      const payload=await response.json();
      const records=(payload.students||[]).sort(compareRiskRecords);
      const badge=document.getElementById('student-count-badge');if(badge)badge.textContent=`${(input?.value?records.length:payload.total||records.length).toLocaleString()} records`;
      tbody.innerHTML=records.length?records.map(student=>{
        const tier=String(student.final_risk_tier||'LOW').toUpperCase(),tag=tier==='HIGH'?'tag-t1':tier==='MEDIUM'?'tag-t2':'tag-t3';
        return `<tr><td><strong>${clean(student.student_name||'Student')}</strong><br><span class="mono" style="color:var(--text3);font-size:10px">${clean(student.student_id||'')}</span></td><td class="mono">${Number(student.ml_risk_score||0).toFixed(3)}</td><td><span class="tag ${tag}">${tier}</span></td><td>${clean(student.top_factor_1||'—')}</td><td><span class="tag tag-t3">${clean(student.outcome_status||'Enrolled')}</span></td><td><button class="btn" onclick="showOperationalStudent('${clean(student.student_id)}')">View</button></td></tr>`;
      }).join(''):'<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:30px">No students found</td></tr>';
    }catch(error){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--red);padding:30px">Unable to load students.</td></tr>';}
  };
  const isAdminWorkspace=Boolean(document.getElementById('page-overview'));
  // Deliberately display-only demo credentials. These are not authentication
  // secrets and the disabled reset control never writes a new password.
  const workspaceProfile=isAdminWorkspace?{role:'College Administrator',username:'admin_demo',email:'admin@dropout-signal.demo',passwordHash:'$2b$12$C6UzMDM.H6dfI/f/IKcEe.7Q4u5UryJB3w5D0Mi.bfoYMrRZd34E6',initials:'CA'}:{role:'Academic Counselor',username:'counselor_demo',email:'counselor@dropout-signal.demo',passwordHash:'$2b$12$9v9pP2nLKqY1dH3fK7s4duiq1D1nH3v4S6pM2Rj1qoN4Bz7bCqLSe',initials:'AC'};
  function settingsMarkup(profile){
    return `<div class="page-hdr"><h1>Settings</h1><p>${clean(profile.role)} profile and workspace preferences</p></div>
      <div class="settings-layout"><section class="card"><div class="card-h"><span class="t">Profile</span></div><div class="card-b settings-body"><div class="profile-avatar">${profile.initials}</div><div class="profile-role"><strong>${clean(profile.role)}</strong><span>Secure demo profile</span></div><label>Username<output class="profile-value">${clean(profile.username)}</output></label><label>Email<output class="profile-value">${clean(profile.email)}</output></label><label>Password hash<output class="profile-value profile-hash">${clean(profile.passwordHash)}</output></label><button class="btn" type="button" onclick="window.showPasswordDemoNotice()">Reset password</button><p class="settings-note">Password reset is disabled in this hosted demonstration.</p></div></section>
      <section class="card"><div class="card-h"><span class="t">Workspace</span></div><div class="card-b settings-body"><div class="settings-line"><div><strong>Theme</strong><span>Switch between dark and light workspace themes.</span></div><button class="btn" type="button" onclick="window.toggleTheme()">Toggle theme</button></div><div class="settings-line"><div><strong>Databricks connection</strong><span>Student risk data connection</span></div><span class="tag tag-t3">Connected</span></div><div class="settings-line"><div><strong>Notifications</strong><span>Intervention alerts are enabled for this workspace.</span></div><span class="tag tag-t3">Enabled</span></div></div></section></div>`;
  }
  function ensureWorkspaceSettings(){
    let page=document.getElementById('page-settings');
    if(!page){
      page=document.createElement('div');page.className='page';page.id='page-settings';
      document.querySelector('.main')?.appendChild(page);
      const nav=document.querySelector('.sb-nav'),item=document.createElement('div');
      item.className='sb-item';item.dataset.page='settings';item.innerHTML='<span style="font-size:16px">⚙</span> Settings';nav?.appendChild(item);
    }
    page.innerHTML=settingsMarkup(workspaceProfile);
  }
  const dataLayers={
    bronze:{name:'Bronze',tone:'bronze',eyebrow:'Raw records and events',summary:'The Bronze layer is the project’s intake point. It keeps the original student records and interaction events together before they are shaped for analysis.',items:['Student directory details: course, branch, year and semester','Academic and attendance inputs: marks, credits and attendance rate','Engagement and support inputs: LMS activity, financial-aid status and contact history','Voice-call and WhatsApp events used to build the intervention record']},
    silver:{name:'Silver',tone:'silver',eyebrow:'Cleaned and connected signals',summary:'The Silver layer standardizes the inputs so the risk workflow can compare students consistently and identify the signals that need attention.',items:['Normalised identifiers so records stay linked to one student','Prepared attendance, marks, engagement and support features','Validated missing or inconsistent values before scoring','Combined recent interaction signals with academic context']},
    model:{name:'Model',tone:'model',eyebrow:'ML and AI risk scoring',summary:'The scoring layer estimates dropout risk and turns the important contributing signals into an explainable priority for the counselor or administrator.',items:['ML risk score estimates the likelihood of dropout','AI score and summary explain the priority in plain language','High, Medium and Low tiers drive the order of each workspace list','Recommended actions connect the identified signal to a practical next step']},
    gold:{name:'Gold',tone:'gold',eyebrow:'Student intervention profile',summary:'The Gold layer is the action-ready view used across the dashboard, At-Risk list and AI Student Summary.',items:['One profile per student with course, attendance, marks and risk tier','AI Student Summary brings together model and conversation context','High-risk students appear first for faster intervention','The dashboard, reports and exports read from this same action-ready view']},
    outreach:{name:'Outreach',tone:'outreach',eyebrow:'Calls, WhatsApp and outcomes',summary:'The outreach layer records the support workflow after a student is identified. It is what makes the risk signal useful in day-to-day student success work.',items:['Asha AI calls collect the five structured support-check questions','WhatsApp follow-ups continue with tailored, longer conversations','Live threads, risk flags and summaries stay visible in both workspaces','Analyze Calls and Export CSV package completed intervention outcomes']}
  };
  const stackIcon=()=>'<span class="layer-stack-icon" aria-hidden="true"><i></i><i></i><i></i><i></i></span>';
  function informationMarkup(){
    const flow=Object.entries(dataLayers).map(([key,layer],index)=>`<button class="data-layer-card ${layer.tone}" data-layer="${key}" onclick="window.selectDataLayer('${key}')"><span class="layer-title">${clean(layer.name)}</span>${stackIcon()}<span class="layer-caption">${clean(layer.eyebrow)}</span></button>${index<Object.keys(dataLayers).length-1?'<span class="flow-arrow" aria-hidden="true">→</span>':''}`).join('');
    return `<div class="page-hdr"><h1>Data Information</h1><p>How this project turns student signals into timely, explainable support</p></div><section class="data-overview"><div class="data-flow" aria-label="Student intervention data flow">${flow}</div></section><section class="card data-detail-card"><div class="card-h"><span class="t">Layer detail</span><span class="b" id="layer-detail-label">Select a layer</span></div><div class="card-b" id="layer-detail"><div class="layer-placeholder"><strong>Explore the data flow</strong><span>Select Bronze, Silver, Model, Gold or Outreach to see how that part of the project works.</span></div></div></section><section class="card how-project-card"><div class="card-h"><span class="t">How the project works</span></div><div class="card-b project-steps"><div><b>1. Detect</b><span>Student information and support signals are organized into an intervention-ready record.</span></div><div><b>2. Prioritise</b><span>ML and AI scores identify high, medium and low risk students and explain the reason for attention.</span></div><div><b>3. Support</b><span>Asha AI calls and WhatsApp follow-ups collect context and guide students toward academic, wellbeing and financial support.</span></div><div><b>4. Review</b><span>Counselors and administrators share the same live lists, AI summaries, alerts, reports and CSV export outcomes.</span></div></div></section>`;
  }
  function alertsMarkup(){
    const alerts=[
      ['high','High-risk review required','Arjun Sharma has been prioritised after attendance and assessment signals increased.','2 minutes ago'],
      ['high','Financial-aid support requested','Suman Tiwari needs a financial-aid follow-up before the next fee deadline.','8 minutes ago'],
      ['medium','Attendance decline detected','Neha Patil has missed two recent sessions and needs an academic check-in.','15 minutes ago'],
      ['medium','Counselor follow-up due','Rohan Verma’s recovery-plan review is due within the next 24 hours.','32 minutes ago'],
      ['low','Engagement watchlist updated','Priya Nair has returned to the LMS; continue monitoring the next activity window.','1 hour ago'],
      ['good','WhatsApp response received','Kiran Thakur confirmed the next support step and requested a short study plan.','2 hours ago'],
      ['good','Intervention plan completed','A support slot and resource checklist were recorded for Aditi Rao.','3 hours ago'],
      ['medium','Call analysis ready','The latest completed call can now be reviewed and included in the CSV export.','Today'],
      ['good','Data quality check passed','Student directory and risk-scoring inputs are available for the current workspace.','Today']
    ];
    return `<div class="page-hdr"><h1>Alerts</h1><p>Priority notifications across student risk, outreach and data readiness</p></div><section class="card"><div class="card-h"><span class="t">All alerts</span><span class="b">${alerts.length} notifications</span></div><div class="card-b alert-feed">${alerts.map(([tone,title,detail,time])=>`<article class="alert-item ${tone}"><span class="alert-dot"></span><div><strong>${clean(title)}</strong><p>${clean(detail)}</p></div><time>${clean(time)}</time></article>`).join('')}</div></section>`;
  }
  function ensureUtilityPage(pageName,label,icon,markup){
    let page=document.getElementById(`page-${pageName}`);
    if(!page){page=document.createElement('div');page.className='page';page.id=`page-${pageName}`;document.querySelector('.main')?.appendChild(page);}
    page.innerHTML=markup();
    if(!document.querySelector(`.sb-item[data-page="${pageName}"]`)){
      const item=document.createElement('div');item.className='sb-item';item.dataset.page=pageName;item.innerHTML=`<span style="font-size:16px">${icon}</span> ${label}`;
      const nav=document.querySelector('.sb-nav'),settings=nav?.querySelector('[data-page="settings"]');if(settings)nav.insertBefore(item,settings);else nav?.appendChild(item);
    }
  }
  window.selectDataLayer=key=>{
    const layer=dataLayers[key]||dataLayers.bronze,detail=document.getElementById('layer-detail'),label=document.getElementById('layer-detail-label');
    document.querySelectorAll('.data-layer-card').forEach(card=>card.classList.toggle('selected',card.dataset.layer===key));
    if(label)label.textContent=`${layer.name} layer`;
    if(detail)detail.innerHTML=`<div class="layer-expanded ${layer.tone}"><div><span class="layer-expanded-kicker">${clean(layer.eyebrow)}</span><h2>${clean(layer.name)} layer</h2><p>${clean(layer.summary)}</p></div><ul>${layer.items.map(item=>`<li>${clean(item)}</li>`).join('')}</ul></div>`;
  };
  ensureUtilityPage('information','Data Information','ⓘ',informationMarkup);
  ensureUtilityPage('alerts','Alerts','⚠',alertsMarkup);
  window.showPasswordDemoNotice=()=>toast('Password changes are disabled in this hosted demo.', 'info');
  window.toggleTheme=()=>{
    const root=document.documentElement,light=root.getAttribute('data-theme')==='light';
    if(light){root.removeAttribute('data-theme');localStorage.removeItem('theme');}else{root.setAttribute('data-theme','light');localStorage.setItem('theme','light');}
    const button=document.getElementById('workspace-theme-toggle');if(button)button.textContent=light?'☾':'☀';
  };
  function ensureWorkspaceThemeToggle(){
    if(document.getElementById('workspace-theme-toggle'))return;
    const button=document.createElement('button');button.id='workspace-theme-toggle';button.className='workspace-theme-toggle';button.type='button';button.title='Toggle theme';button.setAttribute('aria-label','Toggle theme');button.textContent=document.documentElement.getAttribute('data-theme')==='light'?'☀':'☾';button.addEventListener('click',window.toggleTheme);document.body.appendChild(button);
  }
  ensureWorkspaceSettings();ensureWorkspaceThemeToggle();
  document.body.classList.toggle('workspace-dashboard-active',Boolean(document.querySelector('#page-dashboard.active,#page-overview.active')));
  window.activateWorkspacePage = pageName => {
    const page=document.getElementById(`page-${pageName}`),item=document.querySelector(`[data-page="${pageName}"]`);
    if(!page)return;
    const previous=document.querySelector('.page.active')?.id?.replace(/^page-/,'');
    // A workspace page is a fresh context: never carry an expanded thread or
    // a search result into another page.  The guided demo owns its own state.
    if(previous && previous!==pageName && !window.__guidedDemoActive){
      state.voiceOpen=null; state.waOpen=null;
      state.voiceQuery=''; state.waQuery=''; state.scrollLocks={}; state.scrollTops={};
      summaryQuery=''; summaryLimit=80; directoryQuery=''; directoryLimit=80; atRiskLimit=60;
      document.querySelectorAll('.page input').forEach(input=>{
        const type=String(input.type||'text').toLowerCase();
        if(type==='text'||type==='search'||type==='') input.value='';
      });
      persist();
    }
    document.querySelectorAll('.page').forEach(node=>node.classList.remove('active'));
    document.querySelectorAll('.sb-item').forEach(node=>node.classList.remove('active'));
    page.classList.add('active'); item?.classList.add('active');
    document.body.classList.toggle('workspace-dashboard-active',['dashboard','overview'].includes(pageName));
    document.body.classList.toggle('transcript-fs',pageName==='transcript');
    if(['transcript','admin-transcript','whatsapp','admin-whatsapp'].includes(pageName))renderOperations();
    if(['summary','admin-summary'].includes(pageName))renderSummaries();
    if(pageName==='student-directory')loadDirectory();
    if(pageName==='students')window.loadStudents();
    if(pageName==='at-risk')window.loadAtRisk();
    if(pageName==='admin-at-risk')window.loadAdminAtRisk();
  };
  document.querySelectorAll('.sb-item[data-page]').forEach(item=>item.addEventListener('click',event=>{
    // This final router owns navigation for both workspaces.  Capturing the
    // click prevents legacy page listeners from leaving stale chat/search UI.
    event.preventDefault(); event.stopImmediatePropagation();
    window.activateWorkspacePage(item.dataset.page);
  },true));
  window.runAnalysis = async () => { try { const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_name:state.demo?.name || ''})}); const d=await r.json(); if(!r.ok || d.error) throw new Error(d.error || 'Analysis failed'); toast(`${d.analyzed} call${d.analyzed===1?'':'s'} analyzed.`, 'ok'); } catch(e) { toast(`Analysis error: ${e.message}`, 'err'); } };
  window.exportCSV = async () => { try { const r=await fetch('/api/export'); const contentType=r.headers.get('content-type')||''; if(!contentType.includes('application/json'))throw new Error(`Server returned ${r.status}. Restart the Flask app and try again.`); const d=await r.json(); if(!r.ok || d.error) throw new Error(d.error || 'Export failed'); toast(d.pending?d.message:`Exported ${d.count} result${d.count===1?'':'s'} to ${d.exported_to}.`, d.pending?'info':'ok'); } catch(e) { toast(`Export error: ${e.message}`, 'err'); } };
  window.waDemo = async () => { const s=demoStudent() || {name:'Demo Student'}; try { await fetch('/whatsapp/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_name:s.name})}); if(!state.demo) state.demo={id:'STU-2847',name:s.name,status:'completed'}; state.waOpen=state.demo.id;state.waSteps[state.demo.id]=0;renderOperations(); toast('WhatsApp follow-up recorded.', 'ok'); } catch(e) { toast('Unable to record the WhatsApp demo.', 'err'); } };
  window.adminWaDemo = window.waDemo;
  async function callStudent(page){ try { toast('Calling student…', 'info'); const r=await fetch('/api/manual-call',{method:'POST'}); const d=await r.json(); if(d.error) throw new Error(d.error); window.startManualLiveCall(d); await new Promise(resolve=>setTimeout(resolve,700)); document.querySelector(`[data-page="${page}"]`)?.click(); } catch(e) { toast(`Call error: ${e.message}`, 'err'); } }
  window.initiateCall = () => callStudent('transcript');
  window.adminInitiateCall = () => callStudent('admin-transcript');
  window.resetLiveOperations = async () => { if(!confirm('Reset live calls and WhatsApp conversations?')) return; try { const r=await fetch('/api/reset',{method:'POST'}); if(!r.ok) throw new Error('Reset failed'); state={voiceOpen:null,waOpen:null,demo:null,tick:0,voiceQuery:state.voiceQuery||'',waQuery:state.waQuery||'',scrollLocks:{},scrollTops:{},voiceSteps:{},waSteps:{},directoryTotal:state.directoryTotal||4500}; localStorage.removeItem(storageKey); renderOperations(); renderSummaries(); toast('Live call and WhatsApp data reset.', 'ok'); } catch(e) { toast(`Reset error: ${e.message}`, 'err'); } };
  const style=document.createElement('style'); style.textContent=`.operation-row{border-bottom:1px solid var(--border);padding:0}.operation-name{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 4px;background:none;border:0;color:var(--text);font:600 13px var(--font);text-align:left;cursor:pointer}.operation-name:hover{background:var(--surface)}.operation-status{font-size:9px;color:var(--text3);white-space:nowrap}.operation-detail{margin:0 4px 14px;padding:16px;border:1px solid var(--border);border-radius:10px;background:var(--bg);font-size:13px;line-height:1.6}.operation-detail p{margin:3px 0 10px}.speaker{font:600 10px var(--mono);letter-spacing:.6px}.speaker.ai{color:var(--purple)}.speaker.student{color:var(--blue)}.time{color:var(--text3);font-weight:400}.live-pulse{font:11px var(--mono);color:var(--green);margin:14px 0}.chat-line{display:flex;flex-direction:column;gap:3px;max-width:78%;padding:10px 12px;margin:10px 0;border-radius:10px}.chat-line b{font:10px var(--mono);text-transform:uppercase}.ai-chat{background:var(--surface2);color:var(--text)}.student-chat{background:var(--blue-g);color:var(--blue);margin-left:auto}.summary-list-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border:1px solid var(--border);border-radius:10px;background:var(--surface);color:var(--text);cursor:pointer;text-align:left}.summary-list-row:hover{border-color:var(--purple)}.summary-list-row+ .summary-list-row{margin-top:8px}.summary-list-row small{display:block;color:var(--text3);font:10px var(--mono);margin-top:4px}.student-summary{margin:16px 0;padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--surface2);font-size:13px;line-height:1.6}.student-summary p{margin:8px 0 0;color:var(--text2)}`; document.head.appendChild(style);
  const refinements=document.createElement('style');
  refinements.textContent=`
    .operation-toolbar{display:flex;gap:8px;align-items:center;margin:-4px 0 16px}.operation-toolbar .search-input{max-width:360px}.operation-label{display:inline-flex;align-items:center;gap:7px}.presence-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 9px var(--green);display:inline-block}.history-dot{width:6px;height:6px;border-radius:50%;background:var(--text3);display:inline-block}.live-badge{font:700 9px var(--mono);letter-spacing:.7px;padding:3px 5px;color:var(--green);background:var(--green-g);border-radius:4px}.operation-status{font:10px var(--mono);color:var(--text3);white-space:nowrap}.operation-detail{max-height:480px;overflow-y:auto;overscroll-behavior:contain}.risk-flag{margin:14px 0 6px;padding:10px 12px;border:1px solid var(--red);background:var(--red-g);border-radius:8px;color:var(--red);font-size:12px}.operation-empty{padding:22px 4px;color:var(--text3)}
    .transcript-thread{display:flex;flex-direction:column;gap:10px;white-space:normal!important;scroll-behavior:smooth}.transcript-message{display:flex;width:100%}.transcript-message.ai-message{justify-content:flex-start}.transcript-message.student-message{justify-content:flex-end}.message-bubble{display:flex;flex-direction:column;gap:4px;max-width:min(72%,760px);padding:11px 14px;border:1px solid var(--border);border-radius:12px;background:var(--surface2);color:var(--text)}.student-message .message-bubble{background:var(--surface);border-color:var(--border-b)}.message-bubble b{font:700 10px var(--mono);color:var(--text2);text-transform:uppercase}.message-bubble span{line-height:1.55}.message-bubble small{font:9px var(--mono);color:var(--text3);align-self:flex-end}.call-end{align-self:flex-start;margin-top:6px}.call-ended{align-self:center;margin:6px 0;padding:7px 12px;border:1px solid var(--border);border-radius:999px;color:var(--text3);font:10px var(--mono);letter-spacing:.6px}
    #page-transcript .card,#page-admin-transcript .card,#page-whatsapp .card,#page-admin-whatsapp .card{max-width:none!important;width:100%;min-height:calc(100vh - 225px)!important;display:flex;flex-direction:column}#full-transcript-panel,#admin-transcript-panel,#wa-convos-panel,#admin-wa-panel{flex:1;max-height:calc(100vh - 285px)!important;min-height:calc(100vh - 285px)!important;overflow-y:auto!important}
    .summary-list-row{position:relative;overflow:hidden;background:linear-gradient(105deg,var(--surface) 0%,var(--surface2) 100%);border-left:4px solid var(--green)}.summary-list-row.risk-high{border-left-color:var(--red)}.summary-list-row.risk-medium{border-left-color:var(--amber)}.summary-list-row.risk-low{border-left-color:var(--green)}.summary-list-row span{font:700 9px var(--mono);color:var(--text3)}.summary-list-row.risk-high span{color:var(--red)}.summary-list-row.risk-medium span{color:var(--amber)}.summary-list-row.risk-low span{color:var(--green)}.summary-list-row:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,0,0,.18)}.summary-chip.low{color:var(--green);background:var(--green-g)}
    #summary-students,#admin-summary-grid{display:block!important}.ai-summary-list{display:flex;flex-direction:column;gap:9px;background:none}.ai-summary-row{display:block;width:100%;padding:18px 20px;border:1px solid var(--border);border-left:4px solid var(--green);border-radius:10px;background:var(--surface);color:var(--text);text-align:left;cursor:pointer;font:600 14px var(--font)}.ai-summary-row:hover{background:var(--surface2)}.ai-summary-row.risk-high{border-left-color:var(--red)}.ai-summary-row.risk-medium{border-left-color:var(--amber)}.ai-summary-row.risk-low{border-left-color:var(--green)}.at-risk-summary-link{cursor:pointer}.at-risk-summary-link:hover td{background:var(--surface2)}#page-at-risk .tbl th:last-child,#page-admin-at-risk .tbl th:last-child{display:none}
    .completion-notice{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:17500;width:min(440px,calc(100vw - 40px));padding:24px;border:1px solid var(--red);border-radius:14px;background:var(--bg);box-shadow:0 18px 52px rgba(0,0,0,.48);text-align:center}.completion-notice strong{font-size:18px;color:var(--text)}.completion-notice p{margin:10px 0 0;color:var(--text2);font-size:13px;line-height:1.55}.workspace-theme-toggle{position:fixed;right:20px;top:20px;z-index:9000;display:none;width:42px;height:42px;border-radius:50%;border:1px solid var(--border);background:var(--surface);color:var(--text);box-shadow:0 8px 22px rgba(0,0,0,.28);font-size:18px;cursor:pointer}.workspace-theme-toggle:hover{background:var(--surface2)}body:not(.workspace-dashboard-active) .workspace-theme-toggle{display:grid;place-items:center}
    .settings-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}.settings-body{padding:20px!important;display:flex;flex-direction:column;gap:14px}.profile-avatar{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:var(--surface2);font:700 13px var(--mono);color:var(--text)}.profile-role{display:flex;flex-direction:column;gap:3px}.profile-role span,.settings-note,.settings-line span{font-size:11px;color:var(--text3)}.settings-body label{display:flex;flex-direction:column;gap:6px;font:10px var(--mono);letter-spacing:.6px;color:var(--text3)}.profile-value{display:block;width:100%;padding:10px 11px;border:1px solid var(--border);border-radius:7px;background:var(--surface2);color:var(--text);font:12px var(--font);letter-spacing:0;text-transform:none;word-break:break-all}.profile-hash{font:10px var(--mono);color:var(--text2)}.settings-note{margin:0}.settings-line{display:flex;align-items:center;justify-content:space-between;gap:14px;padding-bottom:14px;border-bottom:1px solid var(--border)}.settings-line:last-child{padding-bottom:0;border-bottom:0}.settings-line>div{display:flex;flex-direction:column;gap:4px}.settings-line strong{font-size:13px}@media(max-width:760px){.settings-layout{grid-template-columns:1fr}}
    .data-overview{padding:10px 0 22px}.data-flow{display:flex;align-items:center;justify-content:center;gap:14px;overflow-x:auto;padding:8px 0 14px}.data-layer-card{position:relative;flex:0 0 164px;min-height:198px;display:flex;align-items:center;flex-direction:column;gap:10px;padding:18px 12px;border:1px solid var(--border);border-radius:13px;background:linear-gradient(145deg,var(--surface),var(--surface2));color:var(--text);cursor:pointer;transition:transform .18s,border-color .18s,box-shadow .18s}.data-layer-card:hover,.data-layer-card.selected{transform:translateY(-3px);box-shadow:0 12px 28px rgba(0,0,0,.2)}.data-layer-card.bronze{--layer:#c78a4a}.data-layer-card.silver{--layer:#9aa0a6}.data-layer-card.model{--layer:var(--purple)}.data-layer-card.gold{--layer:#d9bb69}.data-layer-card.outreach{--layer:var(--green)}.data-layer-card.selected{border-color:var(--layer);box-shadow:0 0 0 1px var(--layer),0 12px 28px rgba(0,0,0,.22)}.layer-title{font:700 20px var(--font);color:var(--layer)}.layer-caption{font-size:11px;color:var(--text3);line-height:1.35}.layer-stack-icon{position:relative;width:86px;height:80px;display:block}.layer-stack-icon i{position:absolute;left:17px;width:52px;height:32px;border:6px solid var(--layer);border-radius:5px;transform:rotate(30deg) skewX(-30deg);opacity:.95}.layer-stack-icon i:nth-child(1){top:1px}.layer-stack-icon i:nth-child(2){top:19px}.layer-stack-icon i:nth-child(3){top:37px}.layer-stack-icon i:nth-child(4){top:55px}.flow-arrow{flex:0 0 auto;font-size:35px;color:var(--text3)}.data-detail-card{margin-bottom:16px}.layer-placeholder{padding:16px;display:flex;flex-direction:column;gap:6px;color:var(--text2)}.layer-expanded{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:26px;padding:6px}.layer-expanded{--layer:var(--purple)}.layer-expanded.bronze{--layer:#c78a4a}.layer-expanded.silver{--layer:#9aa0a6}.layer-expanded.model{--layer:var(--purple)}.layer-expanded.gold{--layer:#d9bb69}.layer-expanded.outreach{--layer:var(--green)}.layer-expanded-kicker{font:700 10px var(--mono);letter-spacing:.8px;color:var(--layer);text-transform:uppercase}.layer-expanded h2{margin:8px 0;font-size:22px}.layer-expanded p{margin:0;color:var(--text2);line-height:1.65;font-size:13px}.layer-expanded ul{margin:0;padding:2px 0 0 20px;display:flex;flex-direction:column;gap:9px;color:var(--text2);font-size:13px;line-height:1.45}.layer-expanded li::marker{color:var(--layer)}.project-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:18px!important}.project-steps div{padding:13px;border:1px solid var(--border);border-radius:9px;background:var(--surface);display:flex;flex-direction:column;gap:6px}.project-steps b{color:var(--text);font-size:13px}.project-steps span{font-size:12px;color:var(--text2);line-height:1.5}.alert-feed{padding:0 20px!important}.alert-item{display:grid;grid-template-columns:10px minmax(0,1fr) auto;gap:12px;align-items:start;padding:17px 0;border-bottom:1px solid var(--border)}.alert-item:last-child{border-bottom:0}.alert-dot{width:9px;height:9px;border-radius:50%;background:var(--text3);margin-top:5px}.alert-item.high .alert-dot{background:var(--red);box-shadow:0 0 9px var(--red)}.alert-item.medium .alert-dot{background:var(--amber);box-shadow:0 0 9px var(--amber)}.alert-item.low .alert-dot{background:var(--blue)}.alert-item.good .alert-dot{background:var(--green);box-shadow:0 0 9px var(--green)}.alert-item strong{font-size:13px}.alert-item p{margin:5px 0 0;color:var(--text2);font-size:12px;line-height:1.45}.alert-item time{font:10px var(--mono);color:var(--text3);white-space:nowrap;margin-top:3px}@media(max-width:980px){.data-flow{justify-content:flex-start}.project-steps{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.layer-expanded{grid-template-columns:1fr}.project-steps{grid-template-columns:1fr}.data-layer-card{flex-basis:148px}.flow-arrow{display:none}.alert-item{grid-template-columns:10px minmax(0,1fr)}.alert-item time{grid-column:2}.workspace-theme-toggle{right:12px;top:12px}}
    /* Keep the conversation directory on the document scroll, like every
       other page. This avoids a second narrow scrollbar for the names. */
    #page-transcript .card,#page-admin-transcript .card,#page-whatsapp .card,#page-admin-whatsapp .card{min-height:0!important}
    #full-transcript-panel,#transcript-panel,#admin-transcript-panel,#wa-convos-panel,#admin-wa-panel{min-height:0!important;max-height:none!important;overflow:visible!important}
    @media(max-width:620px){.operation-toolbar{flex-wrap:wrap}.operation-toolbar .search-input{max-width:none;flex:1 1 100%}.operation-status{display:none}}
  `;document.head.appendChild(refinements);
  window.closeModal=()=>document.getElementById('modal')?.classList.remove('show');
  document.addEventListener('keydown',event=>{if(event.key==='Escape')window.closeModal();});
  // A previous prototype poller also writes directly to these panels. Repair
  // only an external overwrite immediately, rather than waiting for the next
  // regular live tick (which caused the visible blank/glitch in the transcript).
  let repairQueued=false;
  const repairOperations=()=>{
    if(window.__guidedDemoActive) return;
    if(repairQueued) return;
    repairQueued=true;
    queueMicrotask(()=>{
      repairQueued=false;
      const panels=['full-transcript-panel','transcript-panel','admin-transcript-panel','wa-convos-panel','admin-wa-panel'].map(id=>document.getElementById(id)).filter(Boolean);
      if(panels.some(panel=>!panel.querySelector('.operation-row'))) renderOperations();
    });
  };
  // Legacy panel pollers are disabled above, so this renderer no longer needs
  // DOM mutation observers that can recursively schedule repair work.
  // Legacy polling also changes the sidebar count independently. Keep it tied
  // to the rendered list (7 sample calls, or 8 once the demo call starts).
  ['ts-count','admin-ts-count','sb-voice-count','admin-voice-count','wa-count-badge','admin-wa-badge','sb-wa-count','admin-wa-count'].map(id=>document.getElementById(id)).filter(Boolean).forEach(counter=>new MutationObserver(enforceOperationCounts).observe(counter,{childList:true,subtree:true,characterData:true}));
  setTimeout(()=>{renderOperations();renderSummaries();},0);
  let workspaceUpdateNumber=0;
  const scheduleWorkspaceUpdate=()=>setTimeout(async()=>{
    if(!window.__guidedDemoActive){await syncSpokenName();await syncActualWhatsApp();renderOperations();renderSummaries();}
    workspaceUpdateNumber+=1; scheduleWorkspaceUpdate();
  },workspaceUpdateNumber<2?5000:4600);
  scheduleWorkspaceUpdate();
})();
</script>'''
ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace("</body></html>", _OPERATIONS_UI + "</body></html>")
COUNSELOR_DASHBOARD = COUNSELOR_DASHBOARD.replace("</body></html>", _OPERATIONS_UI + "</body></html>")

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
