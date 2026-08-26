with open("voice_server.py", "r", encoding="utf-8") as f:
    text = f.read()
with open("out_check_utf8.txt", "w", encoding="utf-8") as out:
    out.write(str("tell me your name" in text.lower()) + "\n")
    out.write(str("how has this semester been going" in text.lower()) + "\n")
