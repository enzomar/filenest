FROM python:3.11-slim

WORKDIR /app/backend

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/backend/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/backend/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
