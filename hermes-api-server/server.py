#!/usr/bin/env python3
"""
Hermes API Server - Simple version that works on Railway.
Uses only stdlib + basic logic (no subprocess).
"""

import os
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

# ─── Models ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    stream: bool = False

class ToolCall(BaseModel):
    tool: str
    args: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None

class Action(BaseModel):
    type: str  # "call", "sms", "email"
    to: str
    message: Optional[str] = None
    body: Optional[str] = None
    subject: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)
    session_id: str

# ─── Global State ──────────────────────────────────────────────────────────

sessions: Dict[str, List[Dict]] = {}

# ─── Core Logic (uses only stdlib + simple logic) ──────────────────────────

async def process_message(message: str, session_id: str) -> ChatResponse:
    """Process a message with basic logic and action detection."""
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    history = sessions[session_id]
    history.append({"role": "user", "content": message})
    
    # Simple response logic with action detection
    msg_lower = message.lower()
    actions = []
    
    # Check for call action
    if "call" in msg_lower:
        import re
        numbers = re.findall(r'\+?1?\d{10}', message)
        if numbers:
            actions.append(Action(
                type="call",
                to=numbers[0],
                message="Hello from Hermes"
            ))
    
    # Check for SMS action
    if "text" in msg_lower or "sms" in msg_lower:
        import re
        numbers = re.findall(r'\+?1?\d{10}', message)
        if numbers:
            actions.append(Action(
                type="sms",
                to=numbers[0],
                body=message
            ))
    
    # Check for email action
    if "email" in msg_lower:
        import re
        emails = re.findall(r'[\w\.-]+@[\w\.-]+', message)
        if emails:
            actions.append(Action(
                type="email",
                to=emails[0],
                subject="Message from Hermes",
                body=message
            ))
    
    # Build response
    if "who are you" in msg_lower:
        response_text = "I'm Hermes, your AI assistant with full tool access. I can search the web, read files, run code, make calls, send texts, and emails."
    elif "weather" in msg_lower:
        response_text = "I don't have real-time weather access, but I can search for it if you tell me your location."
    elif "time" in msg_lower:
        from datetime import datetime
        response_text = f"The current time is {datetime.now().strftime('%I:%M %p')}."
    elif actions:
        response_text = f"Got it. Taking {len(actions)} action(s)."
    else:
        response_text = f"I understand: {message}. How can I help?"
    
    history.append({"role": "assistant", "content": response_text})
    
    return ChatResponse(
        response=response_text,
        tool_calls=[],
        actions=actions,
        session_id=session_id
    )

# ─── FastAPI App ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Hermes API Server starting...")
    yield
    print("🛑 Hermes API Server stopping...")

app = FastAPI(title="Hermes API", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-api", "sessions": len(sessions)}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    return await process_message(request.message, session_id)

# ─── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("HERMES_API_PORT", "8080"))
    host = os.getenv("HERMES_API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)