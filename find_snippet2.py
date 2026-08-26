with open("voice_server.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
with open("out_snippet_utf8_2.txt", "w", encoding="utf-8") as out:
    for i, line in enumerate(lines):
        if "Before we begin" in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            out.write("".join(lines[start:end]) + "\n---\n")
