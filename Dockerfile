FROM python:3.12-slim

COPY src/ /app/src/
RUN mkdir -p /app/data

WORKDIR /app

CMD ["python", "src/main.py"]
