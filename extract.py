import marshal

def extract_strings(code_obj):
    strings = []
    if hasattr(code_obj, 'co_consts'):
        for const in code_obj.co_consts:
            if isinstance(const, str):
                strings.append(const)
            elif hasattr(const, 'co_code'):
                strings.extend(extract_strings(const))
    return strings

try:
    with open('__pycache__/app.cpython-314.pyc', 'rb') as f:
        f.read(16)
        code = marshal.load(f)
        strings = extract_strings(code)
        for s in strings:
            if 'ADMIN_DASHBOARD' in s or 'loadStudents' in s:
                if len(s) > 1000:
                    with open('recovered.txt', 'w', encoding='utf-8') as out:
                        out.write(s)
                    print('Recovered huge string to recovered.txt')
                    break
        else:
            with open('recovered.txt', 'w', encoding='utf-8') as out:
                out.write("Not found any string")
except Exception as e:
    with open('recovered.txt', 'w', encoding='utf-8') as out:
        out.write('Error: ' + str(e))
