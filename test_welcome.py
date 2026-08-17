import urllib.request
import urllib.parse
data = urllib.parse.urlencode({'CallSid':'123','To':'+123'}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/voice/welcome?student_id=STU-123&student_name=Test&ml_risk=0.87', data=data)
out = open("debug_output.txt", "w", encoding="utf-8")
try:
    res = urllib.request.urlopen(req).read().decode()
    out.write(res)
except Exception as e:
    out.write(f"Error: {e}\n")
    if hasattr(e, 'read'):
        out.write(e.read().decode())
out.close()
