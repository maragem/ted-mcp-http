FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .

# Railway injects $PORT at runtime — the server reads it automatically
EXPOSE 8000

CMD ["python", "server.py"]
