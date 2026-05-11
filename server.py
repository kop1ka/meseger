#!/usr/bin/env python3
"""Simple WebSocket-based messenger server with HTTP support."""

import asyncio
import json
from datetime import datetime
from typing import Set, Dict
from http import HTTPStatus
import websockets
from websockets.server import serve

# Store connected clients: {username: websocket}
clients: Dict[str, websockets.WebSocketServerProtocol] = {}
# Store all usernames
usernames: Set[str] = set()

# Simple HTML page
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Messenger</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        #messages { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin-bottom: 10px; }
        .system { color: #666; font-style: italic; }
        .chat { margin: 5px 0; }
        .username { font-weight: bold; color: #0066cc; }
        #input-area { display: flex; gap: 10px; }
        #message-input { flex: 1; padding: 10px; }
        button { padding: 10px 20px; }
    </style>
</head>
<body>
    <h1>💬 Messenger</h1>
    <div id="login-area">
        <input type="text" id="username-input" placeholder="Enter username" />
        <button onclick="join()">Join Chat</button>
    </div>
    <div id="chat-area" style="display:none;">
        <div id="messages"></div>
        <div id="input-area">
            <input type="text" id="message-input" placeholder="Type a message..." />
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        let ws;
        let username;
        
        function join() {
            username = document.getElementById('username-input').value.trim();
            if (!username) return alert('Please enter a username');
            
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}`);
            
            ws.onopen = () => {
                ws.send(JSON.stringify({ action: 'join', username }));
                document.getElementById('login-area').style.display = 'none';
                document.getElementById('chat-area').style.display = 'block';
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                const messagesDiv = document.getElementById('messages');
                const msgDiv = document.createElement('div');
                
                if (data.type === 'system') {
                    msgDiv.className = 'system';
                    msgDiv.textContent = data.message;
                } else if (data.type === 'chat') {
                    msgDiv.className = 'chat';
                    msgDiv.innerHTML = `<span class="username">${data.username}:</span> ${data.message}`;
                }
                
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            };
            
            ws.onclose = () => alert('Disconnected from server');
        }
        
        function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (message && ws) {
                ws.send(JSON.stringify({ action: 'message', message }));
                input.value = '';
            }
        }
        
        document.getElementById('message-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>
"""


async def broadcast(message: str, sender: str = None):
    """Broadcast message to all connected clients."""
    if clients:
        await asyncio.gather(
            *[client.send(message) for client in clients.values()],
            return_exceptions=True
        )


async def handle_client(websocket: websockets.WebSocketServerProtocol):
    """Handle individual client connection."""
    username = None
    
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "join":
                username = data.get("username")
                if username and username not in usernames:
                    usernames.add(username)
                    clients[username] = websocket
                    
                    # Notify everyone about new user
                    join_msg = json.dumps({
                        "type": "system",
                        "message": f"{username} joined the chat",
                        "users": list(usernames),
                        "timestamp": datetime.now().isoformat()
                    })
                    await broadcast(join_msg)
                    
            elif action == "message" and username:
                msg_data = data.get("message", "")
                chat_msg = json.dumps({
                    "type": "chat",
                    "username": username,
                    "message": msg_data,
                    "timestamp": datetime.now().isoformat()
                })
                await broadcast(chat_msg)
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if username:
            usernames.discard(username)
            clients.pop(username, None)
            
            # Notify about user leaving
            leave_msg = json.dumps({
                "type": "system",
                "message": f"{username} left the chat",
                "users": list(usernames),
                "timestamp": datetime.now().isoformat()
            })
            await broadcast(leave_msg)


async def http_handler(path, request_headers):
    """Handle HTTP requests for the main page."""
    if path == "/" or path == "/index.html":
        return HTTPStatus.OK, [("Content-Type", "text/html")], HTML_PAGE.encode()
    return None  # Continue with WebSocket handshake


async def main():
    """Start the WebSocket server with HTTP support."""
    import os
    port = int(os.environ.get("PORT", 8765))
    print(f"🚀 Messenger server starting on http://0.0.0.0:{port}")
    
    async with serve(
        handle_client,
        "0.0.0.0",
        port,
        process_request=http_handler
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
