# 🚀 Messenger

A simple real-time WebSocket-based messenger application.

## Features

- Real-time messaging
- Multiple users support
- User join/leave notifications
- Modern UI with gradient design
- Docker support

## Quick Start with Docker

### Option 1: Using Docker Compose (Recommended)

```bash
cd messenger
docker-compose up --build
```

### Option 2: Using Docker directly

```bash
cd messenger
docker build -t messenger .
docker run -p 8765:8765 messenger
```

## Usage

1. Open your browser and navigate to `http://localhost:8765`
   - Note: You'll need to serve the HTML file separately or access it via a web server
   
2. Enter your username and click "Join Chat"

3. Start messaging!

## Manual Setup (without Docker)

```bash
cd messenger
pip install -r requirements.txt
python server.py
```

Then open `index.html` in your browser.

## Architecture

- **Server**: Python WebSocket server using `websockets` library
- **Client**: Pure HTML/CSS/JavaScript frontend
- **Protocol**: WebSocket (ws://)

## Ports

- **8765**: WebSocket server port

## Files

- `server.py` - WebSocket server
- `index.html` - Frontend client
- `requirements.txt` - Python dependencies
- `Dockerfile` - Docker image configuration
- `docker-compose.yml` - Docker Compose configuration
