import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'ADMIN_DASHBOARD = r?"""(.*?)"""', text, re.DOTALL)
if match:
    with open('out_admin.txt', 'w', encoding='utf-8') as f:
        f.write(match.group(1))
    print("Dumped successfully")
else:
    print("ADMIN_DASHBOARD not found")
