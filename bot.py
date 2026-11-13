#!/usr/bin/env python3
"""
Twilio Voice Bot — Bridge Mode + AI Assistant.
Bridge: You speak → types to me. I type → speaks to you.
"""

import os
import queue
import threading
import time
import requests
from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial, Record, Say, Play
from twilio.rest import Client

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")          # Your Twilio number (+1xxx)
FORWARD_NUMBER = os.getenv("FORWARD_NUMBER")        # Where to forward "press 2"
HERMES_API_URL = os.getenv("HERMES_API_URL", "https://hermes-api-production-acf3f0d9.up.railway.app")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # ElevenLabs TTS
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Default: Adam

client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None

# ─── ElevenLabs TTS Helper ───────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

def elevenlabs_tts(text: str, voice_id: str = None) -> str:
    """Generate speech with ElevenLabs and return base64 data URI.
    Limits text to ~200 chars to keep TwiML under size limits.
    """
    if not ELEVENLABS_API_KEY:
        return None
    
    # Limit text length to keep audio small (~3 seconds max)
    if len(text) > 200:
        text = text[:197] + "..."
    
    vid = voice_id or ELEVENLABS_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        if resp.status_code == 200:
            import base64
            audio_b64 = base64.b64encode(resp.content).decode()
            return f"data:audio/mpeg;base64,{audio_b64}"
    except Exception as e:
        print(f"ElevenLabs TTS error: {e}")
    return None

def say_with_elevenlabs(resp: VoiceResponse, text: str, voice_id: str = None) -> bool:
    """Add ElevenLabs TTS to TwiML response. Returns True if successful."""
    audio_url = elevenlabs_tts(text, voice_id)
    if audio_url:
        resp.play(audio_url)
        return True
    return False

# ─── Bridge Mode State ───────────────────────────────────────────────────
# Queue for messages from you (Hermes) to speak
speech_queue = queue.Queue()
# Store for transcribed speech from caller
transcribed_speech = []
# Lock for thread safety
state_lock = threading.Lock()
# Call tracking
active_calls = {}  # call_sid -> {"mode": "bridge|ai", "last_activity": timestamp}

# ─── Helpers ─────────────────────────────────────────────────────────────
def twiml(resp: VoiceResponse) -> Response:
    """Return TwiML with correct content type."""
    return Response(str(resp), mimetype="application/xml")

# ─── Bridge Mode Endpoints (for you to use) ──────────────────────────────

@app.route("/bridge/speak", methods=["POST"])
def bridge_speak():
    """You POST text here → queued for next caller to hear."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    
    speech_queue.put(text)
    return jsonify({"status": "queued", "queue_size": speech_queue.qsize()})

@app.route("/bridge/next", methods=["GET"])
def bridge_next():
    """Voice bot polls this to get next message to speak (peek, don't consume)."""
    try:
        # Peek at queue without consuming
        with speech_queue.mutex:
            if speech_queue.queue:
                text = speech_queue.queue[0]
                return jsonify({"text": text})
    except:
        pass
    return jsonify({"text": None})

@app.route("/bridge/heard", methods=["POST"])
def bridge_heard():
    """Voice bot posts transcribed speech here for you to read."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    call_sid = data.get("call_sid", "")
    if text:
        with state_lock:
            transcribed_speech.append({
                "text": text,
                "call_sid": call_sid,
                "timestamp": time.time()
            })
    return jsonify({"status": "stored", "total": len(transcribed_speech)})

@app.route("/bridge/read", methods=["GET"])
def bridge_read():
    """You poll this to read what caller said."""
    with state_lock:
        return jsonify({"messages": transcribed_speech[-50:]})  # last 50

@app.route("/bridge/clear", methods=["POST"])
def bridge_clear():
    """Clear stored messages."""
    with state_lock:
        transcribed_speech.clear()
    while not speech_queue.empty():
        speech_queue.get()
    return jsonify({"status": "cleared"})

# ─── Routes ──────────────────────────────────────────────────────────────

@app.route("/voice", methods=["POST"])
def voice():
    """Main entry - choose mode via env or default to bridge."""
    mode = os.getenv("VOICE_MODE", "bridge")  # "bridge" or "ai"
    resp = VoiceResponse()
    
    if mode == "bridge":
        resp.redirect("/bridge/start")
    else:
        resp.redirect("/ai")
    return twiml(resp)

# ─── Bridge Mode ─────────────────────────────────────────────────────────

@app.route("/bridge/start", methods=["POST"])
def bridge_start():
    """Start bridge mode - speak queued message or wait."""
    call_sid = request.form.get("CallSid", "")
    with state_lock:
        active_calls[call_sid] = {"mode": "bridge", "last_activity": time.time()}
    
    resp = VoiceResponse()
    # Check for queued message
    try:
        text = speech_queue.get_nowait()
        if not say_with_elevenlabs(resp, text):
            resp.say(text, voice="Polly.Brian")
    except queue.Empty:
        if not say_with_elevenlabs(resp, "Bridge mode active. Waiting for message."):
            resp.say("Bridge mode active. Waiting for message.", voice="Polly.Brian")
    
    # Listen for speech
    gather = Gather(
        input="speech",
        action="/bridge/listen",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        timeout=10,
    )
    # Empty gather - just listening
    resp.append(gather)
    resp.redirect("/bridge/start")
    return twiml(resp)

@app.route("/bridge/listen", methods=["POST"])
def bridge_listen():
    """Receive transcribed speech from caller."""
    call_sid = request.form.get("CallSid", "")
    user_speech = request.form.get("SpeechResult", "")
    
    with state_lock:
        active_calls[call_sid] = {"mode": "bridge", "last_activity": time.time()}
    
    if user_speech:
        # Store for you to read
        with state_lock:
            transcribed_speech.append({
                "text": user_speech,
                "call_sid": call_sid,
                "timestamp": time.time()
            })
        print(f"📝 Caller said: {user_speech}")
    
    resp = VoiceResponse()
    # Continue listening
    gather = Gather(
        input="speech",
        action="/bridge/listen",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        timeout=10,
    )
    resp.append(gather)
    resp.redirect("/bridge/start")
    return twiml(resp)

# ─── AI Assistant Mode (existing) ────────────────────────────────────────

@app.route("/ai", methods=["POST"])
def ai_start():
    """Start AI conversation loop."""
    call_sid = request.form.get("CallSid", "")
    with state_lock:
        active_calls[call_sid] = {"mode": "ai", "last_activity": time.time()}
    
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/ai/process",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        timeout=8,
    )
    if not say_with_elevenlabs(gather, "Hi! I'm your AI assistant. What can I help with?"):
        gather.say("Hi! I'm your AI assistant. What can I help with?", voice="Polly.Brian")
    resp.append(gather)
    resp.redirect("/ai")
    return twiml(resp)

@app.route("/ai/process", methods=["POST"])
def ai_process():
    """Process speech → Hermes API → respond."""
    import requests

    user_speech = request.form.get("SpeechResult", "")
    call_sid = request.form.get("CallSid", "")

    if not user_speech:
        resp = VoiceResponse()
        resp.say("I didn't catch that.", voice="Polly.Brian")
        resp.redirect("/ai")
        return twiml(resp)

    with state_lock:
        active_calls[call_sid] = {"mode": "ai", "last_activity": time.time()}

    # Call Hermes API
    try:
        response = requests.post(
            f"{HERMES_API_URL}/chat",
            json={"message": user_speech},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ai_reply = data.get("response", "Done")
        
        # Execute any actions (call, sms, email)
        for action in data.get("actions", []):
            if action["type"] == "call":
                if client and TWILIO_NUMBER:
                    try:
                        # Generate ElevenLabs audio for the call message
                        message = action.get('message', 'Hello from Hermes')
                        audio_url = elevenlabs_tts(message)
                        if audio_url:
                            twiml_content = f"<Response><Play>{audio_url}</Play></Response>"
                        else:
                            twiml_content = f"<Response><Say voice='Polly.Brian'>{message}</Say></Response>"
                        
                        call = client.calls.create(
                            to=action["to"],
                            from_=TWILIO_NUMBER,
                            twiml=twiml_content
                        )
                        print(f"Outgoing call initiated: {call.sid} to {action['to']}")
                    except Exception as e:
                        print(f"Call error: {e}")
            elif action["type"] == "sms":
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
    if not say_with_elevenlabs(gather, ai_reply):
        gather.say(ai_reply, voice="Polly.Brian")
    resp.append(gather)
    resp.redirect("/ai")
    return twiml(resp)

# ─── Existing IVR Menu (kept for compatibility) ──────────────────────────

@app.route("/menu", methods=["POST"])
def menu():
    """Handle menu selection."""
    digit = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").lower()
    resp = VoiceResponse()

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
        resp.redirect("/ai")

    else:
        resp.say("Invalid selection.", voice="Polly.Brian")
        resp.redirect("/voice")

    return twiml(resp)

@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.form.get("RecordingUrl")
    duration = request.form.get("RecordingDuration")
    from_num = request.form.get("From")
    print(f"📞 Voicemail from {from_num}: {recording_url} ({duration}s)")

    resp = VoiceResponse()
    resp.say("Thank you. Your message has been saved. Goodbye.", voice="Polly.Brian")
    return twiml(resp)

@app.route("/transcription", methods=["POST"])
def transcription():
    text = request.form.get("TranscriptionText")
    recording_url = request.form.get("RecordingUrl")
    from_num = request.form.get("From")
    print(f"📝 Transcription from {from_num}: {text}")
    return "", 200

@app.route("/recording", methods=["POST"])
def recording():
    recording_url = request.form.get("RecordingUrl")
    call_sid = request.form.get("CallSid")
    print(f"🎙️ Call recording {call_sid}: {recording_url}")
    return "", 200

# ─── SMS Webhook ────────────────────────────────────────────────────────

@app.route("/sms", methods=["POST"])
def sms():
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
    else:
        resp.message(f"Thanks for your message: '{body}'. Text HELP for options.")
    return Response(str(resp), mimetype="application/xml")

# ─── Health Check ────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok", 
        "service": "voice-bot",
        "bridge_queue": speech_queue.qsize(),
        "transcribed_count": len(transcribed_speech),
        "active_calls": len(active_calls)
    }

# ─── Entrypoint ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")