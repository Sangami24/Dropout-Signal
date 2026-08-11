import codecs
import re

with codecs.open('app.py', 'r', 'utf-8') as f:
    text = f.read()

changes = 0

old_1 = '<div class="login-title">The Dropout Signal</div>'
new_1 = '<div class="login-title">Dropout Signal</div>'
if old_1 in text:
    text = text.replace(old_1, new_1)
    changes += 1

old_2 = '<div class="sb-name">The Dropout Signal</div>'
new_2 = '<div class="sb-name">Dropout Signal</div>'
if old_2 in text:
    text = text.replace(old_2, new_2)
    changes += 1

old_3 = '  </div>\n  <a class="admin-logout" href="/logout">&larr; SIGN OUT</a>\n</div>'
new_3 = '  </div>\n</div>\n<a class="admin-logout" href="/logout">&larr; SIGN OUT</a>'
if old_3 in text:
    text = text.replace(old_3, new_3)
    changes += 1

old_4a = 'conic-gradient(var(--red) 0 3.16%,var(--amber) 3.16% 22.61%,var(--green) 22.61% 100%)'
new_4a = 'conic-gradient(#ef4444 0 3.16%,#f59e0b 3.16% 22.61%,#22c55e 22.61% 100%)'
if old_4a in text:
    text = text.replace(old_4a, new_4a)
    changes += 1

old_4b = 'style="background:var(--red)"'
new_4b = 'style="background:#ef4444"'
if old_4b in text:
    text = text.replace(old_4b, new_4b)
    changes += 1

old_4c = 'style="background:var(--amber)"'
new_4c = 'style="background:#f59e0b"'
if old_4c in text:
    text = text.replace(old_4c, new_4c)
    changes += 1

old_4d = 'style="background:var(--green)"'
new_4d = 'style="background:#22c55e"'
if old_4d in text:
    text = text.replace(old_4d, new_4d)
    changes += 1

old_5 = "const colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)',UNKNOWN:'var(--blue)'}"
new_5 = "const colors={HIGH:'#ef4444',MEDIUM:'#f59e0b',LOW:'#22c55e',UNKNOWN:'#3b82f6'}"
if old_5 in text:
    text = text.replace(old_5, new_5)
    changes += 1

old_6 = "colors={HIGH:'var(--red)',MEDIUM:'var(--amber)',LOW:'var(--green)'}"
new_6 = "colors={HIGH:'#ef4444',MEDIUM:'#f59e0b',LOW:'#22c55e'}"
if old_6 in text:
    text = text.replace(old_6, new_6)
    changes += 1

with codecs.open('app.py', 'w', 'utf-8') as f:
    f.write(text)

with codecs.open('fixes.log', 'w', 'utf-8') as f:
    f.write('Changes made: ' + str(changes))
