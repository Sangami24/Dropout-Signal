# Dropout Signal — Startup Instructions

When you close the project and open it again, follow these steps to start the application properly.

## Step 1: Start the Tunnel (Terminal 1)
You need to expose your local server to the internet so Twilio can reach it for voice calls and WhatsApp.

```bash
python scripts/operations/start_tunnel.py
```
*This updates both `WEBHOOK_BASE_URL` and `WHATSAPP_WEBHOOK_URL` in `.env` automatically and prints the Twilio Sandbox settings link.*

## Step 2: Update the Webhook URL
Every time you run tunnelmole, it gives you a **new** URL. `scripts/operations/start_tunnel.py` writes both values to `.env` for you:

```
WEBHOOK_BASE_URL=https://<your-new-url>.tunnelmole.net
WHATSAPP_WEBHOOK_URL=https://<your-new-url>.tunnelmole.net/whatsapp/webhook
```

It also prints the direct [Twilio WhatsApp Sandbox Settings](https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox) link. Paste `WHATSAPP_WEBHOOK_URL` into “When a message comes in.”

## Step 3: Start the Flask App (Terminal 2)
Now start the main application server.

```bash
python app.py
```

If the app was already running when the tunnel URL changed, stop it and run this command again so it reloads `.env`.

## Step 4: Access the Dashboards
Open your browser and navigate to:
- **Landing Page:** `http://localhost:5000`
- **Login:** `http://localhost:5000/login`

**Credentials:**
- Admin: `admin` / `admin123`
- Counselor: `counselor` / `counselor123`
