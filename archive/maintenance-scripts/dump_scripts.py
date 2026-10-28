import codecs
import re

with codecs.open('app.py', 'r', 'utf-8') as f:
    text = f.read()

# Try to find all inline scripts
matches = re.finditer(r'<script.*?>([\s\S]*?)</script>', text, re.IGNORECASE)
with codecs.open('all_scripts.txt', 'w', 'utf-8') as out:
    for i, m in enumerate(matches):
        out.write(f'--- SCRIPT {i} ---\n')
        out.write(m.group(1))
        out.write('\n\n')

# Find adminInitiateCall
idx = text.find('adminInitiateCall')
with codecs.open('admin_call_pos.txt', 'w', 'utf-8') as out:
    if idx != -1:
        out.write(f'Found adminInitiateCall at index {idx}\n')
        out.write(text[max(0, idx-500):idx+2500])
    else:
        out.write('Not found')
