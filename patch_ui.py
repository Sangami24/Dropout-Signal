import json
import os

APP_PY_PATH = "app.py"

def patch_app():
    if not os.path.exists(APP_PY_PATH):
        print(f"Error: {APP_PY_PATH} not found.")
        return

    with open(APP_PY_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update Sidebar Logo
    logo_target = """<div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background:var(--green);box-shadow:0 0 16px rgba(34,197,94,.55)"><svg viewBox="0 0 24 24" style="width:20px;height:20px;stroke:#06230f;fill:none;stroke-width:2.8"><polyline points="2 13 7 13 10 5 14 19 17 11 22 11"/></svg></div>"""
    logo_repl = """<div class="sb-icon" style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,var(--red),#d62828);box-shadow:0 0 16px rgba(239,68,68,.4);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 24 24" style="width:20px;height:20px;stroke:#fff;fill:none;stroke-width:2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>"""
    if logo_target in content:
        content = content.replace(logo_target, logo_repl)
        print("Updated sidebar logo.")

    # 2. Add Fullscreen Transcript CSS
    css_target = """.act-table td { padding: 12px 16px; font-size: 12px; border-bottom: 1px solid var(--border); color: var(--text2); }
.act-table tr:last-child td { border-bottom: none; }
</style>"""
    css_repl = """.act-table td { padding: 12px 16px; font-size: 12px; border-bottom: 1px solid var(--border); color: var(--text2); }
.act-table tr:last-child td { border-bottom: none; }
body.transcript-fs .sidebar { display: none !important; }
body.transcript-fs .main { margin-left: 0 !important; }
</style>"""
    if css_target in content:
        content = content.replace(css_target, css_repl)
        print("Added fullscreen transcript CSS.")

    # 3. Add Fullscreen Transcript JS Logic
    js_target = """document.querySelectorAll('.sb-item').forEach(item=>{
  item.addEventListener('click',()=>{
    document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('page-'+item.dataset.page).classList.add('active');
  });
});"""
    js_repl = """document.querySelectorAll('.sb-item').forEach(item=>{
  item.addEventListener('click',()=>{
    document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('page-'+item.dataset.page).classList.add('active');
    if (item.dataset.page === 'transcript') document.body.classList.add('transcript-fs');
    else document.body.classList.remove('transcript-fs');
  });
});"""
    if js_target in content:
        content = content.replace(js_target, js_repl)
        print("Added fullscreen transcript JS.")

    # 4. Hide counselor rail
    rail_target = """<aside class="counselor-rail" aria-label="Counselor context panel">"""
    rail_repl = """<aside class="counselor-rail" aria-label="Counselor context panel" style="display:none;">"""
    if rail_target in content:
        content = content.replace(rail_target, rail_repl)
        print("Hid counselor rail.")

    # 5. Fix WhatsApp Demo typing speed
    wa_speed_target = """    await pause(role==='user' ? 34 : 24);"""
    wa_speed_repl = """    await pause(60);"""
    if wa_speed_target in content:
        content = content.replace(wa_speed_target, wa_speed_repl)
        print("Adjusted WhatsApp typing speed.")

    # 6. Fix Transcript Demo typing speed
    ts_speed_target = """      // The first answer deliberately starts slowly, then accelerates.
      await pause(q===0 && i<22 ? 62 : (q===0 ? 18 : 14));"""
    ts_speed_repl = """      // The first answer deliberately starts slowly, then accelerates.
      await pause(q===0 && i<15 ? 120 : (q===0 && i<35 ? 60 : 12));"""
    if ts_speed_target in content:
        content = content.replace(ts_speed_target, ts_speed_repl)
        print("Adjusted transcript typing speed.")

    with open(APP_PY_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("app.py patched successfully!")

if __name__ == "__main__":
    patch_app()
