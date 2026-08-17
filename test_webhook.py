import requests
try:
    res = requests.post("http://127.0.0.1:5000/voice/welcome", data={"CallSid":"12345", "To":"+123456"}, params={"student_id":"STU-123", "student_name":"Aarav", "ml_risk":"0.87"})
    with open("test_out.txt", "w", encoding="utf-8") as f:
        f.write(str(res.status_code) + "\n" + res.text)
except Exception as e:
    with open("test_out.txt", "w", encoding="utf-8") as f:
        f.write(str(e))
