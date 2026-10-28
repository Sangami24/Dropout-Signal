import os

with open("voice_server.py", "r", encoding="utf-8") as f:
    text = f.read()

# Replace the voice_welcome route completely
old_welcome = """@app.route("/voice/welcome", methods=["POST"])
def voice_welcome():
    \"\"\"
    Twilio webhook: the student picked up the phone.
    We introduce the agent and ask for their name.
    \"\"\"
    call_sid = request.form.get("CallSid", "")
    student_id = request.args.get("student_id", "unknown")
    student_name = request.args.get("student_name", "Student")
    ml_risk = request.args.get("ml_risk", "0.0")

    # Create session for this call
    sessions[call_sid] = {
        "student_id": student_id,
        "student_name": student_name,
        "ml_risk_score": float(ml_risk),
        "phone": request.form.get("To", ""),
        "call_sid": call_sid,
        "answers": {},
        "current_question": "Before we begin, could you please tell me your name?",
        "started_at": datetime.now().isoformat(),
    }

    print(f"🎙️  Call answered: {student_name} (#{student_id})")

    resp = VoiceResponse()

    # Welcome — positioned as routine wellness check-in
    resp.say(
        f"Hello! This is {UNIVERSITY_NAME}'s Student Wellness team. "
        f"We're doing a quick 3 minute check-in with students this semester.",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )

    resp.pause(length=1)

    resp.say(
        "Before we begin, could you please tell me your name?",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )
    gather = Gather(
        input="speech",
        language=SPEECH_LANGUAGE,
        speech_timeout="auto",
        timeout=10,
        action=f"{WEBHOOK_BASE_URL}/voice/name?sid={call_sid}",
        method="POST",
    )
    resp.append(gather)

    # Fallback if no speech detected
    resp.redirect(
        f"{WEBHOOK_BASE_URL}/voice/name?sid={call_sid}&nospeech=1",
        method="POST",
    )

    return str(resp), 200, {"Content-Type": "text/xml"}"""

new_welcome = """@app.route("/voice/welcome", methods=["POST"])
def voice_welcome():
    call_sid = request.form.get("CallSid", "")
    student_id = request.args.get("student_id", "unknown")
    student_name = request.args.get("student_name", "Student")
    ml_risk = request.args.get("ml_risk", "0.0")

    first_name = student_name.split()[0] if student_name else "Student"

    # Create session for this call
    sessions[call_sid] = {
        "student_id": student_id,
        "student_name": student_name,
        "ml_risk_score": float(ml_risk),
        "phone": request.form.get("To", ""),
        "call_sid": call_sid,
        "answers": {},
        "current_question": QUESTIONS[0],
        "started_at": datetime.now().isoformat(),
        "spoken_name": first_name
    }

    print(f"🎙️  Call answered: {student_name} (#{student_id})")

    resp = VoiceResponse()

    resp.say(
        f"Hello {first_name}, I am your AI agent from the Student Wellness team. "
        f"I have a few questions for you today.",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )

    resp.pause(length=1)

    resp.say(
        f"{QUESTIONS[0]}",
        voice=TWILIO_VOICE,
        language=TWILIO_LANGUAGE,
    )
    gather = Gather(
        input="speech",
        language=SPEECH_LANGUAGE,
        speech_timeout="auto",
        timeout=10,
        action=f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}",
        method="POST",
    )
    resp.append(gather)

    # Fallback if no speech detected
    resp.redirect(
        f"{WEBHOOK_BASE_URL}/voice/respond?q=0&sid={call_sid}&nospeech=1",
        method="POST",
    )

    return str(resp), 200, {"Content-Type": "text/xml"}"""

text = text.replace(old_welcome, new_welcome)

# Also fix the "Question N" numbering in voice_respond
old_question_speech = 'f"Question {next_q + 1}. {QUESTIONS[next_q]}"'
new_question_speech = 'f"{QUESTIONS[next_q]}"'
text = text.replace(old_question_speech, new_question_speech)

with open("voice_server.py", "w", encoding="utf-8") as f:
    f.write(text)

print("File voice_server.py updated.")
os.system("git add voice_server.py")
os.system("git commit -m \"Fix name question skipping and question numbering\"")
os.system("git push")
print("Changes pushed successfully.")
