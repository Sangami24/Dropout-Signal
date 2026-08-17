import sys
with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
with open('routes.txt', 'w', encoding='utf-8') as f:
    for i, line in enumerate(lines):
        if 'app.route' in line or 'def ' in line:
            f.write(f'{i+1}: {line}')
