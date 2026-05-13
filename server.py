#!/usr/bin/env python3
"""Secure Messenger with authentication, private chats, and group chats."""

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
    
    # Users table
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
    
    # Admin sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    ''')
    
    # Friend requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_username TEXT NOT NULL,
            receiver_username TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_username) REFERENCES users(username),
            FOREIGN KEY (receiver_username) REFERENCES users(username),
            UNIQUE(sender_username, receiver_username)
        )
    ''')
    
    # Friends table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1 TEXT NOT NULL,
            user2 TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user1) REFERENCES users(username),
            FOREIGN KEY (user2) REFERENCES users(username),
            UNIQUE(user1, user2)
        )
    ''')
    
    # Chats table (for group chats)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creator_username TEXT NOT NULL,
            is_group INTEGER DEFAULT 1,
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
    
    # Messages table (for all chat types)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            sender_username TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (sender_username) REFERENCES users(username)
        )
    ''')
    
    conn.commit()
    conn.close()

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

def search_users(query: str, exclude_username: str) -> List[str]:
    """Search for users by username."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT username FROM users WHERE username LIKE ? AND username != ? AND is_blocked = 0 LIMIT 20',
        (f'%{query}%', exclude_username)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def send_friend_request(sender: str, receiver: str) -> dict:
    """Send a friend request."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO friend_requests (sender_username, receiver_username) VALUES (?, ?)',
            (sender, receiver)
        )
        conn.commit()
        return {"success": True, "message": "Friend request sent"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "Request already exists"}
    finally:
        conn.close()

def get_friend_requests(username: str) -> List[dict]:
    """Get pending friend requests for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT sender_username, created_at FROM friend_requests WHERE receiver_username = ? AND status = ?',
        (username, 'pending')
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": r[0], "created_at": r[1]} for r in rows]

def respond_to_friend_request(sender: str, receiver: str, accept: bool) -> dict:
    """Accept or decline a friend request."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if accept:
        status = 'accepted'
    else:
        status = 'declined'
    
    cursor.execute(
        'UPDATE friend_requests SET status = ? WHERE sender_username = ? AND receiver_username = ?',
        (status, sender, receiver)
    )
    
    if accept:
        # Create a private chat between the two users
        try:
            cursor.execute(
                'INSERT INTO chats (name, creator_username, is_group) VALUES (?, ?, 0)',
                (f"{min(sender, receiver)}-{max(sender, receiver)}", receiver)
            )
            chat_id = cursor.lastrowid
            cursor.execute('INSERT INTO chat_members (chat_id, username) VALUES (?, ?)', (chat_id, sender))
            cursor.execute('INSERT INTO chat_members (chat_id, username) VALUES (?, ?)', (chat_id, receiver))
        except sqlite3.IntegrityError:
            pass  # Chat already exists
    
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Request {'accepted' if accept else 'declined'}"}

def get_friends(username: str) -> List[str]:
    """Get list of friends for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT CASE WHEN user1 = ? THEN user2 ELSE user1 END as friend
           FROM friends WHERE user1 = ? OR user2 = ?''',
        (username, username, username)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_user_chats(username: str) -> List[dict]:
    """Get all chats for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.creator_username, c.is_group, c.created_at
        FROM chats c
        INNER JOIN chat_members cm ON c.id = cm.chat_id
        WHERE cm.username = ?
        ORDER BY c.created_at DESC
    ''', (username,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "creator_username": r[2], "is_group": bool(r[3]), "created_at": r[4]}
        for r in rows
    ]

def create_chat(name: str, creator_username: str, members: List[str]) -> dict:
    """Create a new group chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO chats (name, creator_username, is_group) VALUES (?, ?, 1)',
            (name, creator_username)
        )
        chat_id = cursor.lastrowid
        
        # Add creator as member
        cursor.execute('INSERT INTO chat_members (chat_id, username) VALUES (?, ?)', (chat_id, creator_username))
        
        # Add other members
        for member in members:
            if member != creator_username:
                cursor.execute('INSERT INTO chat_members (chat_id, username) VALUES (?, ?)', (chat_id, member))
        
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
        SELECT id, chat_id, sender_username, message, timestamp, created_at
        FROM messages
        WHERE chat_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    ''', (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "chat_id": r[1], "sender_username": r[2], "message": r[3], "timestamp": r[4], "created_at": r[5]}
        for r in rows
    ]

def save_chat_message(chat_id: int, username: str, message: str, timestamp: str):
    """Save a message to a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO messages (chat_id, sender_username, message, timestamp) VALUES (?, ?, ?, ?)',
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

def get_private_chat_id(user1: str, user2: str) -> Optional[int]:
    """Get the private chat ID between two users."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    chat_name = f"{min(user1, user2)}-{max(user1, user2)}"
    cursor.execute('SELECT id FROM chats WHERE name = ? AND is_group = 0', (chat_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

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

# Initialize database on startup
init_db()

# Store connected clients: {username: websocket}
clients: Dict[str, web.WebSocketResponse] = {}
# Blocked users cache
blocked_users: Set[str] = set()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Messenger</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .auth-container { display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
        .auth-box { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 400px; }
        .auth-box h2 { color: #667eea; margin-bottom: 10px; text-align: center; }
        .auth-box p { color: #6c757d; text-align: center; margin-bottom: 20px; }
        .auth-box input { width: 100%; padding: 14px; margin-bottom: 15px; border: 2px solid #e9ecef; border-radius: 12px; font-size: 16px; }
        .auth-box input:focus { outline: none; border-color: #667eea; }
        .auth-box button { width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer; }
        .auth-box button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }
        .auth-box .toggle-link { text-align: center; margin-top: 20px; color: #667eea; cursor: pointer; }
        .app-container { display: none; height: 100vh; }
        .app-container.active { display: flex; }
        .sidebar { width: 300px; background: white; border-right: 1px solid #e9ecef; display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; border-bottom: 1px solid #e9ecef; }
        .sidebar-header h2 { color: #667eea; margin-bottom: 10px; }
        .user-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .logout-btn { background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .search-box { display: flex; gap: 10px; margin-bottom: 15px; }
        .search-box input { flex: 1; padding: 10px; border: 2px solid #e9ecef; border-radius: 8px; }
        .search-box button { padding: 10px 16px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .tabs { display: flex; border-bottom: 1px solid #e9ecef; }
        .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; border: none; background: none; }
        .tab.active { color: #667eea; border-bottom: 2px solid #667eea; }
        .chat-list { flex: 1; overflow-y: auto; }
        .chat-item { padding: 15px 20px; border-bottom: 1px solid #f0f0f0; cursor: pointer; transition: background 0.2s; }
        .chat-item:hover { background: #f8f9fa; }
        .chat-item.active { background: #e7f3ff; }
        .chat-item-name { font-weight: 600; margin-bottom: 4px; }
        .chat-item-preview { color: #6c757d; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .main-chat { flex: 1; display: flex; flex-direction: column; background: #f8f9fa; }
        .chat-header { padding: 20px; background: white; border-bottom: 1px solid #e9ecef; display: flex; justify-content: space-between; align-items: center; }
        .chat-header h3 { color: #333; }
        .members-list { color: #6c757d; font-size: 13px; }
        .messages-container { flex: 1; padding: 20px; overflow-y: auto; }
        .message { margin-bottom: 15px; max-width: 70%; }
        .message.my-message { margin-left: auto; }
        .message-bubble { padding: 12px 16px; border-radius: 18px; }
        .message.chat .message-bubble { background: white; border-bottom-left-radius: 4px; }
        .message.my-message .message-bubble { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-bottom-right-radius: 4px; }
        .message-sender { font-size: 12px; color: #667eea; margin-bottom: 4px; font-weight: 600; }
        .message.my-message .message-sender { color: rgba(255,255,255,0.9); }
        .message-time { font-size: 11px; opacity: 0.7; margin-top: 4px; text-align: right; }
        .input-area { padding: 20px; background: white; border-top: 1px solid #e9ecef; display: flex; gap: 10px; }
        .input-area input { flex: 1; padding: 14px 20px; border: 2px solid #e9ecef; border-radius: 24px; font-size: 16px; }
        .input-area input:focus { outline: none; border-color: #667eea; }
        .input-area button { padding: 14px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 24px; cursor: pointer; font-weight: 600; }
        .modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: none; justify-content: center; align-items: center; z-index: 1000; }
        .modal.active { display: flex; }
        .modal-content { background: white; padding: 30px; border-radius: 16px; width: 100%; max-width: 500px; max-height: 80vh; overflow-y: auto; }
        .modal-content h3 { margin-bottom: 20px; color: #667eea; }
        .request-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #f0f0f0; }
        .request-actions { display: flex; gap: 10px; }
        .btn-accept { background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .btn-decline { background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .search-results { margin-top: 10px; max-height: 200px; overflow-y: auto; border: 1px solid #e9ecef; border-radius: 8px; }
        .search-result-item { padding: 10px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
        .btn-send-request { background: #667eea; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .hidden { display: none !important; }
        .no-chats { text-align: center; color: #6c757d; padding: 40px; }
        .create-chat-form { margin-top: 15px; }
        .create-chat-form input { width: 100%; padding: 10px; margin-bottom: 10px; border: 2px solid #e9ecef; border-radius: 8px; }
        .create-chat-form button { width: 100%; padding: 10px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="auth-container" id="authContainer">
        <div class="auth-box">
            <h2 id="authTitle">💬 Login</h2>
            <p id="authSubtitle">Enter your credentials</p>
            <input type="text" id="usernameInput" placeholder="Username" maxlength="20">
            <input type="password" id="passwordInput" placeholder="Password">
            <button id="authBtn" onclick="handleAuth()">Login</button>
            <div class="toggle-link" onclick="toggleAuthMode()">Don't have an account? Register</div>
            <p id="authError" style="color: #dc3545; margin-top: 10px;"></p>
        </div>
    </div>

    <div class="app-container" id="appContainer">
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="user-info">
                    <h2 id="currentUser">User</h2>
                    <button class="logout-btn" onclick="logout()">Logout</button>
                </div>
                <div class="search-box">
                    <input type="text" id="userSearch" placeholder="Search users..." oninput="searchUsers()">
                    <button onclick="searchUsers()">🔍</button>
                </div>
                <div id="searchResults" class="search-results hidden"></div>
                <div class="tabs">
                    <button class="tab active" onclick="showTab('chats')">Chats</button>
                    <button class="tab" onclick="showTab('requests')">Requests (<span id="requestCount">0</span>)</button>
                </div>
            </div>
            <div class="chat-list" id="chatList">
                <div class="no-chats">No chats yet. Start a conversation!</div>
            </div>
        </div>
        <div class="main-chat">
            <div class="chat-header" id="chatHeader">
                <div>
                    <h3 id="currentChatName">Select a chat</h3>
                    <div class="members-list" id="chatMembers"></div>
                </div>
                <button onclick="showCreateChatModal()" style="padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer;">+ New Group</button>
            </div>
            <div class="messages-container" id="messagesContainer">
                <div class="no-chats">Select a chat to start messaging</div>
            </div>
            <div class="input-area" id="inputArea" style="display: none;">
                <input type="text" id="messageInput" placeholder="Type a message..." onkeypress="handleKeyPress(event)">
                <button onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>

    <div class="modal" id="requestsModal">
        <div class="modal-content">
            <h3>Friend Requests</h3>
            <div id="requestsList"></div>
            <button onclick="closeModal('requestsModal')" style="margin-top: 20px; padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer;">Close</button>
        </div>
    </div>

    <div class="modal" id="createChatModal">
        <div class="modal-content">
            <h3>Create Group Chat</h3>
            <div class="create-chat-form">
                <input type="text" id="newChatName" placeholder="Group name">
                <input type="text" id="newChatMembers" placeholder="Add members (comma-separated usernames)">
                <button onclick="createGroupChat()">Create Group</button>
            </div>
            <button onclick="closeModal('createChatModal')" style="margin-top: 20px; padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer;">Cancel</button>
        </div>
    </div>

    <script>
        let authToken = localStorage.getItem('authToken');
        let currentUser = localStorage.getItem('currentUser');
        let isLoginMode = true;
        let currentChatId = null;
        let ws = null;
        let messagePollInterval = null;

        if (authToken && currentUser) {
            showApp();
        }

        function toggleAuthMode() {
            isLoginMode = !isLoginMode;
            document.getElementById('authTitle').textContent = isLoginMode ? '💬 Login' : '📝 Register';
            document.getElementById('authSubtitle').textContent = isLoginMode ? 'Enter your credentials' : 'Create a new account';
            document.getElementById('authBtn').textContent = isLoginMode ? 'Login' : 'Register';
            document.querySelector('.toggle-link').textContent = isLoginMode ? "Don't have an account? Register" : 'Already have an account? Login';
            document.getElementById('authError').textContent = '';
        }

        async function handleAuth() {
            const username = document.getElementById('usernameInput').value.trim();
            const password = document.getElementById('passwordInput').value;
            
            if (!username || !password) {
                document.getElementById('authError').textContent = 'Please fill in all fields';
                return;
            }

            const endpoint = isLoginMode ? '/api/user/login' : '/api/user/register';
            
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                const data = await response.json();
                
                if (data.success) {
                    if (isLoginMode) {
                        authToken = data.token;
                        currentUser = data.username;
                        localStorage.setItem('authToken', authToken);
                        localStorage.setItem('currentUser', currentUser);
                        showApp();
                    } else {
                        alert('Registration successful! Please login.');
                        toggleAuthMode();
                    }
                } else {
                    document.getElementById('authError').textContent = data.message;
                }
            } catch (error) {
                document.getElementById('authError').textContent = 'Connection error';
            }
        }

        function logout() {
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
            authToken = null;
            currentUser = null;
            if (ws) ws.close();
            if (messagePollInterval) clearInterval(messagePollInterval);
            document.getElementById('authContainer').style.display = 'flex';
            document.getElementById('appContainer').classList.remove('active');
        }

        function showApp() {
            document.getElementById('authContainer').style.display = 'none';
            document.getElementById('appContainer').classList.add('active');
            document.getElementById('currentUser').textContent = currentUser;
            loadChats();
            loadFriendRequests();
            connectWebSocket();
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws?token=${authToken}&username=${currentUser}`;
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'new_message' && data.chat_id === currentChatId) {
                    displayMessage(data.message, data.sender_username === currentUser);
                } else if (data.type === 'chat_update') {
                    loadChats();
                } else if (data.type === 'friend_request') {
                    loadFriendRequests();
                }
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting...');
                setTimeout(connectWebSocket, 3000);
            };
        }

        async function loadChats() {
            const response = await fetch('/api/user/chats', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            
            const chatList = document.getElementById('chatList');
            if (data.chats && data.chats.length > 0) {
                chatList.innerHTML = '';
                data.chats.forEach(chat => {
                    const item = document.createElement('div');
                    item.className = 'chat-item';
                    item.onclick = () => openChat(chat.id, chat.name, chat.is_group);
                    item.innerHTML = `
                        <div class="chat-item-name">${escapeHtml(chat.name)}</div>
                        <div class="chat-item-preview">${chat.is_group ? 'Group chat' : 'Private chat'}</div>
                    `;
                    chatList.appendChild(item);
                });
            } else {
                chatList.innerHTML = '<div class="no-chats">No chats yet. Start a conversation!</div>';
            }
        }

        async function openChat(chatId, chatName, isGroup) {
            currentChatId = chatId;
            document.getElementById('currentChatName').textContent = chatName;
            document.getElementById('inputArea').style.display = 'flex';
            
            // Highlight active chat
            document.querySelectorAll('.chat-item').forEach(item => item.classList.remove('active'));
            event.target.closest('.chat-item')?.classList.add('active');
            
            // Load messages
            await loadMessages(chatId);
            
            // Get members
            const response = await fetch(`/api/chat/${chatId}/members`, {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            if (data.members) {
                document.getElementById('chatMembers').textContent = isGroup ? 'Members: ' + data.members.join(', ') : 'Private chat';
            }
            
            // Start polling for new messages
            if (messagePollInterval) clearInterval(messagePollInterval);
            messagePollInterval = setInterval(() => loadMessages(chatId), 2000);
        }

        async function loadMessages(chatId) {
            const response = await fetch(`/api/chat/${chatId}/messages`, {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            
            const container = document.getElementById('messagesContainer');
            if (data.messages && data.messages.length > 0) {
                container.innerHTML = '';
                data.messages.forEach(msg => {
                    displayMessage(msg, msg.sender_username === currentUser);
                });
                container.scrollTop = container.scrollHeight;
            }
        }

        function displayMessage(msg, isMyMessage) {
            const container = document.getElementById('messagesContainer');
            const div = document.createElement('div');
            div.className = `message ${isMyMessage ? 'my-message' : 'chat'}`;
            div.innerHTML = `
                <div class="message-bubble">
                    ${!isMyMessage ? `<div class="message-sender">${escapeHtml(msg.sender_username)}</div>` : ''}
                    <div>${escapeHtml(msg.message)}</div>
                    <div class="message-time">${formatTime(msg.timestamp)}</div>
                </div>
            `;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message || !currentChatId) return;
            
            await fetch(`/api/chat/${currentChatId}/messages`, {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({message})
            });
            
            input.value = '';
            loadMessages(currentChatId);
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') sendMessage();
        }

        async function searchUsers() {
            const query = document.getElementById('userSearch').value.trim();
            if (query.length < 2) {
                document.getElementById('searchResults').classList.add('hidden');
                return;
            }
            
            const response = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`, {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            
            const resultsDiv = document.getElementById('searchResults');
            if (data.users && data.users.length > 0) {
                resultsDiv.classList.remove('hidden');
                resultsDiv.innerHTML = data.users.map(user => `
                    <div class="search-result-item">
                        <span>${escapeHtml(user)}</span>
                        <button class="btn-send-request" onclick="sendFriendRequest('${escapeHtml(user)}')">Add Friend</button>
                    </div>
                `).join('');
            } else {
                resultsDiv.classList.add('hidden');
            }
        }

        async function sendFriendRequest(targetUser) {
            await fetch('/api/friend/request', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({target_user: targetUser})
            });
            document.getElementById('userSearch').value = '';
            document.getElementById('searchResults').classList.add('hidden');
            alert('Friend request sent!');
        }

        async function loadFriendRequests() {
            const response = await fetch('/api/friend/requests', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            
            document.getElementById('requestCount').textContent = data.requests ? data.requests.length : 0;
        }

        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            if (tab === 'requests') {
                showRequestsModal();
            }
        }

        async function showRequestsModal() {
            const response = await fetch('/api/friend/requests', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            
            const list = document.getElementById('requestsList');
            if (data.requests && data.requests.length > 0) {
                list.innerHTML = data.requests.map(req => `
                    <div class="request-item">
                        <span>${escapeHtml(req.sender)}</span>
                        <div class="request-actions">
                            <button class="btn-accept" onclick="respondToRequest('${escapeHtml(req.sender)}', true)">Accept</button>
                            <button class="btn-decline" onclick="respondToRequest('${escapeHtml(req.sender)}', false)">Decline</button>
                        </div>
                    </div>
                `).join('');
            } else {
                list.innerHTML = '<p style="text-align: center; color: #6c757d;">No pending requests</p>';
            }
            document.getElementById('requestsModal').classList.add('active');
        }

        async function respondToRequest(sender, accept) {
            await fetch('/api/friend/respond', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({sender, accept})
            });
            loadFriendRequests();
            showRequestsModal();
            loadChats();
        }

        function showCreateChatModal() {
            document.getElementById('createChatModal').classList.add('active');
        }

        async function createGroupChat() {
            const name = document.getElementById('newChatName').value.trim();
            const membersStr = document.getElementById('newChatMembers').value.trim();
            const members = membersStr ? membersStr.split(',').map(m => m.trim()).filter(m => m) : [];
            
            if (!name) {
                alert('Please enter a group name');
                return;
            }
            
            const response = await fetch('/api/user/chats', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({name, members})
            });
            const data = await response.json();
            
            if (data.success) {
                closeModal('createChatModal');
                document.getElementById('newChatName').value = '';
                document.getElementById('newChatMembers').value = '';
                loadChats();
            } else {
                alert(data.message);
            }
        }

        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            return date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
        }
    </script>
</body>
</html>
"""

async def handle_client(request: web.Request):
    """Handle WebSocket client connection."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    token = request.query.get('token')
    username = request.query.get('username')
    
    if not token or not validate_user_session(token):
        await ws.close()
        return ws
    
    if username:
        clients[username] = ws
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                action = data.get("action")
                
                if action == "message" and username:
                    chat_id = data.get("chat_id")
                    message = data.get("message")
                    if chat_id and message:
                        timestamp = datetime.now().isoformat()
                        save_chat_message(chat_id, username, message, timestamp)
                        
                        # Notify all members of the chat
                        members = get_chat_members(chat_id)
                        chat_msg = json.dumps({
                            "type": "new_message",
                            "chat_id": chat_id,
                            "sender_username": username,
                            "message": message,
                            "timestamp": timestamp
                        })
                        for member in members:
                            if member in clients:
                                try:
                                    await clients[member].send_str(chat_msg)
                                except:
                                    pass
                                
                                # Also notify about chat update
                                update_msg = json.dumps({"type": "chat_update"})
                                try:
                                    await clients[member].send_str(update_msg)
                                except:
                                    pass
                                
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
                
    except Exception:
        pass
    finally:
        if username:
            clients.pop(username, None)
    
    return ws

async def user_register_handler(request: web.Request):
    """Handle user registration."""
    try:
        data = await request.json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return web.json_response({'success': False, 'message': 'Username and password required'}, status=400)
        
        result = register_user(username, password)
        return web.json_response(result) if result['success'] else web.json_response(result, status=400)
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
        return web.json_response(result) if result['success'] else web.json_response(result, status=401)
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
    """Create a new group chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        name = data.get('name', '').strip()
        members = data.get('members', [])
        
        if not name:
            return web.json_response({'success': False, 'message': 'Chat name required'}, status=400)
        
        result = create_chat(name, username, members)
        if result['success']:
            # Notify members
            update_msg = json.dumps({"type": "chat_update"})
            for member in members:
                if member in clients:
                    try:
                        await clients[member].send_str(update_msg)
                    except:
                        pass
            return web.json_response(result)
        else:
            return web.json_response(result, status=400)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def get_chat_messages_handler(request: web.Request):
    """Get messages for a specific chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
    members = get_chat_members(chat_id)
    
    if username not in members:
        return web.json_response({'error': 'Access denied'}, status=403)
    
    messages = get_chat_messages(chat_id)
    return web.json_response({'messages': messages})

async def send_chat_message_handler(request: web.Request):
    """Send a message to a chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
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
        
        # Notify all members
        chat_msg = json.dumps({
            "type": "new_message",
            "chat_id": chat_id,
            "sender_username": username,
            "message": message,
            "timestamp": timestamp
        })
        for member in members:
            if member in clients:
                try:
                    await clients[member].send_str(chat_msg)
                except:
                    pass
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def get_chat_members_handler(request: web.Request):
    """Get members of a chat."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    chat_id = int(request.match_info['chat_id'])
    members = get_chat_members(chat_id)
    
    return web.json_response({'members': members})

async def search_users_handler(request: web.Request):
    """Search for users."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    query = request.query.get('q', '')
    users = search_users(query, username)
    return web.json_response({'users': users})

async def send_friend_request_handler(request: web.Request):
    """Send a friend request."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        target_user = data.get('target_user', '').strip()
        
        if not target_user or target_user == username:
            return web.json_response({'success': False, 'message': 'Invalid target user'}, status=400)
        
        result = send_friend_request(username, target_user)
        
        if result['success'] and target_user in clients:
            try:
                await clients[target_user].send_str(json.dumps({"type": "friend_request"}))
            except:
                pass
        
        return web.json_response(result)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def get_friend_requests_handler(request: web.Request):
    """Get friend requests."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    requests = get_friend_requests(username)
    return web.json_response({'requests': requests})

async def respond_to_friend_request_handler(request: web.Request):
    """Respond to a friend request."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = validate_user_session(token)
    
    if not username:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        data = await request.json()
        sender = data.get('sender', '').strip()
        accept = data.get('accept', False)
        
        if not sender:
            return web.json_response({'success': False, 'message': 'Sender required'}, status=400)
        
        result = respond_to_friend_request(sender, username, accept)
        
        if result['success'] and accept:
            # Notify the sender
            if sender in clients:
                try:
                    await clients[sender].send_str(json.dumps({"type": "friend_request_accepted"}))
                except:
                    pass
        
        return web.json_response(result)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def http_handler(request: web.Request):
    """Handle HTTP requests for the main page."""
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def on_shutdown(app):
    """Close all WebSocket connections on shutdown."""
    for client in clients.values():
        await client.close()
    clients.clear()

def create_app():
    """Create and configure the aiohttp application."""
    app = web.Application()
    app.router.add_get('/', http_handler)
    app.router.add_get('/ws', handle_client)
    
    # User authentication API routes
    app.router.add_post('/api/user/register', user_register_handler)
    app.router.add_post('/api/user/login', user_login_handler)
    app.router.add_get('/api/user/chats', user_chats_handler)
    app.router.add_post('/api/user/chats', create_chat_handler)
    
    # Chat routes
    app.router.add_get('/api/chat/{chat_id}/messages', get_chat_messages_handler)
    app.router.add_post('/api/chat/{chat_id}/messages', send_chat_message_handler)
    app.router.add_get('/api/chat/{chat_id}/members', get_chat_members_handler)
    
    # User search
    app.router.add_get('/api/users/search', search_users_handler)
    
    # Friend requests
    app.router.add_post('/api/friend/request', send_friend_request_handler)
    app.router.add_get('/api/friend/requests', get_friend_requests_handler)
    app.router.add_post('/api/friend/respond', respond_to_friend_request_handler)
    
    app.on_shutdown.append(on_shutdown)
    return app

def main():
    """Start the WebSocket server with HTTP support."""
    import os
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Secure Messenger server starting on http://0.0.0.0:{port}")
    print(f"📝 Default admin: {ADMIN_USERNAME} / admin123")
    
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
