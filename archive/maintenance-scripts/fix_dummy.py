import re
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix dummy live operations DOM updates
new_assignment = """    window.__dummyTranscripts=transcriptRows;
    ['full-transcript-panel', 'transcript-panel', 'admin-transcript-panel'].forEach(id => {
        const el = document.getElementById(id);
        if (el && (!window.__hasActiveSessions)) el.innerHTML = transcriptRows;
    });"""

content = content.replace("    window.__dummyTranscripts=transcriptRows;", new_assignment)

new_wa_assignment = """    window.__dummyWaRows=conversationRows;
    ['wa-convos-panel', 'admin-wa-panel'].forEach(id => {
        const el = document.getElementById(id);
        if (el && (!window.__hasActiveWaSessions)) el.innerHTML = conversationRows;
    });"""

content = content.replace("    window.__dummyWaRows=conversationRows;", new_wa_assignment)

# Also fix the transcript screen size (make it larger, not 75%)
content = content.replace(
    "#page-transcript .card, #page-admin-transcript .card, #page-admin-whatsapp .card, #page-whatsapp .card { max-width: 75%; margin: 0 auto; }",
    "#page-transcript .card, #page-admin-transcript .card, #page-admin-whatsapp .card, #page-whatsapp .card { max-width: 90%; margin: 0 auto; min-height: 70vh; }"
)
content = content.replace(
    "width:75%;margin-left:auto;margin-right:auto;",
    "width:95%;margin-left:auto;margin-right:auto;"
)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
