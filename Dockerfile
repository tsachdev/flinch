FROM python:3.11-slim

WORKDIR /app

# Install deps (exclude rumps — macOS only)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the agent loop
CMD ["python", "main.py"]
