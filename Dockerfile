FROM python:3.12-slim

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src/ /app/src/
RUN mkdir -p /app/data

WORKDIR /app

CMD ["python", "src/main.py"]
