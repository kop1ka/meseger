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

# Simple HTML page with modern responsive design
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Messenger</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 10px;
        }
        
        .container {
            width: 100%;
            max-width: 800px;
            height: 90vh;
            max-height: 700px;
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            text-align: center;
            flex-shrink: 0;
        }
        
        .header h1 {
            font-size: 20px;
            margin-bottom: 5px;
            font-weight: 600;
        }
        
        .users-list {
            font-size: 13px;
            opacity: 0.9;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .status {
            padding: 8px;
            text-align: center;
            font-size: 12px;
            flex-shrink: 0;
        }
        
        .status.connected {
            background: #d4edda;
            color: #155724;
        }
        
        .status.disconnected {
            background: #f8d7da;
            color: #721c24;
        }
        
        .messages {
            flex: 1;
            padding: 15px;
            overflow-y: auto;
            background: #f8f9fa;
            -webkit-overflow-scrolling: touch;
        }
        
        .message {
            margin-bottom: 12px;
            padding: 10px 14px;
            border-radius: 12px;
            max-width: 75%;
            word-wrap: break-word;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.chat {
            background: white;
            margin-right: auto;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .message.my-message {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            margin-left: auto;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
        }
        
        .message.system {
            background: #e9ecef;
            text-align: center;
            max-width: 90%;
            margin-left: auto;
            margin-right: auto;
            font-style: italic;
            font-size: 12px;
            color: #6c757d;
        }
        
        .message-username {
            font-weight: 600;
            font-size: 11px;
            margin-bottom: 4px;
            color: #667eea;
        }
        
        .my-message .message-username {
            color: rgba(255,255,255,0.9);
        }
        
        .message-text {
            font-size: 14px;
            line-height: 1.4;
        }
        
        .message-time {
            font-size: 10px;
            opacity: 0.7;
            margin-top: 4px;
            text-align: right;
        }
        
        .input-area {
            padding: 15px;
            background: white;
            border-top: 1px solid #e9ecef;
            display: flex;
            gap: 10px;
            flex-shrink: 0;
            position: relative;
        }
        
        .emoji-btn {
            padding: 12px 16px;
            background: #f8f9fa;
            color: #6c757d;
            border: 2px solid #e9ecef;
            border-radius: 24px;
            cursor: pointer;
            font-size: 18px;
            transition: all 0.2s;
            -webkit-appearance: none;
        }
        
        .emoji-btn:hover {
            background: #e9ecef;
            transform: translateY(-1px);
        }
        
        .emoji-panel {
            position: absolute;
            bottom: 100%;
            left: 15px;
            right: 15px;
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            padding: 12px;
            display: none;
            grid-template-columns: repeat(8, 1fr);
            gap: 8px;
            margin-bottom: 10px;
            max-height: 200px;
            overflow-y: auto;
        }
        
        .emoji-panel.show {
            display: grid;
        }
        
        .emoji-item {
            font-size: 20px;
            padding: 8px;
            text-align: center;
            cursor: pointer;
            border-radius: 8px;
            transition: background 0.2s;
        }
        
        .emoji-item:hover {
            background: #f0f0f0;
        }
        
        #messageInput {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 24px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
            font-family: inherit;
        }
        
        #messageInput:focus {
            border-color: #667eea;
        }
        
        #sendBtn {
            padding: 12px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 24px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: transform 0.2s, box-shadow 0.2s;
            font-family: inherit;
            -webkit-appearance: none;
        }
        
        #sendBtn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        #sendBtn:active {
            transform: translateY(0);
        }
        
        .login-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(4px);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            padding: 20px;
        }
        
        .login-box {
            background: white;
            padding: 30px 25px;
            border-radius: 16px;
            text-align: center;
            width: 100%;
            max-width: 360px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .login-box h2 {
            margin-bottom: 10px;
            color: #667eea;
            font-size: 22px;
        }
        
        .login-box p {
            color: #6c757d;
            font-size: 14px;
            margin-bottom: 20px;
        }
        
        .login-box input {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            font-size: 16px;
            margin-bottom: 15px;
            font-family: inherit;
            transition: border-color 0.2s;
        }
        
        .login-box input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .login-box button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            font-family: inherit;
            -webkit-appearance: none;
        }
        
        .login-box button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .login-box button:active {
            transform: translateY(0);
        }
        
        .hidden {
            display: none !important;
        }
        
        /* Mobile optimizations */
        @media (max-width: 480px) {
            body {
                padding: 0;
                align-items: flex-start;
            }
            
            .container {
                height: 100vh;
                max-height: none;
                border-radius: 0;
            }
            
            .header h1 {
                font-size: 18px;
            }
            
            .users-list {
                font-size: 12px;
            }
            
            .message {
                max-width: 85%;
                padding: 8px 12px;
            }
            
            .message-text {
                font-size: 13px;
            }
            
            .input-area {
                padding: 12px;
            }
            
            #messageInput {
                padding: 10px 14px;
                font-size: 16px; /* Prevents zoom on iOS */
            }
            
            #sendBtn {
                padding: 10px 16px;
            }
            
            .login-box {
                padding: 25px 20px;
                margin: 20px;
            }
        }
        
        /* Tablet optimizations */
        @media (min-width: 481px) and (max-width: 768px) {
            .container {
                height: 85vh;
            }
            
            .message {
                max-width: 80%;
            }
        }
        
        /* Desktop optimizations */
        @media (min-width: 769px) {
            .container {
                height: 80vh;
            }
        }
        
        /* Dark mode support */
        @media (prefers-color-scheme: dark) {
            .message.chat {
                background: #2d3748;
                color: #e2e8f0;
            }
            
            .message.system {
                background: #4a5568;
                color: #cbd5e0;
            }
            
            #messageInput {
                background: #1a202c;
                border-color: #4a5568;
                color: #e2e8f0;
            }
            
            .input-area {
                background: #1a202c;
                border-top-color: #4a5568;
            }
            
            .messages {
                background: #1a202c;
            }
        }
    </style>
</head>
<body>
    <div class="login-modal" id="loginModal">
        <div class="login-box">
            <h2>💬 Messenger</h2>
            <p>Enter your username to join the chat</p>
            <input type="text" id="usernameInput" placeholder="Your username" maxlength="20" autocomplete="off">
            <button onclick="joinChat()">Join Chat</button>
        </div>
    </div>
    
    <div class="container">
        <div class="header">
            <h1>💬 Messenger</h1>
            <div class="users-list" id="usersList">Users: </div>
        </div>
        
        <div class="status disconnected" id="status">Connecting...</div>
        
        <div class="messages" id="messages"></div>
        
        <div class="input-area">
            <button id="emojiBtn" class="emoji-btn" onclick="toggleEmojiPanel()">😊</button>
            <div class="emoji-panel" id="emojiPanel"></div>
            <input type="text" id="messageInput" placeholder="Type a message..." onkeypress="handleKeyPress(event)" autocomplete="off">
            <button id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        let ws;
        let username = '';
        
        function joinChat() {
            const input = document.getElementById('usernameInput');
            username = input.value.trim();
            
            if (!username) {
                alert('Please enter a username');
                return;
            }
            
            // Connect to WebSocket server using current host and /ws path
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('loginModal').classList.add('hidden');
                document.getElementById('status').textContent = 'Connected';
                document.getElementById('status').className = 'status connected';
                
                // Send join message
                ws.send(JSON.stringify({
                    action: 'join',
                    username: username
                }));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                displayMessage(data);
            };
            
            ws.onclose = () => {
                document.getElementById('status').textContent = 'Disconnected - Reconnecting...';
                document.getElementById('status').className = 'status disconnected';
                setTimeout(() => location.reload(), 3000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function displayMessage(data) {
            const messagesDiv = document.getElementById('messages');
            const msgDiv = document.createElement('div');
            
            if (data.type === 'system') {
                msgDiv.className = 'message system';
                msgDiv.innerHTML = `<div class="message-text">${escapeHtml(data.message)}</div>`;
                if (data.users && data.users.length > 0) {
                    document.getElementById('usersList').textContent = 'Users: ' + data.users.join(', ');
                } else if (data.users) {
                    document.getElementById('usersList').textContent = 'Users: 0';
                }
            } else if (data.type === 'chat') {
                const isMyMessage = data.username === username;
                msgDiv.className = `message chat ${isMyMessage ? 'my-message' : ''}`;
                msgDiv.innerHTML = `
                    <div class="message-username">${escapeHtml(data.username)}</div>
                    <div class="message-text">${escapeHtml(data.message)}</div>
                    <div class="message-time">${formatTime(data.timestamp)}</div>
                `;
            }
            
            messagesDiv.appendChild(msgDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (message && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'message',
                    message: message
                }));
                input.value = '';
                input.focus();
            }
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatTime(timestamp) {
            if (!timestamp) return '';
            try {
                const date = new Date(timestamp);
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            } catch (e) {
                return '';
            }
        }
        
        // Allow login with Enter key
        document.getElementById('usernameInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                joinChat();
            }
        });
        
        // Auto-focus username input on load
        window.addEventListener('load', () => {
            document.getElementById('usernameInput').focus();
            initEmojiPanel();
        });
        
        // Popular emojis list
        const emojis = ['😀','😃','😄','😁','😆','😅','🤣','😂','🙂','🙃','😉','😊','😇','🥰','😍','🤩','😘','😗','😚','😙','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🤫','🤔','🤐','🤨','😐','😑','😶','😏','😒','🙄','😬','🤥','😌','😔','😪','🤤','😴','😷','🤒','🤕','🤢','🤮','🤧','🥵','🥶','🥴','😵','🤯','🤠','🥳','😎','🤓','🧐','😕','😟','🙁','☹️','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','🥱','😤','😡','😠','🤬','😈','👿','💀','☠️','💩','🤡','👹','👺','👻','👽','👾','🤖','😺','😸','😹','😻','😼','😽','🙀','😿','😾','🙈','🙉','🙊','💋','💌','💘','💝','💖','💗','💓','💞','💕','💟','❣️','💔','❤️','🧡','💛','💚','💙','💜','🤎','🖤','🤍','👍','👎','👊','✊','🤛','🤜','🤞','✌️','🤟','🤘','👌','🤌','🤏','👈','👉','👆','👇','☝️','✋','🤚','🖐️','🖖','👋','🤙','💪','🖕','✍️','🙏','🦶','🦵','🦿','🦾','🦿'];
        
        function initEmojiPanel() {
            const panel = document.getElementById('emojiPanel');
            emojis.forEach(emoji => {
                const span = document.createElement('span');
                span.className = 'emoji-item';
                span.textContent = emoji;
                span.onclick = () => insertEmoji(emoji);
                panel.appendChild(span);
            });
        }
        
        function toggleEmojiPanel() {
            const panel = document.getElementById('emojiPanel');
            panel.classList.toggle('show');
        }
        
        function insertEmoji(emoji) {
            const input = document.getElementById('messageInput');
            input.value += emoji;
            input.focus();
            document.getElementById('emojiPanel').classList.remove('show');
        }
        
        // Close emoji panel when clicking outside
        document.addEventListener('click', (e) => {
            const panel = document.getElementById('emojiPanel');
            const btn = document.getElementById('emojiBtn');
            if (!panel.contains(e.target) && e.target !== btn) {
                panel.classList.remove('show');
            }
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
