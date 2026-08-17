with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: enrichSummaryCards - hide details and toggle
old_enrich = '''card.innerHTML=`<span class=\"summary-chip ${tier==='HIGH'?'high':'medium'}\">${tier} RISK · SCORE ${score}</span><h3 style=\"margin:12px 0 4px\">${name}</h3><div class=\"summary-copy\">'''
new_enrich = '''card.setAttribute('onclick', "const d1=this.querySelector('.summary-copy'); const d2=this.querySelector('.summary-meta'); const isHidden=d1.style.display==='none'; document.querySelectorAll('.summary-copy').forEach(x=>x.style.display='none'); document.querySelectorAll('.summary-meta').forEach(x=>x.style.display='none'); d1.style.display=isHidden?'block':'none'; d2.style.display=isHidden?'flex':'none';");
card.innerHTML=`<span class=\"summary-chip ${tier==='HIGH'?'high':'medium'}\">${tier} RISK · SCORE ${score}</span><h3 style=\"margin:12px 0 4px\">${name}</h3><div class=\"summary-copy\" style=\"display:none\">'''
content = content.replace(old_enrich, new_enrich)

old_meta = '''<div class=\"summary-meta\">'''
new_meta = '''<div class=\"summary-meta\" style=\"display:none\">'''
content = content.replace(old_meta, new_meta)

# Fix 2: startManualLiveCall - rename Aarav Patel to Student
old_start = '''window.__manualLiveCall={id:uid,name:data.student_name||'Aarav Patel',started:Date.now()};'''
new_start = '''window.__manualLiveCall={id:uid,name:data.student_name||'Student',started:Date.now()};'''
content = content.replace(old_start, new_start)

# Fix 3: renderDummyLiveOperations - update Student to Aarav Patel after 8 seconds
old_manual_var = '''const manual=window.__manualLiveCall;'''
new_manual_var = '''const manual=window.__manualLiveCall;
if(manual && manual.name === 'Student' && Date.now() - manual.started > 8000) { manual.name = 'Aarav Patel'; }'''
content = content.replace(old_manual_var, new_manual_var)

# Fix 4: Fix WhatsApp Bubbles in renderDummyLiveOperations
old_manualChat = '''<article style=\"padding:14px;border:1px solid var(--green);border-radius:10px;margin-bottom:12px\"><div style=\"display:flex;justify-content:space-between;cursor:pointer\" onclick=\"window.toggleTranscript(event, '${followedUp.id}_wa')\"><strong style=\"color:var(--green)\">${followedUp.name}</strong><span class=\"mono\" style=\"font-size:10px;color:var(--text3)\">${followedUp.id} · FOLLOW-UP</span></div><div class=\"transcript-expanded-view\" style=\"display:${isWaExpanded(followedUp.id)?'block':'none'}\" onclick=\"event.stopPropagation()\"><div style=\"font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;\">WhatsApp Conversation</div><div style=\"color:var(--text2); margin-bottom:16px;\">Student: ${followedUp.name} (${followedUp.id})</div><div class=\"speaker ai\">Asha AI <span class=\"time\">10:00 AM</span></div><div>I am connecting you with financial-aid support and a counselor today.</div><div class=\"speaker student\">${followedUp.name.split(' ')[0]} <span class=\"time\">10:15 AM</span></div><div>Thank you, I would really appreciate that.</div></div></article>'''

new_manualChat = '''<article style=\"padding:14px;border:1px solid var(--green);border-radius:10px;margin-bottom:12px\"><div style=\"display:flex;justify-content:space-between;cursor:pointer\" onclick=\"window.toggleTranscript(event, '${followedUp.id}_wa')\"><strong style=\"color:var(--green)\">${followedUp.name}</strong><span class=\"mono\" style=\"font-size:10px;color:var(--text3)\">${followedUp.id} · FOLLOW-UP</span></div><div class=\"transcript-expanded-view\" style=\"display:${isWaExpanded(followedUp.id)?'block':'none'}\" onclick=\"event.stopPropagation()\"><div style=\"font-size:18px; font-weight:600; color:var(--text); margin-bottom:8px;\">WhatsApp Conversation</div><div style=\"color:var(--text2); margin-bottom:16px;\">Student: ${followedUp.name} (${followedUp.id})</div><div class=\"chat-msg assistant\" style=\"margin-bottom:12px;display:flex;justify-content:flex-start\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">🤖 Asha AI</div>I am connecting you with financial-aid support and a counselor today.</div></div><div class=\"chat-msg user\" style=\"margin-bottom:12px;display:flex;justify-content:flex-end\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">${followedUp.name.split(' ')[0]}</div>Thank you, I would really appreciate that.</div></div></div></article>'''
content = content.replace(old_manualChat, new_manualChat)


old_conversationRows = '''<div class=\"speaker ai\">Asha AI <span class=\"time\">10:00 AM</span></div><div>Hi ${s.name.split(' ')[0]}, following up on our call. Have you been able to review the resources I sent over?</div><div class=\"speaker student\">${s.name.split(' ')[0]} <span class=\"time\">10:15 AM</span></div><div>Not yet, I've been busy. ${s.reply}</div><div class=\"speaker ai\">Asha AI <span class=\"time\">10:17 AM</span></div><div>${asha}</div><div class=\"speaker student\">${s.name.split(' ')[0]} <span class=\"time\">10:25 AM</span></div><div>${phase===2?'Yes, that would help.':s.reply}</div>'''

new_conversationRows = '''<div class=\"chat-msg assistant\" style=\"margin-bottom:12px;display:flex;justify-content:flex-start\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">🤖 Asha AI</div>Hi ${s.name.split(' ')[0]}, following up on our call. Have you been able to review the resources I sent over?</div></div><div class=\"chat-msg user\" style=\"margin-bottom:12px;display:flex;justify-content:flex-end\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">${s.name.split(' ')[0]}</div>Not yet, I've been busy. ${s.reply}</div></div><div class=\"chat-msg assistant\" style=\"margin-bottom:12px;display:flex;justify-content:flex-start\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--surface2);color:var(--text);border-bottom-left-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">🤖 Asha AI</div>${asha}</div></div><div class=\"chat-msg user\" style=\"margin-bottom:12px;display:flex;justify-content:flex-end\"><div class=\"chat-bubble\" style=\"max-width:75%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.4;background:var(--blue-g);color:var(--blue);border-bottom-right-radius:4px\"><div style=\"font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px\">${s.name.split(' ')[0]}</div>${phase===2?'Yes, that would help.':s.reply}</div></div>'''
content = content.replace(old_conversationRows, new_conversationRows)

# Fix 5: Change renderDummyLiveOperations to save to a global variable instead of overwriting, 
# and update the actual loadTranscripts and loadWAConvos functions to append the dummy variables!
old_set_panels = '''['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel)panel.innerHTML=transcriptRows;});'''
new_set_panels = '''window.__dummyTranscriptRows = transcriptRows;
['full-transcript-panel','transcript-panel','admin-transcript-panel'].forEach(id=>{
  const panel=document.getElementById(id);
  if(panel && !panel.innerHTML.includes('border-bottom:1px solid #333') && !panel.innerHTML.includes('style=\"padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer\"')) {
     panel.innerHTML=transcriptRows;
  }
});
'''
content = content.replace(old_set_panels, new_set_panels)

old_set_wa = '''['wa-convos-panel','admin-wa-panel'].forEach(id=>{const panel=document.getElementById(id);if(panel)panel.innerHTML=conversationRows;});'''
new_set_wa = '''window.__dummyWaRows = conversationRows;
['wa-convos-panel','admin-wa-panel'].forEach(id=>{
  const panel=document.getElementById(id);
  if(panel && !panel.innerHTML.includes('class=\"chat-bubble\"') && !panel.innerHTML.includes('style=\"padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:10px;cursor:pointer\"')) {
     panel.innerHTML=conversationRows;
  }
});
'''
content = content.replace(old_set_wa, new_set_wa)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done patching')
