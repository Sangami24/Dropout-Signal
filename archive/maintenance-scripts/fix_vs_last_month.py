import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = content.replace('<div class="sb-sub">vs last month</div>', '')
new_content = new_content.replace('vs last month', '')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Replaced vs last month successfully.')
