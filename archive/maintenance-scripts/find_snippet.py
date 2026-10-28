with open("voice_server.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
with open("out_snippet_utf8.txt", "w", encoding="utf-8") as out:
    for i, line in enumerate(lines):
        if "tell me your name" in line:
            start = max(0, i - 5)
            end = min(len(lines), i + 10)
            out.write("".join(lines[start:end]))
            break
