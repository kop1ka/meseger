# Messenger Docker Image
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY index.html .

# Expose WebSocket port
EXPOSE 8765

# Serve static files and run WebSocket server
CMD ["python", "server.py"]
