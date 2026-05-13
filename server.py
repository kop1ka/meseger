#!/usr/bin/env python3
"""Simple WebSocket-based messenger server with HTTP support using aiohttp."""

import asyncio
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime
from typing import Set, Dict, List, Optional
from aiohttp import web
import aiohttp

# Database setup
DB_PATH = "messenger.db"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode()).hexdigest()

def init_db():
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Users table for admin management
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_blocked INTEGER DEFAULT 0,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT
        )
    ''')
    
    # Admin sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    ''')
    
    # User sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    ''')
    
    # Chats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creator_username TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_username) REFERENCES users(username)
        )
    ''')
    
    # Chat members table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (username) REFERENCES users(username),
            UNIQUE(chat_id, username)
        )
    ''')
    
    # Chat messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (username) REFERENCES users(username)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_message(username: str, message: str, timestamp: str):
    """Save a message to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)',
        (username, message, timestamp)
    )
    # Update user last_seen
    cursor.execute(
        'INSERT OR IGNORE INTO users (username) VALUES (?)',
        (username,)
    )
    cursor.execute(
        'UPDATE users SET last_seen = ? WHERE username = ?',
        (timestamp, username)
    )
    conn.commit()
    conn.close()

def get_all_messages(limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all messages from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, message, timestamp, created_at FROM messages ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (limit, offset)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "username": r[1], "message": r[2], "timestamp": r[3], "created_at": r[4]}
        for r in rows
    ]

def get_all_users() -> List[dict]:
    """Get all users from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username, is_blocked, first_seen, last_seen FROM users ORDER BY last_seen DESC')
    rows = cursor.fetchall()
    conn.close()
    return [
        {"username": r[0], "is_blocked": bool(r[1]), "first_seen": r[2], "last_seen": r[3]}
        for r in rows
    ]

def block_user(username: str, blocked: bool):
    """Block or unblock a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET is_blocked = ? WHERE username = ?',
        (1 if blocked else 0, username)
    )
    conn.commit()
    conn.close()

def delete_message(message_id: int):
    """Delete a message by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()

def clear_all_messages():
    """Clear all messages from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages')
    conn.commit()
    conn.close()

def create_admin_session() -> str:
    """Create a new admin session token."""
    token = secrets.token_hex(32)
    now = datetime.now().isoformat()
    expires = datetime.now().replace(hour=23, minute=59, second=59).isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO admin_sessions (session_token, created_at, expires_at) VALUES (?, ?, ?)',
        (token, now, expires)
    )
    conn.commit()
    conn.close()
    return token

def validate_admin_session(token: str) -> bool:
    """Validate an admin session token."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM admin_sessions WHERE session_token = ? AND expires_at > ?',
        (token, datetime.now().isoformat())
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


# User authentication functions
def register_user(username: str, password: str) -> dict:
    """Register a new user."""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            (username, password_hash)
        )
        conn.commit()
        return {"success": True, "message": "User registered successfully"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "Username already exists"}
    finally:
        conn.close()


def login_user(username: str, password: str) -> dict:
    """Login user and create session."""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT username FROM users WHERE username = ? AND password_hash = ? AND is_blocked = 0',
        (username, password_hash)
    )
    row = cursor.fetchone()
    
    if row:
        # Create session
        token = secrets.token_hex(32)
        now = datetime.now().isoformat()
        expires = datetime.now().replace(hour=23, minute=59, second=59).isoformat()
        cursor.execute(
            'INSERT INTO user_sessions (username, session_token, created_at, expires_at) VALUES (?, ?, ?, ?)',
            (username, token, now, expires)
        )
        conn.commit()
        conn.close()
        return {"success": True, "token": token, "username": username}
    else:
        conn.close()
        return {"success": False, "message": "Invalid credentials or user is blocked"}


def validate_user_session(token: str) -> Optional[str]:
    """Validate user session token and return username."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT username FROM user_sessions WHERE session_token = ? AND expires_at > ?',
        (token, datetime.now().isoformat())
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_chats(username: str) -> List[dict]:
    """Get all chats for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.creator_username, c.created_at
        FROM chats c
        INNER JOIN chat_members cm ON c.id = cm.chat_id
        WHERE cm.username = ?
        ORDER BY c.created_at DESC
    ''', (username,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "creator_username": r[2], "created_at": r[3]}
        for r in rows
    ]


def create_chat(name: str, creator_username: str) -> dict:
    """Create a new chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO chats (name, creator_username) VALUES (?, ?)',
            (name, creator_username)
        )
        chat_id = cursor.lastrowid
        
        # Add creator as member
        cursor.execute(
            'INSERT INTO chat_members (chat_id, username) VALUES (?, ?)',
            (chat_id, creator_username)
        )
        conn.commit()
        return {"success": True, "chat_id": chat_id, "message": "Chat created successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


def add_user_to_chat(chat_id: int, username: str) -> dict:
    """Add a user to a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO chat_members (chat_id, username) VALUES (?, ?)',
            (chat_id, username)
        )
        conn.commit()
        return {"success": True, "message": "User added to chat"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "User is already in the chat"}
    finally:
        conn.close()


def get_chat_messages(chat_id: int, limit: int = 100) -> List[dict]:
    """Get messages for a specific chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, chat_id, username, message, timestamp, created_at
        FROM chat_messages
        WHERE chat_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "chat_id": r[1], "username": r[2], "message": r[3], "timestamp": r[4], "created_at": r[5]}
        for r in rows
    ]


def save_chat_message(chat_id: int, username: str, message: str, timestamp: str):
    """Save a message to a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO chat_messages (chat_id, username, message, timestamp) VALUES (?, ?, ?, ?)',
        (chat_id, username, message, timestamp)
    )
    conn.commit()
    conn.close()


def get_chat_members(chat_id: int) -> List[str]:
    """Get all members of a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM chat_members WHERE chat_id = ?', (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


# Initialize database on startup
init_db()

# Store connected clients: {username: websocket}
clients: Dict[str, web.WebSocketResponse] = {}
# Store all usernames
usernames: Set[str] = set()
# Blocked users cache
blocked_users: Set[str] = set()

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

# Admin panel HTML page
ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - Messenger</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; min-height: 100vh; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 24px; }
        .logout-btn { background: rgba(255,255,255,0.2); border: none; color: white; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
        .logout-btn:hover { background: rgba(255,255,255,0.3); }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 12px 24px; background: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
        .tab.active { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .tab:hover:not(.active) { background: #e9ecef; }
        .panel { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .login-form { max-width: 400px; margin: 100px auto; text-align: center; }
        .login-form input { width: 100%; padding: 14px; margin-bottom: 15px; border: 2px solid #e9ecef; border-radius: 8px; font-size: 16px; }
        .login-form button { width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e9ecef; }
        th { background: #f8f9fa; font-weight: 600; }
        .message-text { max-width: 400px; word-break: break-word; }
        .btn { padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-warning { background: #ffc107; color: #212529; }
        .blocked { background: #ffebee; }
        .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        .status-active { background: #d4edda; color: #155724; }
        .status-blocked { background: #f8d7da; color: #721c24; }
        .actions { display: flex; gap: 10px; }
        .clear-btn { margin-top: 20px; }
        .hidden { display: none !important; }
        .error { color: #dc3545; margin-top: 10px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px; text-align: center; }
        .stat-value { font-size: 32px; font-weight: bold; }
        .stat-label { font-size: 14px; opacity: 0.9; }
    </style>
</head>
<body>
    <div id="loginSection">
        <div class="panel login-form">
            <h2>🔐 Admin Login</h2>
            <p style="color: #6c757d; margin: 10px 0 20px;">Enter your credentials to access the admin panel</p>
            <input type="text" id="adminUsername" placeholder="Username" value="admin">
            <input type="password" id="adminPassword" placeholder="Password">
            <button onclick="login()">Login</button>
            <p class="error" id="loginError"></p>
        </div>
    </div>
    
    <div id="adminSection" class="hidden">
        <div class="header">
            <h1>🛡️ Admin Panel</h1>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
        
        <div class="container">
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value" id="totalMessages">0</div>
                    <div class="stat-label">Total Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="totalUsers">0</div>
                    <div class="stat-label">Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="blockedUsers">0</div>
                    <div class="stat-label">Blocked Users</div>
                </div>
            </div>
            
            <div class="tabs">
                <button class="tab active" onclick="showTab('messages')">📝 Messages</button>
                <button class="tab" onclick="showTab('users')">👥 Users</button>
            </div>
            
            <div id="messagesPanel" class="panel">
                <h2 style="margin-bottom: 15px;">Message History</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>User</th>
                            <th>Message</th>
                            <th>Time</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="messagesTable"></tbody>
                </table>
                <button class="btn btn-danger clear-btn" onclick="clearAllMessages()">🗑️ Clear All Messages</button>
            </div>
            
            <div id="usersPanel" class="panel hidden">
                <h2 style="margin-bottom: 15px;">User Management</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Status</th>
                            <th>First Seen</th>
                            <th>Last Seen</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="usersTable"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let authToken = localStorage.getItem('adminToken');
        
        if (authToken) {
            showAdminSection();
        }
        
        function login() {
            const username = document.getElementById('adminUsername').value;
            const password = document.getElementById('adminPassword').value;
            
            fetch('/api/admin/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    authToken = data.token;
                    localStorage.setItem('adminToken', authToken);
                    showAdminSection();
                    loadMessages();
                    loadUsers();
                } else {
                    document.getElementById('loginError').textContent = data.error || 'Login failed';
                }
            });
        }
        
        function logout() {
            localStorage.removeItem('adminToken');
            authToken = null;
            document.getElementById('loginSection').classList.remove('hidden');
            document.getElementById('adminSection').classList.add('hidden');
        }
        
        function showAdminSection() {
            document.getElementById('loginSection').classList.add('hidden');
            document.getElementById('adminSection').classList.remove('hidden');
        }
        
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('messagesPanel').classList.add('hidden');
            document.getElementById('usersPanel').classList.add('hidden');
            
            if (tab === 'messages') {
                document.getElementById('messagesPanel').classList.remove('hidden');
                loadMessages();
            } else {
                document.getElementById('usersPanel').classList.remove('hidden');
                loadUsers();
            }
        }
        
        function loadMessages() {
            fetch('/api/admin/messages', {headers: {'Authorization': 'Bearer ' + authToken}})
            .then(r => r.json())
            .then(data => {
                const tbody = document.getElementById('messagesTable');
                tbody.innerHTML = '';
                
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${msg.id}</td>
                            <td><strong>${escapeHtml(msg.username)}</strong></td>
                            <td class="message-text">${escapeHtml(msg.message)}</td>
                            <td>${formatDate(msg.created_at)}</td>
                            <td><button class="btn btn-danger" onclick="deleteMessage(${msg.id})">Delete</button></td>
                        `;
                        tbody.appendChild(row);
                    });
                    document.getElementById('totalMessages').textContent = data.messages.length;
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#6c757d;">No messages found</td></tr>';
                }
            });
        }
        
        function loadUsers() {
            fetch('/api/admin/users', {headers: {'Authorization': 'Bearer ' + authToken}})
            .then(r => r.json())
            .then(data => {
                const tbody = document.getElementById('usersTable');
                tbody.innerHTML = '';
                
                let blockedCount = 0;
                
                if (data.users && data.users.length > 0) {
                    data.users.forEach(user => {
                        if (user.is_blocked) blockedCount++;
                        const row = document.createElement('tr');
                        row.className = user.is_blocked ? 'blocked' : '';
                        row.innerHTML = `
                            <td><strong>${escapeHtml(user.username)}</strong></td>
                            <td><span class="status-badge ${user.is_blocked ? 'status-blocked' : 'status-active'}">${user.is_blocked ? 'Blocked' : 'Active'}</span></td>
                            <td>${formatDate(user.first_seen)}</td>
                            <td>${formatDate(user.last_seen)}</td>
                            <td class="actions">
                                <button class="btn ${user.is_blocked ? 'btn-success' : 'btn-warning'}" onclick="toggleBlock('${escapeHtml(user.username)}', ${!user.is_blocked})">
                                    ${user.is_blocked ? 'Unblock' : 'Block'}
                                </button>
                            </td>
                        `;
                        tbody.appendChild(row);
                    });
                    document.getElementById('totalUsers').textContent = data.users.length;
                    document.getElementById('blockedUsers').textContent = blockedCount;
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#6c757d;">No users found</td></tr>';
                }
            });
        }
        
        function deleteMessage(id) {
            if (!confirm('Are you sure you want to delete this message?')) return;
            
            fetch('/api/admin/delete-message', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({id})
            }).then(() => loadMessages());
        }
        
        function toggleBlock(username, blocked) {
            fetch('/api/admin/block-user', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({username, blocked})
            }).then(() => loadUsers());
        }
        
        function clearAllMessages() {
            if (!confirm('Are you sure you want to delete ALL messages? This cannot be undone!')) return;
            
            fetch('/api/admin/clear-messages', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken}
            }).then(() => loadMessages());
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatDate(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleString();
        }
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
                    # Check if user is blocked
                    if username in blocked_users:
                        continue
                    msg_data = data.get("message", "")
                    timestamp = datetime.now().isoformat()
                    
                    # Save message to database
                    save_message(username, msg_data, timestamp)
                    
                    chat_msg = json.dumps({
                        "type": "chat",
                        "username": username,
                        "message": msg_data,
                        "timestamp": timestamp
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


async def admin_page_handler(request: web.Request):
    """Handle HTTP requests for the admin page."""
    return web.Response(text=ADMIN_PAGE, content_type='text/html')


async def admin_login_handler(request: web.Request):
    """Handle admin login."""
    try:
        data = await request.json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        # Check credentials
        if username == ADMIN_USERNAME and hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
            token = create_admin_session()
            return web.json_response({'success': True, 'token': token})
        else:
            return web.json_response({'success': False, 'error': 'Invalid credentials'}, status=401)
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=400)


async def admin_messages_handler(request: web.Request):
    """Get all messages for admin panel."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not validate_admin_session(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    limit = int(request.query.get('limit', 100))
    offset = int(request.query.get('offset', 0))
    
    messages = get_all_messages(limit, offset)
    return web.json_response({'messages': messages})


async def admin_users_handler(request: web.Request):
    """Get all users for admin panel."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not validate_admin_session(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    users = get_all_users()
    return web.json_response({'users': users})


async def admin_block_user_handler(request: web.Request):
    """Block or unblock a user."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not validate_admin_session(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        username = data.get('username')
        blocked = data.get('blocked', False)
        
        if not username:
            return web.json_response({'error': 'Username required'}, status=400)
        
        block_user(username, blocked)
        
        # Update blocked users cache
        if blocked:
            blocked_users.add(username)
        else:
            blocked_users.discard(username)
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=400)


async def admin_delete_message_handler(request: web.Request):
    """Delete a message."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not validate_admin_session(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        message_id = data.get('id')
        
        if not message_id:
            return web.json_response({'error': 'Message ID required'}, status=400)
        
        delete_message(message_id)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=400)


async def admin_clear_messages_handler(request: web.Request):
    """Clear all messages."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not validate_admin_session(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    clear_all_messages()
    return web.json_response({'success': True})


# User authentication API handlers
async def user_register_handler(request: web.Request):
    """Handle user registration."""
    try:
        data = await request.json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return web.json_response({'success': False, 'message': 'Username and password required'}, status=400)
        
        result = register_user(username, password)
        if result['success']:
            return web.json_response(result)
        else:
            return web.json_response(result, status=400)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def user_login_handler(request: web.Request):
    """Handle user login."""
    try:
        data = await request.json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return web.json_response({'success': False, 'message': 'Username and password required'}, status=400)
        
        result = login_user(username, password)
        if result['success']:
            return web.json_response(result)
        else:
            return web.json_response(result, status=401)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def user_chats_handler(request: web.Request):
    """Get user's chats."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chats = get_user_chats(username)
    return web.json_response({'chats': chats})


async def create_chat_handler(request: web.Request):
    """Create a new chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        name = data.get('name', '').strip()
        
        if not name:
            return web.json_response({'success': False, 'message': 'Chat name required'}, status=400)
        
        result = create_chat(name, username)
        if result['success']:
            return web.json_response(result)
        else:
            return web.json_response(result, status=400)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def get_chat_messages_handler(request: web.Request) -> web.Response:
    """Get messages for a specific chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
    
    # Check if user is member of the chat
    members = get_chat_members(chat_id)
    if username not in members:
        return web.json_response({'error': 'Access denied'}, status=403)
    
    messages = get_chat_messages(chat_id)
    return web.json_response({'messages': messages})


async def send_chat_message_handler(request: web.Request) -> web.Response:
    """Send a message to a chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
    
    # Check if user is member of the chat
    members = get_chat_members(chat_id)
    if username not in members:
        return web.json_response({'error': 'Access denied'}, status=403)
    
    try:
        data = await request.json()
        message = data.get('message', '').strip()
        
        if not message:
            return web.json_response({'success': False, 'message': 'Message required'}, status=400)
        
        timestamp = datetime.now().isoformat()
        save_chat_message(chat_id, username, message, timestamp)
        
        return web.json_response({
            'success': True,
            'message': {
                'username': username,
                'message': message,
                'timestamp': timestamp
            }
        })
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def add_member_to_chat_handler(request: web.Request) -> web.Response:
    """Add a member to a chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
    
    # Only chat creator can add members
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT creator_username FROM chats WHERE id = ?', (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] != username:
        return web.json_response({'error': 'Only chat creator can add members'}, status=403)
    
    try:
        data = await request.json()
        new_member = data.get('username', '').strip()
        
        if not new_member:
            return web.json_response({'success': False, 'message': 'Username required'}, status=400)
        
        result = add_user_to_chat(chat_id, new_member)
        if result['success']:
            return web.json_response(result)
        else:
            return web.json_response(result, status=400)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


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
    app.router.add_get('/admin', admin_page_handler)  # Admin panel page
    
    # Admin API routes
    app.router.add_post('/api/admin/login', admin_login_handler)
    app.router.add_get('/api/admin/messages', admin_messages_handler)
    app.router.add_get('/api/admin/users', admin_users_handler)
    app.router.add_post('/api/admin/block-user', admin_block_user_handler)
    app.router.add_post('/api/admin/delete-message', admin_delete_message_handler)
    app.router.add_post('/api/admin/clear-messages', admin_clear_messages_handler)
    
    # User authentication API routes
    app.router.add_post('/api/user/register', user_register_handler)
    app.router.add_post('/api/user/login', user_login_handler)
    app.router.add_get('/api/user/chats', user_chats_handler)
    app.router.add_post('/api/user/chats', create_chat_handler)
    app.router.add_get('/api/chat/{chat_id}/messages', get_chat_messages_handler)
    app.router.add_post('/api/chat/{chat_id}/messages', send_chat_message_handler)
    app.router.add_post('/api/chat/{chat_id}/members', add_member_to_chat_handler)
    
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
