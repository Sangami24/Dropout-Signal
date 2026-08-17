import re
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add window.__hasActiveSessions flag to loadAdminTranscripts and loadAdminWhatsApp
content = content.replace("if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyTranscripts||'Waiting for active calls...';", "if(Object.keys(sessions).length===0){window.__hasActiveSessions=false;p.innerHTML=window.__dummyTranscripts||'Waiting for active calls...';")
content = content.replace("document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';", "window.__hasActiveSessions=true;document.getElementById('admin-ts-count').textContent=Object.keys(sessions).length+' active';")

content = content.replace("if(Object.keys(sessions).length===0){p.innerHTML=window.__dummyWaRows||'WhatsApp conversations appear here.';", "if(Object.keys(sessions).length===0){window.__hasActiveWaSessions=false;p.innerHTML=window.__dummyWaRows||'WhatsApp conversations appear here.';")
content = content.replace("document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';", "window.__hasActiveWaSessions=true;document.getElementById('admin-wa-badge').textContent=Object.keys(sessions).length+' conversations';")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
