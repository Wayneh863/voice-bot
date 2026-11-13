#!/usr/bin/env python3
"""
Hermes API Server - Exposes Hermes as HTTP API for external clients.
Uses execute_code for full tool access.
"""

import os
import json
import uuid
import asyncio
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

# ─── Execute Code Helper ───────────────────────────────────────────────────

async def run_hermes_code(code: str) -> Dict:
    """Run code in Hermes execute_code environment."""
    # This will be called from the API server
    # We need to communicate with the Hermes kernel
    import subprocess
    import sys
    
    # Write code to temp file and run with hermes python
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_path = f.name
    
    try:
        # Run with the Hermes kernel python
        result = subprocess.run([
            sys.executable, '-c', 
            f"import sys; sys.path.insert(0, '/opt/data/cache/scratch/hermes_kernel_9_k4twqb'); exec(open('{temp_path}').read())"
        ], capture_output=True, text=True, timeout=60, cwd='/opt/data')
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass

# ─── Core Logic ────────────────────────────────────────────────────────────

async def process_message(message: str, session_id: str) -> ChatResponse:
    """Process a message through Hermes with full tool access."""
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    history = sessions[session_id]
    history.append({"role": "user", "content": message})
    
    # Build code to execute in Hermes environment
    hermes_code = f'''
import json
from hermes_tools import terminal, web_search, web_extract, read_file, write_file, search_files, patch

# Session history
history = {json.dumps(history)}

# Process message: "{message}"
# For now, just use available tools to respond
response_text = "I received your message: {message}"

# Check for action triggers
msg_lower = "{message.lower()}"
actions = []

if "call" in msg_lower:
    import re
    numbers = re.findall(r'\\+?1?\\d{{10}}', "{message}")
    if numbers:
        actions.append({{"type": "call", "to": numbers[0], "message": "Hello from Hermes"}})

if "text" in msg_lower or "sms" in msg_lower:
    import re
    numbers = re.findall(r'\\+?1?\\d{{10}}', "{message}")
    if numbers:
        actions.append({{"type": "sms", "to": numbers[0], "body": "{message}"}})

if "email" in msg_lower:
    import re
    emails = re.findall(r'[\\w\\.-]+@[\\w\\.-]+', "{message}")
    if emails:
        actions.append({{"type": "email", "to": emails[0], "subject": "Message from Hermes", "body": "{message}"}})

if actions:
    response_text += f" — Taking {{len(actions)}} action(s)."

# Output result as JSON
result = {{
    "response": response_text,
    "actions": actions
}}
print(json.dumps(result))
'''
    
    result = await run_hermes_code(hermes_code)
    
    if result["returncode"] != 0:
        return ChatResponse(
            response=f"Error processing message: {result['stderr']}",
            tool_calls=[],
            actions=[],
            session_id=session_id
        )
    
    try:
        data = json.loads(result["stdout"].strip())
        response_text = data.get("response", "Done")
        actions_data = data.get("actions", [])
        
        actions = [Action(**a) for a in actions_data]
        
        history.append({"role": "assistant", "content": response_text})
        
        return ChatResponse(
            response=response_text,
            tool_calls=[],
            actions=actions,
            session_id=session_id
        )
    except Exception as e:
        return ChatResponse(
            response=f"Error parsing result: {e}",
            tool_calls=[],
            actions=[],
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