#!/usr/bin/env python3
"""Simple WebSocket-based messenger server with HTTP support using aiohttp."""

import asyncio
import json
from datetime import datetime
from typing import Set, Dict
from aiohttp import web
import aiohttp

# Store connected clients: {username: websocket}
clients: Dict[str, web.WebSocketResponse] = {}
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
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
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
        for client in clients.values():
            try:
                await client.send_str(message)
            except Exception:
                pass


async def handle_client(request: web.Request):
    """Handle WebSocket client connection."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    username = None
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                action = data.get("action")
                
                if action == "join":
                    username = data.get("username")
                    if username and username not in usernames:
                        usernames.add(username)
                        clients[username] = ws
                        
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
                    
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
                
    except Exception:
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
    
    return ws


async def http_handler(request: web.Request):
    """Handle HTTP requests for the main page."""
    return web.Response(text=HTML_PAGE, content_type='text/html')


async def on_shutdown(app):
    """Close all WebSocket connections on shutdown."""
    for client in clients.values():
        await client.close()
    clients.clear()
    usernames.clear()


def create_app():
    """Create and configure the aiohttp application."""
    app = web.Application()
    app.router.add_get('/', http_handler)
    app.router.add_get('/ws', handle_client)  # WebSocket endpoint
    app.on_shutdown.append(on_shutdown)
    return app


def main():
    """Start the WebSocket server with HTTP support."""
    import os
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Messenger server starting on http://0.0.0.0:{port}")
    
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=port)


if __name__ == "__main__":
    main()
