import sys

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = """                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>

    // Health
    const h=await api('/api/health');
    document.getElementById('health-time').textContent=new Date().toLocaleTimeString();
    document.getElementById('health-panel').innerHTML=`
  }catch(e){toast('Analytics failed: '+e,'err');}
}"""

replacement = """                <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
            `;
        }
  }catch(e){console.error('Analytics overview error', e);}
}
window.loadStudents=async function(){const q=document.getElementById('student-search')?.value||'',body=document.getElementById('students-tbody');if(!body)return;body.innerHTML='<tr><td colspan=\"6\" style=\"padding:40px;text-align:center\"><div class=\"loading-spinner\"></div></td></tr>';const d=await api('/api/students?limit=4500&search='+encodeURIComponent(q)),rows=d.students||[];document.getElementById('student-count-badge').textContent=d.total?d.total.toLocaleString()+' records':rows.length+' records';body.innerHTML=rows.length?rows.map(s=>`<tr><td><strong>${s.student_name||'Student'}</strong><br><span class=\"mono\" style=\"color:var(--text3);font-size:10px\">${s.student_id}</span></td><td class=\"mono\">${Number(s.ml_risk_score||0).toFixed(3)}</td><td><span class=\"tag ${s.final_risk_tier==='HIGH'?'tag-t1':s.final_risk_tier==='MEDIUM'?'tag-t2':'tag-t3'}\">${s.final_risk_tier}</span></td><td>${s.top_factor_1||'—'}</td><td><span class=\"tag tag-t3\">${s.outcome_status||'Enrolled'}</span></td><td><button class=\"btn\" onclick=\"showStudent('${s.student_id}')\">View</button></td></tr>`).join(''):'<tr><td colspan=\"6\" style=\"text-align:center;color:var(--text3);padding:30px\">No students found</td></tr>';};
window.loadHistogram=async function(){};"""

if target in text:
    text = text.replace(target, replacement)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Success: Injected loadStudents")
else:
    print("Target not found. Let's try replacing line by line.")
    # fallback
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "    const h=await api('/api/health');" in line:
            print("Found health api at line", i)
            # Replace lines i-2 to i+3
            lines = lines[:i-2] + replacement.split('\n') + lines[i+4:]
            with open('app.py', 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print("Success: Injected loadStudents via fallback")
            sys.exit(0)
