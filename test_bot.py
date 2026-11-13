#!/usr/bin/env python3
"""
Quick local test — verifies bot.py imports and TwiML generation.
Run: python test_bot.py
"""
import os
import sys

# Set dummy env for import test
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test")
os.environ.setdefault("TWILIO_NUMBER", "+15551234567")

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot import app
from twilio.twiml.voice_response import VoiceResponse

def test_voice_endpoint():
    """Test /voice returns valid TwiML with Gather."""
    with app.test_client() as client:
        resp = client.post("/voice", data={"CallSid": "test123"})
        assert resp.status_code == 200
        assert resp.mimetype == "application/xml"
        xml = resp.get_data(as_text=True)
        assert "<Gather" in xml
        assert "Welcome" in xml
        print("✅ /voice returns valid TwiML with Gather")

def test_menu_endpoint():
    """Test /menu handles each option."""
    with app.test_client() as client:
        # Option 1: Hours
        resp = client.post("/menu", data={"Digits": "1"})
        xml = resp.get_data(as_text=True)
        assert "9 AM to 5 PM" in xml
        print("✅ /menu digit=1 returns hours")

        # Option 3: Voicemail
        resp = client.post("/menu", data={"Digits": "3"})
        xml = resp.get_data(as_text=True)
        assert "<Record" in xml
        print("✅ /menu digit=3 returns Record")

def test_sms_endpoint():
    """Test /sms returns MessagingResponse."""
    with app.test_client() as client:
        resp = client.post("/sms", data={"Body": "HELP", "From": "+15559999999"})
        assert resp.status_code == 200
        xml = resp.get_data(as_text=True)
        assert "<Message" in xml
        assert "unsubscribe" in xml.lower()
        print("✅ /sms returns valid MessagingResponse")

def test_health_endpoint():
    """Test /health returns JSON."""
    with app.test_client() as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.is_json
        data = resp.get_json()
        assert data["status"] == "ok"
        print("✅ /health returns {'status': 'ok'}")

def test_twiml_generation():
    """Test VoiceResponse builds correctly."""
    resp = VoiceResponse()
    resp.say("Test", voice="Polly.Brian")
    xml = str(resp)
    assert "<Say" in xml
    assert "Polly.Brian" in xml
    print("✅ VoiceResponse generates valid TwiML")

if __name__ == "__main__":
    print("Running bot tests...\n")
    test_twiml_generation()
    test_voice_endpoint()
    test_menu_endpoint()
    test_sms_endpoint()
    test_health_endpoint()
    print("\n🎉 All tests passed!")