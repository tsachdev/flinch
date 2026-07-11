FROM node:20-slim AS console-ui-build

WORKDIR /app/console-ui
COPY console-ui/package.json console-ui/package-lock.json ./
RUN npm ci
COPY console-ui/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# Install deps (exclude rumps — macOS only)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=console-ui-build /app/console-ui/dist ./console-ui/dist

# Default: run the agent loop
CMD ["python", "main.py"]
