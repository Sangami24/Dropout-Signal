import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv('.env')

account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
phone_number = os.environ.get('TWILIO_PHONE_NUMBER')
webhook_url = os.environ.get('WEBHOOK_BASE_URL')

if not all([account_sid, auth_token, phone_number, webhook_url]):
    print("Missing Twilio credentials or webhook URL in .env")
    exit(1)

client = Client(account_sid, auth_token)

# Find the phone number by friendly name or phone number
numbers = client.incoming_phone_numbers.list(phone_number=phone_number)
if not numbers:
    print(f"Phone number {phone_number} not found in your Twilio account.")
    exit(1)

tw_number = numbers[0]
voice_url = f"{webhook_url}/voice"

print(f"Updating Twilio Phone Number {phone_number} Voice Webhook to: {voice_url}")

updated_number = client.incoming_phone_numbers(tw_number.sid).update(
    voice_url=voice_url,
    voice_method='POST'
)

print("Successfully updated Twilio Voice Webhook!")
print("The 'Application Error' should now be fixed.")
