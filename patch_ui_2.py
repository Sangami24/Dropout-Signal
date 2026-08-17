import re
import sys

def main():
    with open('app.py', 'r', encoding='utf-8') as f:
        text = f.read()

    # 1. Change Admin Counselor to Counselor
    text = text.replace('Admin Counselor', 'Counselor')

    # 2. Fix loadStudents to use student_name and load 4500 students
    old_load_students = "const d=await api('/api/students?search='+encodeURIComponent(q)),rows=d.students||[];document.getElementById('student-count-badge').textContent=d.total?d.total.toLocaleString()+' records':rows.length+' records';body.innerHTML=rows.length?rows.map(s=>`<tr><td class=\"mono\"><strong>${s.student_id}</strong></td><td class=\"mono\">${Number(s.ml_risk_score||0).toFixed(3)}</td>"
    new_load_students = "const d=await api('/api/students?limit=4500&search='+encodeURIComponent(q)),rows=d.students||[];document.getElementById('student-count-badge').textContent=d.total?d.total.toLocaleString()+' records':rows.length+' records';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class=\"mono\" style=\"color:var(--text3);font-size:10px\">${s.student_id}</span></td><td class=\"mono\">${Number(s.ml_risk_score||0).toFixed(3)}</td>"
    if old_load_students in text:
        text = text.replace(old_load_students, new_load_students)
    else:
        print("Warning: loadStudents replacement not found")

    # 3. Fix loadAdminTranscripts to cover 3/4 width, unique names, no demo
    old_load_ts = "p.innerHTML=Object.values(sessions).map(s=>`<div style=\"padding:14px 0;border-bottom:1px solid var(--border);cursor:pointer\" onclick=\"const t=this.querySelector('.det');t.style.display=t.style.display==='none'?'block':'none'\"><strong style=\"color:var(--blue)\">☎ ${s.student_name} (${s.student_id})</strong><div class=\"det\" style=\"display:none;margin-top:8px;color:var(--text3)\">${Object.values(s.answers||{}).map(a=>'Q: '+a.question+'<br>A: '+a.text).join('<br><br>')||'Listening for response...'}</div></div>`).join('');"
    new_load_ts = r"""const filteredSessions = Object.values(sessions).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredSessions.map(s=>`<div style="padding:14px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="document.querySelectorAll('.ts-det').forEach(x=>{if(x!==this.querySelector('.ts-det'))x.style.display='none'});const t=this.querySelector('.ts-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--blue)">☎ ${s.student_name} (${s.student_id})</strong><div class="ts-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">Live Transcript</div>${Object.values(s.answers||{}).map(a=>'<strong style="color:var(--purple)">AI:</strong> '+a.question+'<br><strong style="color:var(--green)">Student:</strong> '+a.text).join('<br><br>')||'Listening for response...'}</div></div>`).join('');"""
    if old_load_ts in text:
        text = text.replace(old_load_ts, new_load_ts)
    else:
        print("Warning: loadAdminTranscripts replacement not found")

    # 4. Fix loadAdminWhatsApp to behave similarly
    old_load_wa = "p.innerHTML=Object.entries(sessions).map(([id,s])=>`<div style=\"padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer\" onclick=\"const t=this.querySelector('.det');t.style.display=t.style.display==='none'?'block':'none'\"><strong style=\"color:var(--green)\">${s.student_name||id}</strong><div class=\"det\" style=\"display:none;margin-top:7px;color:var(--text2);font-size:12px\">${(s.messages||[]).map(m=>(m.from==='user'?'Student: ':'Asha: ')+(m.body||m.text||'')).join('<br><br>')||'Conversation active'}</div></div>`).join('');"
    new_load_wa = r"""const filteredWA = Object.entries(sessions).filter(([id, s]) => id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
    p.innerHTML=filteredWA.map(([id,s])=>`<div style="padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer" onclick="document.querySelectorAll('.wa-det').forEach(x=>{if(x!==this.querySelector('.wa-det'))x.style.display='none'});const t=this.querySelector('.wa-det');t.style.display=t.style.display==='none'?'block':'none'"><strong style="color:var(--green)">${s.student_name||id}</strong><div class="wa-det" style="display:none;margin-top:16px;color:var(--text);width:75%;margin-left:auto;margin-right:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,0.12)"><div style="margin-bottom:12px;font-weight:600;font-size:16px">WhatsApp Log</div>${(s.messages||[]).map(m=>(m.from==='user'?'<strong style="color:var(--green)">Student:</strong> ':'<strong style="color:var(--purple)">Asha:</strong> ')+(m.body||m.text||'')).join('<br><br>')||'Conversation active'}</div></div>`).join('');"""
    if old_load_wa in text:
        text = text.replace(old_load_wa, new_load_wa)
    else:
        print("Warning: loadAdminWhatsApp replacement not found")

    # 5. Fix loadAdminSummary to show names as list, expand on click
    old_load_summary = "grid.innerHTML=(d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).slice(0,20).map(s=>{const high=String(s.final_risk_tier).toUpperCase()==='HIGH',score=Number(s.ml_risk_score||0).toFixed(3);return `<article class=\"summary-person admin-summary-card\" style=\"cursor:pointer\" onclick=\"showStudent('${s.student_id}')\" data-search=\"${(s.student_name+' '+s.student_id+' '+(s.top_factor_1||'')).toLowerCase()}\"><span class=\"summary-chip ${high?'high':'medium'}\">${s.final_risk_tier} RISK · SCORE ${score}</span><h3 style=\"margin:12px 0 4px\">${s.student_name}</h3></article>`}).join('')};"
    new_load_summary = r"""const atRisk = (d.students||[]).filter(s=>['HIGH','MEDIUM'].includes(String(s.final_risk_tier||'').toUpperCase())).filter(s => s.student_id !== 'STU-DEMO' && s.student_name !== 'Aarav Patel');
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
    </div>`}).join('') + '</div>';};"""
    if old_load_summary in text:
        text = text.replace(old_load_summary, new_load_summary)
    else:
        print("Warning: loadAdminSummary replacement not found")

    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Done")

if __name__ == "__main__":
    main()
