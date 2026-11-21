FROM python:3.12-slim

WORKDIR /app
COPY heartbeat.py /app/heartbeat.py

RUN useradd --system --uid 10001 heartbeat
USER heartbeat

ENTRYPOINT ["python", "-u", "/app/heartbeat.py"]
