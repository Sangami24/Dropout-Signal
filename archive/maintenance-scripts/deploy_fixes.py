import os
import subprocess

# 1. Run direct_patch.py to fix app.py
print("Running direct_patch.py...")
subprocess.run(["python", "direct_patch.py"])

# 2. Fix voice_server.py
print("Fixing voice_server.py...")
with open("voice_server.py", "r", encoding="utf-8") as f:
    voice_content = f.read()

# Replace the greeting to NOT ask for name
old_greeting = """    resp.say(
        "Before we begin, could you please tell me your name?",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )"""

new_greeting = """    # We already know their name from the dashboard, no need to ask
    pass"""

voice_content = voice_content.replace(old_greeting, new_greeting)

# Update the initial current_question in the session
old_q = '"current_question": "Before we begin, could you please tell me your name?"'
new_q = '"current_question": "How has this semester been going for you so far?"'
voice_content = voice_content.replace(old_q, new_q)

# Fix the first question numbering
# The first question is "How has this semester been going for you so far?"
# When we ask the question, we shouldn't say "Question 1."
# Let's just find and replace it if it's there.
# Wait, actually we can just look for the place where it says f"Question {question_index}."
old_question_speech = 'question_speech = f"Question {question_index}. {question_text}"'
new_question_speech = 'question_speech = f"{question_text}"'
voice_content = voice_content.replace(old_question_speech, new_question_speech)

with open("voice_server.py", "w", encoding="utf-8") as f:
    f.write(voice_content)

print("Committing and pushing...")
os.system("git add app.py voice_server.py")
os.system("git commit -m \"Fix voice server to not ask for name and fix dashboard popup\"")
os.system("git push")
print("Done!")
