import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Admin Dashboard generic tab clicking
generic_click = r"""document.querySelectorAll('.sb-item').forEach(i=>i.addEventListener('click',()=>{document.querySelectorAll('.sb-item').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));i.classList.add('active');const p=document.getElementById('page-'+i.dataset.page);if(p)p.classList.add('active');if(i.dataset.page==='admin-at-risk')loadAdminAtRisk();if(i.dataset.page==='admin-summary')loadAdminSummary();if(i.dataset.page==='admin-transcript')loadAdminTranscripts();if(i.dataset.page==='admin-whatsapp')loadAdminWhatsApp()}));"""

text = re.sub(
    r"document\.querySelectorAll\('\.sb-item\[data-page\^=\"admin-\"\]'\)\.forEach\(i=>i\.addEventListener\('click',\(\)=>\{.*?\}\)\);",
    generic_click,
    text
)

# 2. Append SHARED_JS to ADMIN_DASHBOARD
text = re.sub(
    r"ADMIN_DASHBOARD = ADMIN_DASHBOARD\.replace\(\"</script>\\n</body></html>\", r'''</script>\n<script>\n\(function\(\)\{",
    r"ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace(\"</script>\\n</body></html>\", \"</script>\\n\" + SHARED_JS + r'''<script>\n(function(){",
    text
)

# 3. AI Student Summary Expansion
text = re.sub(
    r"card\.innerHTML=`<span class=\"summary-chip \$\{t\}\">\$\{t\.toUpperCase\(\)\} RISK(.*?)card\.onclick=function\(\)\{",
    r"card.innerHTML=`<div class=\"sum-header\" style=\"display:flex;align-items:center;justify-content:space-between\"><h3 style=\"margin:0;font-size:16px\">${n}</h3><span class=\"summary-chip ${t}\">${t.toUpperCase()} RISK</span></div><div class=\"sum-body\" style=\"display:none;margin-top:12px;border-top:1px solid rgba(255,255,255,0.1);padding-top:12px\"><div class=\"mono\" style=\"font-size:10px;color:var(--${t});margin-bottom:7px\">AI STUDENT SUMMARY</div><p style=\"margin:0;color:var(--text2);font-size:13px\">${n} is showing signs of disengagement...</p></div>`;card.onclick=function(){",
    text,
    flags=re.DOTALL
)

# 4. loadStudents() show all 4500 and names
text = re.sub(
    r"window\.loadStudents=async function\(\)\{(.*?)\.filter\(s=>\['HIGH','MEDIUM'\]\.includes\(String\(s\.final_risk_tier\|\|''\)\.toUpperCase\(\)\)\);",
    r"window.loadStudents=async function(){\1;",
    text,
    flags=re.DOTALL
)
text = re.sub(
    r"document\.getElementById\('sb-student-count'\)\.textContent=rows\.length;",
    r"document.getElementById('sb-student-count').textContent='4,500';",
    text
)
text = re.sub(
    r"<td><strong>\$\{s\.student_id\}</strong></td>",
    r"<td><strong>${s.student_name||'Student'}</strong><br><span class=\"mono\" style=\"color:var(--text3)\">${s.student_id}</span></td>",
    text
)

# 5. Pipeline Schema Tables removal
text = re.sub(
    r'<!-- Data Schema.*?<!-- Pipeline Architecture',
    r'<!-- Pipeline Architecture',
    text,
    flags=re.DOTALL
)

# 6. Admin Interventions and Conversations removal
text = re.sub(
    r'<!-- Removed Interventions and Conversations -->.*?<div class="sb-item" data-page="analytics">',
    r'<div class="sb-item" data-page="analytics">',
    text,
    flags=re.DOTALL
)
text = re.sub(
    r'<div class="sb-item" data-page="interventions">.*?</div>',
    r'',
    text,
    flags=re.DOTALL
)
text = re.sub(
    r'<div class="sb-item" data-page="whatsapp">.*?</div>',
    r'',
    text,
    flags=re.DOTALL
)


try:
    with open('patch_app_fixed.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Wrote patch_app_fixed.py")
except Exception as e:
    with open('error.txt', 'w') as f:
        f.write(str(e))
