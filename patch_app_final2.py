import sys
import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix Admin Counselor
text = text.replace('Admin Counselor', 'Academic Counselor')

# 2. Inject missing Javascript functions before loadTranscripts
if 'window.loadStudents=async function' not in text:
    inject_js = r'''
window.loadStudents=async function(){const q=document.getElementById('student-search')?.value||'',body=document.getElementById('students-tbody');if(!body)return;body.innerHTML='<tr><td colspan=\"6\" style=\"padding:40px;text-align:center\"><div class=\"loading-spinner\"></div></td></tr>';const d=await api('/api/students?limit=4500&search='+encodeURIComponent(q)),rows=d.students||[];document.getElementById('student-count-badge').textContent=d.total?d.total.toLocaleString()+' records':rows.length+' records';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class=\"mono\" style=\"color:var(--text3);font-size:10px\">${s.student_id}</span></td><td class=\"mono\">${Number(s.ml_risk_score||0).toFixed(3)}</td><td><span class=\"tag ${s.final_risk_tier==='HIGH'?'tag-t1':s.final_risk_tier==='MEDIUM'?'tag-t2':'tag-t3'}\">${s.final_risk_tier}</span></td><td>${s.top_factor_1||'—'}</td><td><span class=\"tag tag-t3\">${s.outcome_status||'Enrolled'}</span></td><td><button class=\"btn\" onclick=\"showStudent('${s.student_id}')\">View</button></td></tr>`).join(''):'<tr><td colspan=\"6\" style=\"text-align:center;color:var(--text3);padding:30px\">No students found</td></tr>';};
window.loadHistogram=async function(){};
'''
    text = text.replace('async function loadTranscripts(){', inject_js + '\nasync function loadTranscripts(){', 1)

# 3. Replace loadAdminTranscripts via re
ts_pattern = r'window\.loadAdminTranscripts=async function\(\)\{.*?\};'
new_ts = r'''window.loadAdminTranscripts=async function(){const p=document.getElementById('admin-transcript-panel');if(!p)return;if(window.renderDummyLiveOperations){window.renderDummyLiveOperations();return;}const d=await apiA('/api/transcripts'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML='Waiting for active calls...';document.getElementById('admin-ts-count').textContent='0 active';document.getElementById('admin-voice-count').textContent='0';return;}document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';document.getElementById('admin-voice-count').textContent=Object.keys(sessions).length;
const filteredSessions = Object.values(sessions).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
p.innerHTML=filteredSessions.map(s=>`<div style=\"padding:14px 0;border-bottom:1px solid var(--border);cursor:pointer\" onclick=\"document.querySelectorAll('.ts-det').forEach(x=>{if(x!==this.querySelector('.ts-det'))x.style.display='none'});const t=this.querySelector('.ts-det');t.style.display=t.style.display==='none'?'block':'none'\"><strong style=\"color:var(--blue)\">☎ ${s.student_name}</strong><div class=\"ts-det\" style=\"display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)\"><div style=\"margin-bottom:12px;font-weight:600;font-size:16px\">Live Transcript - ${s.student_name} (${s.student_id})</div>${Object.values(s.answers||{}).map(a=>'<strong style=\"color:var(--purple)\">AI:</strong> '+a.question+'<br><strong style=\"color:var(--green)\">Student:</strong> '+a.text).join('<br><br>')||'Listening for response...'}</div></div>`).join('');};'''
text = re.sub(ts_pattern, new_ts, text, flags=re.DOTALL)

# 4. Replace loadAdminWhatsApp
wa_pattern = r'window\.loadAdminWhatsApp=async function\(\)\{.*?\};'
new_wa = r'''window.loadAdminWhatsApp=async function(){const p=document.getElementById('admin-wa-panel');if(!p)return;if(window.renderDummyLiveOperations){window.renderDummyLiveOperations();return;}const d=await apiA('/whatsapp/conversations'),sessions=d.sessions||{};if(Object.keys(sessions).length===0){p.innerHTML='WhatsApp conversations appear here.';document.getElementById('admin-wa-badge').textContent='0 conversations';document.getElementById('admin-wa-count').textContent='0';return;}document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';document.getElementById('admin-wa-count').textContent=Object.keys(sessions).length;
const filteredWA = Object.entries(sessions).filter(([id, s]) => id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
p.innerHTML=filteredWA.map(([id,s])=>`<div style=\"padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer\" onclick=\"document.querySelectorAll('.wa-det').forEach(x=>{if(x!==this.querySelector('.wa-det'))x.style.display='none'});const t=this.querySelector('.wa-det');t.style.display=t.style.display==='none'?'block':'none'\"><strong style=\"color:var(--green)\">${s.student_name||id}</strong><div class=\"wa-det\" style=\"display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)\"><div style=\"margin-bottom:12px;font-weight:600;font-size:16px\">WhatsApp Log - ${s.student_name||id}</div>${(s.messages||[]).map(m=>(m.from==='user'?'<strong style=\"color:var(--green)\">Student:</strong> ':'<strong style=\"color:var(--purple)\">Asha:</strong> ')+(m.body||m.text||'')).join('<br><br>')||'Conversation active'}</div></div>`).join('');};'''
text = re.sub(wa_pattern, new_wa, text, flags=re.DOTALL)

# 5. Replace loadAdminSummary
summary_pattern = r'window\.loadAdminSummary=async function\(\)\{.*?\};'
new_summary = r'''window.loadAdminSummary=async function(){const grid=document.getElementById('admin-summary-grid');if(!grid)return;const d=await apiA('/api/students?limit=24');
const atRisk = (d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
document.querySelector('.summary-count').textContent = atRisk.length + ' students';
grid.innerHTML = '<div style=\"display:flex;flex-direction:column;gap:8px;width:100%\">' + atRisk.map(s=>{const high=String(s.final_risk_tier).toUpperCase()==='HIGH',score=Number(s.ml_risk_score||0).toFixed(3);return `<div class=\"admin-summary-card\" style=\"border:1px solid var(--border);border-radius:8px;background:var(--surface);cursor:pointer\" data-search=\"${(s.student_name+' '+s.student_id+' '+(s.top_factor_1||'')).toLowerCase()}\">
    <div style=\"padding:16px;display:flex;justify-content:space-between;align-items:center\" onclick=\"const t=this.nextElementSibling;t.style.display=t.style.display==='none'?'block':'none'\">
        <div style=\"font-weight:600;font-size:15px\">${s.student_name}</div>
        <span class=\"tag ${high?'tag-t1':'tag-t2'}\">${s.final_risk_tier} RISK</span>
    </div>
    <div style=\"display:none;padding:0 16px 16px;border-top:1px solid var(--border);margin-top:16px;padding-top:16px;color:var(--text2)\">
        <div style=\"font-size:12px;margin-bottom:8px\"><strong style=\"color:var(--text)\">Student ID:</strong> ${s.student_id}</div>
        <div style=\"font-size:12px;margin-bottom:8px\"><strong style=\"color:var(--text)\">Primary Risk Factor:</strong> ${s.top_factor_1||'N/A'}</div>
        <div style=\"font-size:12px;margin-bottom:8px\"><strong style=\"color:var(--text)\">Risk Score:</strong> ${score}</div>
        <div style=\"font-size:12px;margin-bottom:16px\"><strong style=\"color:var(--text)\">Current Action:</strong> ${s.final_action||'N/A'}</div>
        <button class=\"btn\" onclick=\"showStudent('${s.student_id}')\">View Full Record</button>
    </div>
</div>`}).join('') + '</div>';};'''
text = re.sub(summary_pattern, new_summary, text, flags=re.DOTALL)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Patched successfully!')
