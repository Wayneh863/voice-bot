"""
Twilio Voice Bot — IVR, voicemail, call forwarding, speech recognition.
Deploy to Railway/Render/Fly.io or run locally with ngrok.
"""
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial, Record, Say, Play
from twilio.rest import Client

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")          # Your Twilio number (+1xxx)
FORWARD_NUMBER = os.getenv("FORWARD_NUMBER")        # Where to forward "press 2"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")        # Optional: AI responses

client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None

# ─── Helpers ─────────────────────────────────────────────────────────────
def twiml(resp: VoiceResponse) -> Response:
    """Return TwiML with correct content type."""
    return Response(str(resp), mimetype="application/xml")

# ─── Routes ──────────────────────────────────────────────────────────────
@app.route("/voice", methods=["POST"])
def voice():
    """Direct to AI assistant — no menu."""
    resp = VoiceResponse()
    resp.redirect("/ai")
    return twiml(resp)


@app.route("/menu", methods=["POST"])
def menu():
    """Handle menu selection."""
    digit = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").lower()
    resp = VoiceResponse()

    # Normalize speech to digit
    if not digit and speech:
        if any(w in speech for w in ["1", "one", "hour"]):
            digit = "1"
        elif any(w in speech for w in ["2", "two", "support", "agent", "human"]):
            digit = "2"
        elif any(w in speech for w in ["3", "three", "message", "voicemail"]):
            digit = "3"
        elif any(w in speech for w in ["4", "four", "ai", "assistant", "bot"]):
            digit = "4"

    if digit == "1":
        resp.say(
            "We are open Monday through Friday, 9 AM to 5 PM Eastern. "
            "Closed weekends and holidays.",
            voice="Polly.Brian",
        )
        resp.redirect("/voice")

    elif digit == "2":
        if FORWARD_NUMBER:
            resp.say("Connecting you to support. Please hold.", voice="Polly.Brian")
            dial = Dial(
                caller_id=TWILIO_NUMBER,
                timeout=30,
                record="record-from-answer",
                recording_status_callback="/recording",
            )
            dial.number(FORWARD_NUMBER)
            resp.append(dial)
        else:
            resp.say("Support forwarding not configured.", voice="Polly.Brian")
            resp.redirect("/voice")

    elif digit == "3":
        resp.say("Leave your message after the beep. Press any key to finish.", voice="Polly.Brian")
        resp.record(
            max_length=120,
            play_beep=True,
            action="/voicemail",
            method="POST",
            transcribe=True,
            transcribe_callback="/transcription",
        )

    elif digit == "4":
        if OPENAI_API_KEY:
            resp.say("Connecting you to our AI assistant.", voice="Polly.Brian")
            resp.redirect("/ai")
        else:
            resp.say("AI assistant not configured.", voice="Polly.Brian")
            resp.redirect("/voice")

    else:
        resp.say("Invalid selection.", voice="Polly.Brian")
        resp.redirect("/voice")

    return twiml(resp)


@app.route("/voicemail", methods=["POST"])
def voicemail():
    """Voicemail recorded — save/notify."""
    recording_url = request.form.get("RecordingUrl")
    duration = request.form.get("RecordingDuration")
    from_num = request.form.get("From")

    # TODO: Save to DB, email, Slack, etc.
    print(f"📞 Voicemail from {from_num}: {recording_url} ({duration}s)")

    resp = VoiceResponse()
    resp.say("Thank you. Your message has been saved. Goodbye.", voice="Polly.Brian")
    return twiml(resp)


@app.route("/transcription", methods=["POST"])
def transcription():
    """Voicemail transcription callback."""
    text = request.form.get("TranscriptionText")
    recording_url = request.form.get("RecordingUrl")
    from_num = request.form.get("From")
    print(f"📝 Transcription from {from_num}: {text}")
    # TODO: Store/forward transcription
    return "", 200


@app.route("/recording", methods=["POST"])
def recording():
    """Call recording callback (from Dial)."""
    recording_url = request.form.get("RecordingUrl")
    call_sid = request.form.get("CallSid")
    print(f"🎙️ Call recording {call_sid}: {recording_url}")
    return "", 200


# ─── AI Assistant (Optional) ─────────────────────────────────────────────
@app.route("/ai", methods=["POST"])
def ai_start():
    """Start AI conversation loop."""
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/ai/process",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        timeout=8,
    )
    gather.say("Hi! I'm your AI assistant. What can I help with?", voice="Polly.Brian")
    resp.append(gather)
    resp.redirect("/ai")
    return twiml(resp)


@app.route("/ai/process", methods=["POST"])
def ai_process():
    """Process speech → Hermes API → respond."""
    import requests

    user_speech = request.form.get("SpeechResult", "")
    call_sid = request.form.get("CallSid")

    if not user_speech:
        resp = VoiceResponse()
        resp.say("I didn't catch that.", voice="Polly.Brian")
        resp.redirect("/ai")
        return twiml(resp)

    # Call Hermes API (same model, full tool access)
    hermes_url = os.getenv("HERMES_API_URL", "https://hermes-api-production-acf3f0d9.up.railway.app")
    try:
        response = requests.post(
            f"{hermes_url}/chat",
            json={"message": user_speech},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ai_reply = data.get("response", "Done")
        
        # Execute any actions (call, sms, email)
        for action in data.get("actions", []):
            if action["type"] == "call":
                # Make outgoing call via Twilio
                if client and TWILIO_NUMBER:
                    try:
                        call = client.calls.create(
                            to=action["to"],
                            from_=TWILIO_NUMBER,
                            twiml=f"<Response><Say voice='Polly.Brian'>{action.get('message', 'Hello from Hermes')}</Say></Response>"
                        )
                        print(f"Outgoing call initiated: {call.sid} to {action['to']}")
                    except Exception as e:
                        print(f"Call error: {e}")
            elif action["type"] == "sms":
                # Send SMS via Twilio
                if client and TWILIO_NUMBER:
                    try:
                        msg = client.messages.create(
                            to=action["to"],
                            from_=TWILIO_NUMBER,
                            body=action.get("body", "Message from Hermes")
                        )
                        print(f"SMS sent: {msg.sid} to {action['to']}")
                    except Exception as e:
                        print(f"SMS error: {e}")
            elif action["type"] == "email":
                # Send email (placeholder - would need SMTP config)
                print(f"EMAIL to {action['to']}: {action.get('subject', '')} - {action.get('body', '')}")
                
    except Exception as e:
        print(f"Hermes API error: {e}")
        ai_reply = "Sorry, I'm having trouble thinking right now."

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/ai/process",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        timeout=8,
    )
    gather.say(ai_reply, voice="Polly.Brian")
    resp.append(gather)
    resp.redirect("/ai")
    return twiml(resp)


# ─── SMS Webhook (Optional) ──────────────────────────────────────────────
@app.route("/sms", methods=["POST"])
def sms():
    """Handle incoming SMS."""
    from twilio.twiml.messaging_response import MessagingResponse

    body = request.form.get("Body", "").strip()
    from_num = request.form.get("From")

    resp = MessagingResponse()
    if "help" in body.lower():
        resp.message("Reply STOP to unsubscribe. Text HOURS for hours. Text SUPPORT to request a callback.")
    elif "hours" in body.lower():
        resp.message("Mon-Fri 9AM-5PM ET. Closed weekends.")
    elif "support" in body.lower():
        resp.message("We'll call you back within 1 business hour.")
        # TODO: Create callback task
    else:
        resp.message(f"Thanks for your message: '{body}'. Text HELP for options.")
    return Response(str(resp), mimetype="application/xml")


# ─── Health Check ────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "voice-bot"}


# ─── Entrypoint ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")