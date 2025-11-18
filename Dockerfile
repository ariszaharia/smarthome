FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire app folder into the container
COPY app/ ./app/

WORKDIR /app/app

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8000"]
