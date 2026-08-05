FROM python:3.12-slim

# Stream prints to Render logs immediately — without this, Python block-buffers
# stdout (8KB) and the log tail looks empty even while the bot runs fine.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src/ /app/src/
RUN mkdir -p /app/data

WORKDIR /app

CMD ["python", "src/main.py"]
