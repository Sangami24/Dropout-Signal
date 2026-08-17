import urllib.request
import traceback
try:
    req = urllib.request.urlopen('http://localhost:5000/admin')
    html = req.read().decode('utf-8')
    with open('out3.txt', 'w', encoding='utf-8') as f:
        f.write(html)
except Exception as e:
    with open('out3.txt', 'w', encoding='utf-8') as f:
        f.write(traceback.format_exc())
