with open('app.py', encoding='utf-8') as f:
    with open('results.txt', 'w', encoding='utf-8') as out:
        for i, line in enumerate(f):
            if 'dropout signal' in line.lower() or 'logout' in line.lower() or 'main' in line.lower() or 'admin-logout' in line.lower() or 'sidebar' in line.lower():
                out.write(f'{i+1}: {line.strip()[:100]}\n')
