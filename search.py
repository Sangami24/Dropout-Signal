with open('app.py', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'donut' in line.lower() or 'chart' in line.lower() or 'tier' in line.lower():
            print(f'{i+1}: {line.strip()[:100]}')
