#!/usr/bin/env python3
"""
ElevenLabs TTS Server - Hosts audio files for Twilio.
Run alongside the voice bot.
"""

import os
import uuid
import hashlib
import base64
import requests
from flask import Flask, request, send_file, jsonify
import tempfile
import atexit
import shutil

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
BASE_URL = os.getenv("BASE_URL", "https://your-domain.com")  # Set this to your public URL

# Temp directory for audio files
AUDIO_DIR = tempfile.mkdtemp(prefix="elevenlabs_tts_")
print(f"Audio cache dir: {AUDIO_DIR}")

# Cache: text_hash -> filename
audio_cache = {}

def cleanup():
    shutil.rmtree(AUDIO_DIR, ignore_errors=True)

atexit.register(cleanup)

# ─── ElevenLabs TTS ──────────────────────────────────────────────────────

def generate_audio(text: str, voice_id: str = None) -> str:
    """Generate audio file and return local filename."""
    if not ELEVENLABS_API_KEY:
        return None
    
    vid = voice_id or ELEVENLABS_VOICE_ID
    
    # Create cache key
    cache_key = hashlib.md5(f"{text}:{vid}".encode()).hexdigest()
    if cache_key in audio_cache:
        return audio_cache[cache_key]
    
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
        resp = requests.post(url, json=data, headers=headers, timeout=15)
        if resp.status_code == 200:
            filename = f"{cache_key}.mp3"
            filepath = os.path.join(AUDIO_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            audio_cache[cache_key] = filename
            return filename
    except Exception as e:
        print(f"ElevenLabs TTS error: {e}")
    return None

# ─── Routes ──────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return {"status": "ok", "cached_files": len(audio_cache)}

@app.route("/tts", methods=["POST"])
def tts():
    """Generate TTS and return audio URL."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    voice_id = data.get("voice_id")
    
    if not text:
        return jsonify({"error": "text required"}), 400
    
    filename = generate_audio(text, voice_id)
    if not filename:
        return jsonify({"error": "TTS generation failed"}), 500
    
    audio_url = f"{BASE_URL}/audio/{filename}"
    return jsonify({"audio_url": audio_url, "filename": filename})

@app.route("/audio/<filename>")
def serve_audio(filename):
    """Serve cached audio file."""
    filepath = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Not found"}), 404
    return send_file(filepath, mimetype="audio/mpeg")

@app.route("/tts/direct", methods=["POST"])
def tts_direct():
    """Generate and return audio directly (for testing)."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    voice_id = data.get("voice_id")
    
    if not text:
        return jsonify({"error": "text required"}), 400
    
    filename = generate_audio(text, voice_id)
    if not filename:
        return jsonify({"error": "TTS generation failed"}), 500
    
    filepath = os.path.join(AUDIO_DIR, filename)
    return send_file(filepath, mimetype="audio/mpeg")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    # Use gunicorn in production for better performance
    import sys
    if os.getenv("RAILWAY_ENVIRONMENT") == "production":
        os.execvpe("gunicorn", ["gunicorn", "--bind", f"0.0.0.0:{port}", "--workers", "2", "--threads", "4", "--timeout", "60", "tts_server:app"], os.environ)
    else:
        app.run(host="0.0.0.0", port=port, debug=False)