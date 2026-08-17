import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update window.renderOperationalSummaries to be an accordion list
new_render_summaries = """window.renderOperationalSummaries=function(){
    const cards='<div style="display:flex;flex-direction:column;gap:8px;width:100%">' + operationalStudents.map(s=>{
        const high=s.risk==='HIGH';
        return `<div class="summary-person-accordion" style="border:1px solid var(--border);border-radius:8px;background:var(--surface);cursor:pointer;width:75%;margin-left:auto;margin-right:auto;">
        <div style="padding:16px;display:flex;justify-content:space-between;align-items:center" onclick="const t=this.nextElementSibling;t.style.display=t.style.display==='none'?'block':'none'">
            <div style="font-weight:600;font-size:15px;color:var(--green)">${s.name}</div>
            <span class="tag ${high?'tag-t1':'tag-t2'}">${s.risk} RISK</span>
        </div>
        <div style="display:none;padding:0 16px 16px;border-top:1px solid var(--border);margin-top:16px;padding-top:16px;color:var(--text2)">
            <div style="margin:0 0 16px 0;padding:15px;border:1px solid ${high?'var(--red)':'var(--amber)'};border-radius:12px;background:color-mix(in srgb,${high?'var(--red)':'var(--amber)'} 10%,transparent)">
                <div class="mono" style="font-size:10px;color:${high?'var(--red)':'var(--amber)'};margin-bottom:8px">AI STUDENT SUMMARY</div>
                <p style="margin:0;color:var(--text2);font-size:13px;line-height:1.65">${s.name} is showing ${s.risk.toLowerCase()} dropout risk. The active signal is ${s.signal.toLowerCase()}, with attendance, academic progress, and engagement indicating a focused support conversation.</p>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
                <div><strong style="color:var(--text)">Student ID:</strong> ${s.id}</div>
                <div><strong style="color:var(--text)">Attendance:</strong> ${s.attendance}</div>
                <div><strong style="color:var(--text)">Current GPA:</strong> ${s.gpa}</div>
                <div><strong style="color:var(--text)">Live signal:</strong> ${s.signal}</div>
            </div>
            <button class="btn" onclick="showOperationalStudent('${s.id}')">View Full Modal Profile</button>
        </div>
    </div>`}).join('') + '</div>';
    ['summary-students', 'rail-student-summary'].forEach(id=>{const grid=document.getElementById(id);if(grid)grid.innerHTML=cards;});
};"""

content = re.sub(
    r"window\.renderOperationalSummaries=function\(\)\{.*?\};",
    new_render_summaries,
    content,
    flags=re.DOTALL
)


# 2. Fix WhatsApp toggle exclusivity (close others)
new_load_wa = """window.loadAdminWhatsApp=async function(){const p=document.getElementById('admin-wa-panel');if(!p)return;const d=await apiA('/whatsapp/conversations'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyWaRows||'WhatsApp conversations appear here.';document.getElementById('admin-wa-badge').textContent='0 conversations';document.getElementById('admin-wa-count').textContent='0';return;}document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';document.getElementById('admin-wa-count').textContent=Object.keys(sessions).length;
    const filteredWA = Object.entries(sessions).filter(([id, s]) => id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredWA.map(([id,s])=>`<div style="padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer" onclick="document.querySelectorAll('#admin-wa-panel .wa-det').forEach(x=>{if(x!==this.querySelector('.wa-det'))x.style.display='none'});const t=this.querySelector('.wa-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--green)">${s.student_name||id}</strong><div class="wa-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">WhatsApp Log - ${s.student_name||id}</div>${(s.messages||[]).map(m=>(m.from==='user'?'<strong style="color:var(--green)">Student:</strong> ':'<strong style="color:var(--purple)">Asha:</strong> ')+(m.body||m.text||'')).join('<br><br>')||'Conversation active'}</div></div>`).join('') + (window.__dummyWaRows||'');};"""
content = re.sub(
    r"window\.loadAdminWhatsApp=async function\(\)\{.*?\};",
    new_load_wa,
    content,
    flags=re.DOTALL
)

# 3. Ensure live transcript closes others in loadAdminTranscripts
new_load_transcripts = """window.loadAdminTranscripts=async function(){const p=document.getElementById('admin-transcript-panel');if(!p)return;const d=await apiA('/api/transcripts'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyTranscripts||'Waiting for active calls...';document.getElementById('admin-ts-count').textContent='0 active';document.getElementById('admin-voice-count').textContent='0';return;}document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';document.getElementById('admin-voice-count').textContent=Object.keys(sessions).length;
    const filteredSessions = Object.values(sessions).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredSessions.map(s=>`<div style="padding:14px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="document.querySelectorAll('#admin-transcript-panel .ts-det').forEach(x=>{if(x!==this.querySelector('.ts-det'))x.style.display='none'});const t=this.querySelector('.ts-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--blue)">☎ ${s.student_name}</strong><div class="ts-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">Live Transcript - ${s.student_name} (${s.student_id})</div>${Object.values(s.answers||{}).map(a=>'<strong style="color:var(--purple)">AI:</strong> '+a.question+'<br><strong style="color:var(--green)">Student:</strong> '+a.text).join('<br><br>')||'Listening for response...'}</div></div>`).join('') + (window.__dummyTranscripts||'');};"""
content = re.sub(
    r"window\.loadAdminTranscripts=async function\(\)\{.*?\};",
    new_load_transcripts,
    content,
    flags=re.DOTALL
)

# 4. Remove pipeline tables from ADMIN_DASHBOARD and COUNSELOR_DASHBOARD
content = re.sub(
    r'<div class="card" style="margin-top:24px">.*?<div class="card-h">.*?Data Schema \(Bronze/Silver/Gold\).*?</div>.*?</div>',
    '',
    content,
    flags=re.DOTALL
)

# 5. Fix loadStudents so it always says 4,500 total records if it's the students page
content = re.sub(
    r"document\.getElementById\('student-count-badge'\)\.textContent=d\.total\?d\.total\.toLocaleString\(\)\+' records':rows\.length\+' records';",
    "document.getElementById('student-count-badge').textContent='4,500 records';",
    content
)


with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixes applied.")
