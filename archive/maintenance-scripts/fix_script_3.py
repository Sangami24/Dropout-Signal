import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. AI Summary Details Hidden
text = re.sub(
    r'card\.dataset\.enriched=\'1\';card\.innerHTML=`<span class=\"summary-chip',
    r'''card.dataset.enriched='1';
card.setAttribute('onclick', "const d1=this.querySelector('.summary-copy'); const d2=this.querySelector('.summary-meta'); const isHidden=d1.style.display==='none'; document.querySelectorAll('.summary-copy').forEach(x=>x.style.display='none'); document.querySelectorAll('.summary-meta').forEach(x=>x.style.display='none'); d1.style.display=isHidden?'block':'none'; d2.style.display=isHidden?'flex':'none';");
card.innerHTML=`<span class=\"summary-chip''',
    text
)
text = text.replace('<div class="summary-copy">AI synthesis:', '<div class="summary-copy" style="display:none">AI synthesis:')
text = text.replace('<div class="summary-meta"><span>Attendance', '<div class="summary-meta" style="display:none"><span>Attendance')


# 2. 'Student' -> 'Aarav Patel' transition
text = text.replace("name:data.student_name||'Aarav Patel'", "name:data.student_name||'Student'")
text = text.replace('const manual=window.__manualLiveCall;', "const manual=window.__manualLiveCall; if(manual && manual.name==='Student' && Date.now() - manual.started > 8000){manual.name='Aarav Patel';}")


# 3. WhatsApp chat bubbles for dummy data
wa_dummy_match = re.search(r'const conversationRows=(.*?)`\)\.join\(\'\'\);', text, re.DOTALL)
if wa_dummy_match:
    wa_code = wa_dummy_match.group(0)
    wa_code = wa_code.replace(
        '''<div class="speaker ai">Asha AI <span class="time">10:00 AM</span></div><div>Hi ${s.name.split(' ')[0]}, following up on our call. Have you been able to review the resources I sent over?</div><div class="speaker student">${s.name.split(' ')[0]} <span class="time">10:15 AM</span></div><div>Not yet, I've been busy. ${s.reply}</div><div class="speaker ai">Asha AI <span class="time">10:17 AM</span></div><div>${asha}</div><div class="speaker student">${s.name.split(' ')[0]} <span class="time">10:25 AM</span></div><div>${phase===2?'Yes, that would help.':s.reply}</div>''',
        '''
        <div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
            Hi ${s.name.split(' ')[0]}, following up on our call. Have you been able to review the resources I sent over?
          </div>
        </div>
        <div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${s.name.split(' ')[0]}</div>
            Not yet, I've been busy. ${s.reply}
          </div>
        </div>
        <div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
            ${asha}
          </div>
        </div>
        <div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${s.name.split(' ')[0]}</div>
            ${phase===2?'Yes, that would help.':s.reply}
          </div>
        </div>
        '''.replace('\n', '')
    )
    
    wa_code = wa_code.replace(
        '''<div class="speaker ai">Asha AI <span class="time">10:00 AM</span></div><div>I am connecting you with financial-aid support and a counselor today.</div><div class="speaker student">${followedUp.name.split(' ')[0]} <span class="time">10:15 AM</span></div><div>Thank you, I would really appreciate that.</div>''',
        '''
        <div class="chat-msg assistant" style="margin-bottom:12px;display:flex;justify-content:flex-start">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">🤖 Asha AI</div>
            I am connecting you with financial-aid support and a counselor today.
          </div>
        </div>
        <div class="chat-msg user" style="margin-bottom:12px;display:flex;justify-content:flex-end">
          <div class="chat-bubble" style="max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px">${followedUp.name.split(' ')[0]}</div>
            Thank you, I would really appreciate that.
          </div>
        </div>
        '''.replace('\n', '')
    )
    text = text.replace(wa_dummy_match.group(0), wa_code)


# 4. Expose dummy html globally and prevent overwriting
text = text.replace(
    "['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel)panel.innerHTML=transcriptRows;});",
    "window.__dummyTranscripts = transcriptRows; ['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel && !panel.innerHTML.includes('border-bottom:1px solid var(--border);padding-bottom:12px'))panel.innerHTML=transcriptRows;});"
)

text = text.replace(
    "['wa-convos-panel','admin-wa-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel)panel.innerHTML=conversationRows;});",
    "window.__dummyWaRows = conversationRows; ['wa-convos-panel','admin-wa-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel && !panel.innerHTML.includes('chat-bubble') && !panel.innerHTML.includes('wa-student-card'))panel.innerHTML=conversationRows;});"
)


# 5. Append dummy HTML to actual loadTranscripts and loadWAConvos
# loadTranscripts:
text = text.replace(
    'tp.innerHTML=html;\n    if(isScrolledToBottom)',
    'tp.innerHTML=html + (window.__dummyTranscripts || \'\');\n    if(isScrolledToBottom)'
)

# loadWAConvos:
text = text.replace(
    '''wp.innerHTML = html;
          
          wp.querySelectorAll('.wa-student-card').forEach(card => {''',
    '''wp.innerHTML = html + (window.__dummyWaRows || '');
          
          wp.querySelectorAll('.wa-student-card').forEach(card => {'''
)
text = text.replace(
    '''} else {
          wp.innerHTML = html;
          wp.querySelectorAll('.chat-box').forEach(box => {''',
    '''} else {
          wp.innerHTML = html + (window.__dummyWaRows || '');
          wp.querySelectorAll('.chat-box').forEach(box => {'''
)


with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Patched successfully!')
