import subprocess
import re
import os
import sys

def update_env(new_url):
    env_path = '.env'
    if not os.path.exists(env_path):
        print(f"Creating {env_path}...")
        with open(env_path, 'w') as f:
            f.write(f"WEBHOOK_BASE_URL={new_url}\n")
            f.write(f"WHATSAPP_WEBHOOK_URL={new_url}/whatsapp/webhook\n")
        return

    with open(env_path, 'r') as f:
        lines = f.readlines()

    updated = False
    whatsapp_updated = False
    for i in range(len(lines)):
        if lines[i].startswith('WEBHOOK_BASE_URL='):
            lines[i] = f"WEBHOOK_BASE_URL={new_url}\n"
            updated = True
        elif lines[i].startswith('WHATSAPP_WEBHOOK_URL='):
            lines[i] = f"WHATSAPP_WEBHOOK_URL={new_url}/whatsapp/webhook\n"
            whatsapp_updated = True
    
    if not updated:
        lines.append(f"WEBHOOK_BASE_URL={new_url}\n")
    if not whatsapp_updated:
        lines.append(f"WHATSAPP_WEBHOOK_URL={new_url}/whatsapp/webhook\n")

    with open(env_path, 'w') as f:
        f.writelines(lines)
    whatsapp_url = f"{new_url}/whatsapp/webhook"
    print(f"Successfully updated WEBHOOK_BASE_URL in {env_path} to: {new_url}")
    print(f"Successfully updated WHATSAPP_WEBHOOK_URL in {env_path} to: {whatsapp_url}")
    print("Update Twilio WhatsApp Sandbox here:")
    print("https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox")
    print(f'Paste this in "When a message comes in": {whatsapp_url}')

def start_tunnel():
    print("Starting tunnelmole on port 5000...")
    # Use unbuffered output to catch lines immediately
    process = subprocess.Popen(
        'npx tunnelmole 5000',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    url_pattern = re.compile(r'(https://[\w-]+\.tunnelmole\.net)')
    url_found = False

    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if not url_found:
                match = url_pattern.search(line)
                if match:
                    new_url = match.group(1)
                    update_env(new_url)
                    url_found = True
                    print("Restart python app.py so it loads the new webhook URL.")
    except KeyboardInterrupt:
        print("\nStopping tunnelmole...")
    finally:
        process.terminate()

if __name__ == '__main__':
    start_tunnel()
