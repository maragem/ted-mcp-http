FROM python:3.12-slim

WORKDIR /app

# pymupdf needs these system libs for PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8000

CMD ["python", "server.py"]
