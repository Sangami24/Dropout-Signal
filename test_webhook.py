import urllib.request
import urllib.parse
data = urllib.parse.urlencode({'CallSid': 'CA123'}).encode('ascii')
req = urllib.request.Request('http://localhost:5000/voice/welcome?student_id=2847&student_name=Demo', data=data)
try:
    with urllib.request.urlopen(req) as response:
        print("Status:", response.status)
        print("Body:", response.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
