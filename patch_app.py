import sys
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update /counselor route to handle demo=true
old_counselor_route = """@app.route("/counselor")
def counselor_dashboard():
    if session.get("role") != "counselor":
        return redirect("/login")
    return render_template_string(COUNSELOR_DASHBOARD)"""
new_counselor_route = """@app.route("/counselor")
def counselor_dashboard():
    if request.args.get("demo") == "true":
        session["user"] = "counselor"
        session["role"] = "counselor"
    elif session.get("role") != "counselor":
        return redirect("/login")
    return render_template_string(COUNSELOR_DASHBOARD)"""
content = content.replace(old_counselor_route, new_counselor_route)

# 2. Add watchDemo function to LANDING_HTML
if "function watchDemo()" not in content:
    landing_script = """<script>
function watchDemo() {
    window.location.href = '/counselor?demo=true';
}
</script>
</body>"""
    content = content.replace("</body>", landing_script, 1)

# 3. Update loadWAConvos to use nice chat interface
old_loadWAConvos = """async function loadWAConvos(){
  try{
    const d=await api('/whatsapp/conversations');
    document.getElementById('wa-count-badge').textContent=d.total+' conversations';
    document.getElementById('sb-wa-count').textContent=d.total||0;
    const panel=document.getElementById('wa-convos-panel');
    if(!d.conversations||!d.conversations.length){panel.innerHTML='<p style="color:var(--text3);font-size:12px">No conversations yet.</p>';return;}
    panel.innerHTML=d.conversations.map((c,i)=>`
      <div class="card" style="margin-bottom:8px;cursor:pointer" onclick="this.querySelector('.chat-box').style.display=this.querySelector('.chat-box').style.display==='none'?'block':'none'">
        <div class="card-h">
          <span class="t" style="color:var(--green)">${c.profile_name||c.student_name||c.phone}</span>
          <span class="b">${c.message_count} msgs | ${c.risk_level}</span>
        </div>
        <div class="chat-box" style="display:none;margin:0 12px 12px"></div>
      </div>
    `).join('');
  }catch(e){toast('Failed to load conversations','err');}
}"""
new_loadWAConvos = """async function loadWAConvos(){
  try{
    const d=await api('/whatsapp/conversations');
    document.getElementById('wa-count-badge').textContent=d.total+' conversations';
    document.getElementById('sb-wa-count').textContent=d.total||0;
    const panel=document.getElementById('wa-convos-panel');
    if(!d.conversations||!d.conversations.length){panel.innerHTML='<p style="color:var(--text3);font-size:12px">No conversations yet.</p>';return;}
    
    d.conversations.sort((a,b) => {
        if((a.profile_name||a.student_name||'').toLowerCase().includes('demo')) return -1;
        if((b.profile_name||b.student_name||'').toLowerCase().includes('demo')) return 1;
        return 0;
    });

    panel.innerHTML=d.conversations.map((c,i)=>`
      <div class="card" style="margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)">
        <div class="card-h" style="cursor:pointer;background:rgba(255,255,255,0.02)" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
          <span class="t" style="color:var(--green)">${c.profile_name||c.student_name||c.phone}</span>
          <span class="b">${c.message_count} msgs | ${c.risk_level}</span>
        </div>
        <div class="chat-box" style="display:${i===0?'block':'none'};margin:12px;background:#0d0d12;border:1px solid var(--border);border-radius:8px;padding:16px;max-height:400px;overflow-y:auto">
          ${c.messages.map(m=>`
            <div class="chat-msg ${m.role==='user'?'user':''}" style="margin-bottom:12px;display:flex;${m.role==='user'?'justify-content:flex-end':''}">
               <div class="chat-bubble ${m.role}" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;${m.role==='user'?'background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px':'background:var(--surface2);color:var(--text);border-bottom-left-radius:4px'}">
                 <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${m.role==='user'?(c.profile_name||c.student_name||'Student'):'🤖 Asha AI'}</div>
                 ${m.content}
               </div>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  }catch(e){toast('Failed to load conversations','err');}
}"""
content = content.replace(old_loadWAConvos, new_loadWAConvos)

# 4. Add startAutomatedDemo to COUNSELOR_DASHBOARD script
automated_demo_script = """const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('demo') === 'true') {
    startAutomatedDemo();
}

async function startAutomatedDemo() {
    const floatBtn = document.createElement('div');
    floatBtn.innerHTML = '<button class="btn btn-red" style="padding:12px 24px;height:auto;font-size:14px;box-shadow:0 0 20px rgba(239,68,68,0.5);font-weight:700" onclick="window.location.href=\'/\'">End Demo</button>';
    floatBtn.style.position = 'fixed';
    floatBtn.style.bottom = '24px';
    floatBtn.style.left = '50%';
    floatBtn.style.transform = 'translateX(-50%)';
    floatBtn.style.zIndex = '9999';
    document.body.appendChild(floatBtn);

    toast('Starting automated demo...', 'info');
    
    document.querySelector('[data-page="voice"]').click();
    
    await new Promise(r => setTimeout(r, 1500));
    
    const tp = document.getElementById('transcript-panel');
    if(!tp) return;
    
    const qas = [
        {q: "How has this semester been going for you so far?", a: "It's been really tough this semester, I've been struggling with the workload"},
        {q: "What has been the most challenging part of college life recently?", a: "Definitely the financial pressure, my scholarship got reduced"},
        {q: "On a scale of 1 to 5, how confident are you about completing your degree?", a: "I'd say maybe a 3, I'm not super confident right now"}
    ];
    
    document.getElementById('ts-count').innerText = '1 active';
    
    let html = `<div style="margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:12px">
        <strong style="color:var(--blue)">📞 Call: Demo Student (STU-DEMO)</strong><br>
        <span style="color:#888">Name verified: Demo Student</span><br>`;
        
    tp.innerHTML = html + `</div>`;
    
    for (const qa of qas) {
        await new Promise(r => setTimeout(r, 2000));
        html += `<br><span style="color:var(--amber)">🤖 ${qa.q}</span><br>`;
        tp.innerHTML = html + `</div>`;
        tp.scrollTop = tp.scrollHeight;
        
        await new Promise(r => setTimeout(r, 1500));
        let typed = "";
        html += `<span style="color:var(--green)">🗣️ `;
        tp.innerHTML = html + `</span><br></div>`;
        tp.scrollTop = tp.scrollHeight;
        
        for (let i = 0; i < qa.a.length; i++) {
            typed += qa.a[i];
            tp.innerHTML = html + typed + `</span><br></div>`;
            tp.scrollTop = tp.scrollHeight;
            await new Promise(r => setTimeout(r, 30));
        }
        html += qa.a + `</span><br>`;
    }
    
    await new Promise(r => setTimeout(r, 2000));
    toast('Call completed. Generating AI insights...', 'info');
    await new Promise(r => setTimeout(r, 3000));
    
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();
    
    await new Promise(r => setTimeout(r, 1500));
    let convosPanel = document.getElementById('wa-convos-panel');
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
    // clear the loading text if it's there
    if(convosPanel.innerHTML.includes('No conversations')) {
        convosPanel.innerHTML = '';
    }
    convosPanel.innerHTML = demoHtml + convosPanel.innerHTML;
    
    await new Promise(r => setTimeout(r, 2000));
    const replyDiv = document.getElementById('demo-student-reply');
    let replyText = "Hi, yeah things have been a bit rough lately with the finances";
    let currentReply = `<div class="chat-bubble user" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
               <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">Demo Student</div>`;
               
    for (let i = 0; i < replyText.length; i++) {
        replyDiv.innerHTML = currentReply + replyText.substring(0, i + 1) + `</div>`;
        await new Promise(r => setTimeout(r, 40));
    }
    
    toast('Demo completed.', 'ok');
}
</script>"""
content = content.replace("</script>\n</body></html>", automated_demo_script + "\n</body></html>")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated app.py successfully!")
