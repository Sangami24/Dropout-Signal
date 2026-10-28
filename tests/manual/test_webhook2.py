import requests
import os
try:
    res = requests.post("http://127.0.0.1:5000/voice/welcome", data={"CallSid":"12345", "To":"+123456"}, params={"student_id":"STU-123", "student_name":"Aarav", "ml_risk":"0.87"})
    out_path = r"C:\Users\achal\.gemini\antigravity-ide\brain\2fc8e66d-a61f-46b1-82b0-0ec7ae991bc7\scratch\test_out.txt"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(str(res.status_code) + "\n" + res.text)
except Exception as e:
    out_path = r"C:\Users\achal\.gemini\antigravity-ide\brain\2fc8e66d-a61f-46b1-82b0-0ec7ae991bc7\scratch\test_out.txt"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(str(e))
