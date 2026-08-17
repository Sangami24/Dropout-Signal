import urllib.request
try:
    with open('status.txt', 'w') as f:
        f.write(str(urllib.request.urlopen("http://127.0.0.1:5000/").status))
except Exception as e:
    with open('status.txt', 'w') as f:
        f.write(str(e))
