import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Extract the `page-overview` from ADMIN_DASHBOARD
admin_overview_match = re.search(r'<!-- OVERVIEW -->(.+?)<!-- STUDENTS -->', content, re.DOTALL)
if admin_overview_match:
    admin_overview_html = admin_overview_match.group(1).strip()
else:
    print("Could not find admin overview")
    exit(1)

# Replace the topbar actions in the copied overview to include Counselor actions
new_actions = """<div class="topbar-actions">
        <div class="top-search">
            <svg viewBox="0 0 24 24" style="width:16px;height:16px;stroke:var(--text3);fill:none;stroke-width:2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" placeholder="Search students, ID, or keyword...">
        </div>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px" onclick="demoCall()">&#x1f4de; Call Student</button>
        <button class="nav-cta" style="display:flex;align-items:center;gap:6px;background:var(--green)" onclick="waDemo()">&#x1f4ac; WhatsApp Demo</button>
        <button class="btn" onclick="runAnalysis()">&#x1f9e0; Analyze Calls</button>
        <button class="btn" onclick="exportCSV()">&#x1f4e5; Export CSV</button>
    </div>"""

admin_overview_html = re.sub(r'<div class="topbar-actions">.*?</div>\s*</div>', new_actions + '\n  </div>', admin_overview_html, flags=re.DOTALL)
# Also change ID to page-dashboard to match counselor navigation
admin_overview_html = admin_overview_html.replace('id="page-overview"', 'id="page-dashboard"')


# 2. Extract the `page-dashboard` from COUNSELOR_DASHBOARD
counselor_dashboard_match = re.search(r'<!-- COUNSELOR DASHBOARD -->.*?<div class="page active" id="page-dashboard">(.+?)</div>\s*<!-- AT-RISK STUDENTS -->', content, re.DOTALL)
if not counselor_dashboard_match:
    print("Could not find counselor dashboard")
    exit(1)

counselor_dashboard_full = f'<!-- COUNSELOR DASHBOARD -->\n{admin_overview_html}\n'

# Wait, the counselor dashboard has other elements: Live Call Transcripts, Voice Analysis Results. We should keep them, maybe at the bottom of the overview.
transcripts_html = """
  <div class="grid-3" style="margin-top:16px;">
      <div class="card-new" style="grid-column: span 1;">
        <div class="card-new-h"><h3>Live Call Transcripts</h3><span class="b" id="ts-count" style="font-size:12px;color:var(--text3)">0 active</span></div>
        <div class="card-new-b" id="transcript-panel" style="background:#0a0a0a;color:#0f0;padding:12px;border-radius:4px;font-family:var(--mono);font-size:11px;min-height:200px;max-height:250px;overflow-y:auto;white-space:pre-wrap;">Waiting for active calls...</div>
      </div>
      <div class="card-new" style="grid-column: span 2;">
        <div class="card-new-h"><h3>Voice Analysis Results</h3><span class="b" id="analysis-count" style="font-size:12px;color:var(--text3)">-</span></div>
        <div style="overflow-x:auto;padding:16px;">
          <table class="act-table"><thead><tr><th style="text-align:left;padding-bottom:8px">Student</th><th style="text-align:left;padding-bottom:8px">Score</th><th style="text-align:left;padding-bottom:8px">Intent</th><th style="text-align:left;padding-bottom:8px">Prob</th><th style="text-align:left;padding-bottom:8px">Root Cause</th><th style="text-align:left;padding-bottom:8px">Sentiment</th></tr></thead>
          <tbody id="analysis-tbody"><tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text3)">Run a demo call + analyze to see results</td></tr></tbody></table>
        </div>
      </div>
  </div>
</div>
"""
admin_overview_html = admin_overview_html.replace('</div>\n</div>', '</div>\n' + transcripts_html)

content = content.replace(counselor_dashboard_match.group(0), f'<!-- COUNSELOR DASHBOARD -->\n{admin_overview_html}\n\n<!-- AT-RISK STUDENTS -->')


# 3. Update JS in COUNSELOR_DASHBOARD loadAnalysis to format table like act-table
old_loadAnalysis_row = """return `<tr>
          <td><span style="font-weight:500;color:var(--text)">${r.spoken_name || r.student_name || r.student_id}</span></td>
          <td><span class="mono">${score.toFixed(2)}</span></td>
          <td><span class="tag tag-${icls}">${intent}</span></td>
          <td><span class="mono">${prob.toFixed(2)}</span></td>
          <td style="font-size:11px;color:var(--text2);text-transform:capitalize">${r.primary_root_cause||'-'}</td>
          <td style="font-size:11px;color:var(--text2);text-transform:capitalize">${r.overall_sentiment||'-'}</td>
        </tr>`;"""
new_loadAnalysis_row = """return `<tr>
          <td style="padding:12px 16px"><span style="font-weight:600;color:var(--text)">${r.spoken_name || r.student_name || r.student_id}</span></td>
          <td style="padding:12px 16px"><span class="mono">${score.toFixed(2)}</span></td>
          <td style="padding:12px 16px"><span class="tag tag-${icls}">${intent}</span></td>
          <td style="padding:12px 16px"><span class="mono">${prob.toFixed(2)}</span></td>
          <td style="padding:12px 16px;font-size:11px;color:var(--text2);text-transform:capitalize">${r.primary_root_cause||'-'}</td>
          <td style="padding:12px 16px;font-size:11px;color:var(--text2);text-transform:capitalize">${r.overall_sentiment||'-'}</td>
        </tr>`;"""
content = content.replace(old_loadAnalysis_row, new_loadAnalysis_row)

# 4. Update the startAutomatedDemo JS logic
# It should fast forward (lower timeout) and have blinking emoji.
# It should show a popup at the end and redirect to `/`.
demo_js_start = content.find('async function startAutomatedDemo() {')
if demo_js_start != -1:
    demo_js_end = content.find('}\n</script>', demo_js_start)
    old_demo_js = content[demo_js_start:demo_js_end+1]
    
    new_demo_js = """async function startAutomatedDemo() {
    const floatBtn = document.createElement('div');
    floatBtn.innerHTML = '<button class="btn btn-red" style="padding:12px 24px;height:auto;font-size:14px;box-shadow:0 0 20px rgba(239,68,68,0.5);font-weight:700" onclick="window.location.href=\'/\'">End Demo</button>';
    floatBtn.style.position = 'fixed';
    floatBtn.style.bottom = '24px';
    floatBtn.style.left = '50%';
    floatBtn.style.transform = 'translateX(-50%)';
    floatBtn.style.zIndex = '9999';
    document.body.appendChild(floatBtn);

    // Simulate clicking call student
    toast('Simulating: Clicked "Call Student"...', 'info');
    await new Promise(r => setTimeout(r, 1000));
    
    document.querySelector('[data-page="voice"]').click();
    await new Promise(r => setTimeout(r, 1000));
    
    const tp = document.getElementById('transcript-panel');
    if(tp) {
        document.getElementById('ts-count').innerText = '1 active';
        let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px">
            <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
            <span style="color:#888">Name verified: Demo Student</span><br>`;
        tp.innerHTML = html + `</div>`;
        
        const qas = [
            {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
            {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
            {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
        ];
        
        for (const qa of qas) {
            await new Promise(r => setTimeout(r, 500));
            html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
            tp.innerHTML = html + `</div>`;
            tp.scrollTop = tp.scrollHeight;
            
            await new Promise(r => setTimeout(r, 500));
            let typed = "";
            // Blinking fast-forward emoji
            html += `<span style="color:var(--green)">🗣️ </span>`;
            
            for (let i = 0; i < qa.a.length; i++) {
                typed += qa.a[i];
                let blink = (i % 4 < 2) ? " ⏩" : ""; // Blinking effect
                tp.innerHTML = html.replace('🗣️ </span>', `🗣️ ${typed}${blink}</span></div>`);
                tp.scrollTop = tp.scrollHeight;
                await new Promise(r => setTimeout(r, 10)); // FAST FORWARD
            }
            html = html.replace('🗣️ </span>', `🗣️ ${qa.a}</span><br>`);
            tp.innerHTML = html + `</div>`;
        }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    toast('Call completed. Generating AI insights...', 'info');
    await new Promise(r => setTimeout(r, 1500));
    
    // Final Summary popup FIRST
    const summaryPop = document.createElement('div');
    summaryPop.innerHTML = `
      <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:32px;z-index:10000;box-shadow:0 0 64px rgba(0,0,0,0.8);text-align:center;width:400px">
        <h2 style="font-size:24px;margin-bottom:16px;color:var(--text)">Live Demo Ended</h2>
        <div style="background:var(--surface2);border-radius:8px;padding:16px;text-align:left;margin-bottom:24px">
            <h4 style="font-size:12px;color:var(--text3);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">AI Final Summary</h4>
            <p style="font-size:14px;color:var(--text);line-height:1.5">Demo Student is experiencing high financial stress due to a reduced scholarship, leading to low confidence in degree completion. Recommended action: Fast-track financial aid advising.</p>
        </div>
        <p style="font-size:13px;color:var(--text2);margin-bottom:24px">Switching to WhatsApp follow-up in 5 seconds...</p>
      </div>
      <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:9999" id="summary-backdrop"></div>
    `;
    document.body.appendChild(summaryPop);
    
    // Wait exactly 5 seconds
    await new Promise(r => setTimeout(r, 5000));
    
    // Remove the popup
    summaryPop.remove();

    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1000));
    let convosPanel = document.getElementById('wa-convos-panel');
    if(convosPanel) {
        let demoHtml = `
          <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
            <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)">
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
        if(convosPanel.innerHTML.includes('No conversations')) {
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
            await new Promise(r => setTimeout(r, 20)); // FAST FORWARD
        }
    }
}"""
    content = content.replace(old_demo_js, new_demo_js)
else:
    print("Could not find startAutomatedDemo")
    exit(1)

# 5. Speed up polling of loadAnalysis
setInterval_old = "setInterval(()=>{loadDashboard();loadAnalysis();loadWAConvos();},15000);"
setInterval_new = "setInterval(()=>{loadDashboard();loadAnalysis();loadWAConvos();},3000);"
content = content.replace(setInterval_old, setInterval_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Counselor dashboard patched successfully!")
