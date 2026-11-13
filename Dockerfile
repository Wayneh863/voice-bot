# Twilio Voice Bot / Hermes API / TTS Server — Multi-stage Docker build
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Also install Hermes API requirements
COPY hermes-api-server/requirements.txt /tmp/hermes-requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/hermes-requirements.txt

# Also install TTS server requirements
COPY tts_server.py /tmp/tts_server.py
RUN pip install --no-cache-dir --prefix=/install flask requests

FROM python:3.12-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy all apps
COPY bot.py .
COPY hermes-api-server/server.py hermes_server.py
COPY tts_server.py tts_server.py

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 3000 8080 8081

# Run based on SERVICE_TYPE env var
CMD ["sh", "-c", "if [ \"$SERVICE_TYPE\" = \"hermes-api\" ]; then exec python hermes_server.py; elif [ \"$SERVICE_TYPE\" = \"tts-server\" ]; then exec python tts_server.py; else exec gunicorn --bind 0.0.0.0:3000 --workers 2 --threads 4 --timeout 60 bot:app; fi"]