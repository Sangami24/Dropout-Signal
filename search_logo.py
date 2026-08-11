with open('app.py', encoding='utf-8') as f:
    text = f.read()
    import re
    with open('logo_search.txt', 'w', encoding='utf-8') as out:
        for m in re.finditer(r'Dropout Signal', text, re.IGNORECASE):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            line_num = text.count(chr(10), 0, m.start()) + 1
            out.write(f'{line_num}: {text[start:end]}\n')
