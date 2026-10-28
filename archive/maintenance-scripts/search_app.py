import sys
try:
    with open('voice_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open('out_voice.txt', 'w', encoding='utf-8') as out:
        for i, line in enumerate(lines):
            if 'def voice_welcome' in line:
                out.write(f"Found voice_welcome at line {i+1}\n")
except Exception as e:
    with open('out_voice.txt', 'w', encoding='utf-8') as out:
        out.write(str(e))
