FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY threads_api.py .
COPY x_api.py .
COPY exchange_threads.py .


CMD ["python", "main.py"]
