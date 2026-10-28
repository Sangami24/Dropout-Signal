with open('app.py', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'dropout signal' in line.lower() or 'logout' in line.lower() or 'main' in line.lower():
            print(f'{i+1}: {line.strip()[:100]}')
