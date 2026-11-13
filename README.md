# Twilio Voice Bot

Production-ready IVR with voicemail, call forwarding, SMS, and optional AI assistant.

## Features

| Feature | Description |
|---------|-------------|
| **IVR Menu** | DTMF (keypad) + Speech recognition |
| **Voicemail** | Recording + auto-transcription |
| **Call Forwarding** | Press 2 → dials your real number |
| **AI Assistant** | GPT-4o-mini powered voice bot (optional) |
| **SMS Webhook** | Auto-replies, keywords (HELP, HOURS, SUPPORT) |
| **Call Recording** | Full call recording on forwarded calls |

---

## Quick Start (Local + ngrok)

```bash
# 1. Clone & setup
cd /opt/data/voice-bot
cp .env.example .env
# Edit .env with your Twilio credentials

# 2. Install deps
pip install -r requirements.txt

# 3. Run bot
python bot.py
# → Listening on http://localhost:3000

# 4. Expose with ngrok (separate terminal)
ngrok http 3000
# → Copy the HTTPS URL (e.g., https://abc123.ngrok-free.app)

# 5. Configure Twilio
# Console → Phone Numbers → Your Number →
#   Voice webhook: https://abc123.ngrok-free.app/voice
#   SMS webhook:  https://abc123.ngrok-free.app/sms
```

---

## Deploy Free (Railway — Recommended)

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login & init
railway login
railway init

# 3. Add environment variables
railway variables set TWILIO_ACCOUNT_SID=ACxxx
railway variables set TWILIO_AUTH_TOKEN=xxx
railway variables set TWILIO_NUMBER=+15551234567
railway variables set FORWARD_NUMBER=+15559876543
# Optional: railway variables set OPENAI_API_KEY=sk-xxx

# 4. Deploy
railway up
# → Gives you https://your-app.railway.app

# 5. Point Twilio webhooks to Railway URL
```

**Railway free tier:** 500 hrs/mo, auto-SSL, custom domains.

---

## Alternative Deploy Targets

| Platform | Command | Free Tier |
|----------|---------|-----------|
| **Render** | Connect GitHub → Web Service | 750 hrs/mo |
| **Fly.io** | `fly launch && fly deploy` | 3 shared CPU VMs |
| **Twilio Functions** | Paste `bot.py` logic into Console → Functions | Built-in, no server |

---

## Twilio Console Setup Checklist

1. **Buy a number** → Phone Numbers → Manage → Buy (+1, Voice + SMS)
2. **Set webhooks** on that number:
   - **Voice:** `https://your-domain/voice`
   - **SMS:** `https://your-domain/sms`
3. **Verify caller ID** (for forwarding) → Console → Phone Numbers → Verified Caller IDs

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TWILIO_ACCOUNT_SID` | ✅ | Starts with `AC...` |
| `TWILIO_AUTH_TOKEN` | ✅ | From Console → Account → API |
| `TWILIO_NUMBER` | ✅ | Your Twilio number (E.164: `+1555...`) |
| `FORWARD_NUMBER` | ❌ | Where "Press 2" forwards to |
| `OPENAI_API_KEY` | ❌ | Enables AI assistant (menu option 4) |
| `PORT` | ❌ | Default 3000 (Railway sets automatically) |

---

## Customize the IVR

Edit `bot.py` → `voice()` and `menu()` functions:

```python
# Add new menu option
gather.say("Press 5 for billing.")

# In menu():
elif digit == "5":
    resp.say("Billing department. Please hold.")
    dial = Dial(caller_id=TWILIO_NUMBER)
    dial.number("+15551112222")
    resp.append(dial)
```

---

## SMS Keywords

Edit `bot.py` → `sms()` function:

```python
if "billing" in body.lower():
    resp.message("Billing: billing@company.com or 1-800-555-0199")
```

---

## Test Checklist

- [ ] Call Twilio number → hear menu
- [ ] Press 1 → hear hours
- [ ] Press 2 → forwards to your phone
- [ ] Press 3 → leave voicemail → check transcription callback
- [ ] Press 4 → AI responds (if `OPENAI_API_KEY` set)
- [ ] SMS "HELP" → get auto-reply
- [ ] SMS "HOURS" → get hours
- [ ] Check `/health` endpoint returns 200

---

## Logs & Debugging

```bash
# Local
python bot.py  # See Flask logs

# Railway
railway logs

# Twilio Debugger
# Console → Monitor → Logs → Voice / Messaging
```

---

## Cost Estimate (After $15 Trial)

| Item | Monthly |
|------|---------|
| Phone number | $1.15 |
| Incoming call/min | $0.0085 |
| Outgoing call/min | $0.013 |
| SMS | $0.0075 |
| Recording storage | $0.0025/min |
| Transcription | $0.02/min |
| **Typical light use** | **~$3-5/mo** |

---

## License

MIT — Use freely.