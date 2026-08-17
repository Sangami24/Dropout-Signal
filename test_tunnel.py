import urllib.request
import os

with open('.env', 'r') as f:
    for line in f:
        if line.startswith('WEBHOOK_BASE_URL='):
            url = line.strip().split('=')[1]
            break

try:
    req = urllib.request.Request(url + "/voice/welcome", method="POST")
    res = urllib.request.urlopen(req)
    msg = f"Status: {res.status}\n"
except urllib.error.HTTPError as e:
    msg = f"HTTP Error: {e.code}\n{e.read().decode()}"
except Exception as e:
    msg = f"Exception: {str(e)}"

out_path = r"C:\Users\achal\.gemini\antigravity-ide\brain\2fc8e66d-a61f-46b1-82b0-0ec7ae991bc7\scratch\tunnel_test.txt"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w') as f:
    f.write(f"URL: {url}\n{msg}")
