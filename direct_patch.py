import sys

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

demo_js_start = content.find('async function startAutomatedDemo() {')
if demo_js_start != -1:
    demo_js_end = content.find('}\n</script>', demo_js_start)
    old_demo_js = content[demo_js_start:demo_js_end+1]
    
    new_demo_js = """async function startAutomatedDemo() {
    const floatBtn = document.createElement('div');
    floatBtn.innerHTML = '<button class="btn btn-red" style="padding:12px 24px;height:auto;font-size:14px;box-shadow:0 0 20px rgba(239,68,68,0.5);font-weight:700" onclick="window.location.href=\\'/\\'">End Demo</button>';
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
                await new Promise(r => setTimeout(r, 20)); // FAST FORWARD
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
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched app.py successfully!")
else:
    print("Could not find startAutomatedDemo in app.py!")
