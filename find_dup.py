with open("voice_server.py", "r", encoding="utf-8") as f:
    text = f.read()
idx1 = text.find("def voice_welcome")
idx2 = text.find("def voice_welcome", idx1 + 1)
with open("out_dup_utf8.txt", "w", encoding="utf-8") as out:
    out.write(f"Index 1: {idx1}\n")
    out.write(f"Index 2: {idx2}\n")
    if idx2 != -1:
        out.write(text[idx2-50:idx2+200])
