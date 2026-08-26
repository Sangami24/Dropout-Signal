"""
This script directly fixes the two corruption zones in app.py:
1. Lines 6640-6650: orphaned fragment of _local_api_model_metrics
2. Lines 6612-6617: duplicate 'if voice is None' block
"""

with open(r'c:\Users\achal\Documents\Projects\Dropout Signal\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ---- FIX 1: Remove the orphaned fragment after api_call_result ----
# These lines appear right after the return statement of api_call_result
# and before @app.route("/api/dataset/status")
bad_fragment = '''    return jsonify({"call": _native_json(call), "result": _native_json(result)})
        "dataset_loaded": True,\r
        "run_id": status.get("run_id"),\r
        "dataset_name": status.get("dataset_name"),\r
        "record_count": status.get("record_count"),\r
        "created_at": status.get("created_at"),\r
        "tiers": status["tier_breakdown"],\r
        "models": status["models"],\r
        "champion_model": status["champion_model"],\r
        "shap": _native_json(active_global_shap()),\r
        "feature_groups": FEATURE_GROUPS,\r
    })\r
\r
\r
@app.route("/api/dataset/status")\r'''

good_fragment = '''    return jsonify({"call": _native_json(call), "result": _native_json(result)})


@app.route("/api/dataset/status")'''

if bad_fragment in content:
    content = content.replace(bad_fragment, good_fragment, 1)
    print("FIX 1 applied: removed orphaned fragment")
else:
    print("FIX 1: fragment not found with CRLF - trying LF version...")
    bad_fragment_lf = bad_fragment.replace('\r\n', '\n').replace('\r', '\n')
    if bad_fragment_lf in content:
        content = content.replace(bad_fragment_lf, good_fragment, 1)
        print("FIX 1 applied (LF): removed orphaned fragment")
    else:
        # Try line by line approach
        lines = content.splitlines(True)
        new_lines = []
        skip_until_dataset_status = False
        i = 0
        while i < len(lines):
            line = lines[i]
            # Detect the orphaned fragment: after api_call_result return,
            # if next non-blank line is '        "dataset_loaded": True,'
            if (line.strip() == 'return jsonify({"call": _native_json(call), "result": _native_json(result)})' 
                    and i + 1 < len(lines) 
                    and '"dataset_loaded": True,' in lines[i+1]):
                new_lines.append(line)
                # Skip orphaned lines until we hit the @app.route for dataset/status
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('@app.route("/api/dataset/status")'):
                    i += 1
                print(f"FIX 1 applied (line-by-line): skipped to line {i+1}")
                continue
            new_lines.append(line)
            i += 1
        content = ''.join(new_lines)
        print("FIX 1 applied (line-by-line method)")

# ---- FIX 2: Remove duplicate 'if voice is None' block ----
# The student_detail function has this block duplicated
dup_block = '''    if voice is None:\r
        name = str(row.get("student_name") or "This student")\r
        factor = str(row.get("primary_root_cause") or row.get("top_factor_1") or "current engagement signals")\r
    if voice is None:\n'''

if dup_block in content:
    content = content.replace(dup_block, '    if voice is None:\n', 1)
    print("FIX 2 applied: removed duplicate 'if voice is None'")
else:
    # Try with both line endings
    lines = content.splitlines(True)
    new_lines = []
    i = 0
    while i < len(lines):
        # Look for double 'if voice is None:' pattern
        if (lines[i].strip() == 'if voice is None:' and
                i + 3 < len(lines) and
                lines[i+3].strip() == 'if voice is None:'):
            # Skip lines i, i+1, i+2 (the first incomplete block)
            new_lines.append(lines[i+3])  # Keep second 'if voice is None:'
            i += 4
            print(f"FIX 2 applied (line-by-line): removed duplicate at line {i-4+1}")
            continue
        new_lines.append(lines[i])
        i += 1
    content = ''.join(new_lines)

# Write the fixed file
with open(r'c:\Users\achal\Documents\Projects\Dropout Signal\app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\nFile written. Now running syntax check...")

import subprocess
result = subprocess.run(
    ['python', '-m', 'py_compile', 'app.py'],
    capture_output=True, text=True,
    cwd=r'c:\Users\achal\Documents\Projects\Dropout Signal'
)
if result.returncode == 0:
    print("✅ SYNTAX OK - app.py compiles cleanly!")
else:
    print("❌ SYNTAX ERROR:", result.stderr)
