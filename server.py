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
import os

# Database setup
DB_PATH = os.environ.get("MESSENGER_DB_PATH", "messenger.db")
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
    
    # Create default admin user if not exists
    cursor.execute('SELECT username FROM users WHERE username = ?', (ADMIN_USERNAME,))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            (ADMIN_USERNAME, ADMIN_PASSWORD_HASH)
        )
        print(f"✅ Default admin user created: {ADMIN_USERNAME}")
    
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
    
    # Audit log table for admin actions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_username TEXT NOT NULL,
            action TEXT NOT NULL,
            target_user TEXT,
            details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_username TEXT NOT NULL,
            reported_username TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            resolved_by TEXT
        )
    ''')
    
    # System statistics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_name TEXT UNIQUE NOT NULL,
            stat_value TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
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

def block_user(username: str, blocked: bool, admin_username: str = None):
    """Block or unblock a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET is_blocked = ? WHERE username = ?',
        (1 if blocked else 0, username)
    )
    conn.commit()
    
    # Log the action
    if admin_username:
        cursor.execute(
            'INSERT INTO audit_log (admin_username, action, target_user, details) VALUES (?, ?, ?, ?)',
            (admin_username, 'block_user' if blocked else 'unblock_user', username, f'Blocked: {blocked}')
        )
        conn.commit()
    
    conn.close()

def log_admin_action(admin_username: str, action: str, target_user: str = None, details: str = None):
    """Log an admin action to the audit log."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO audit_log (admin_username, action, target_user, details) VALUES (?, ?, ?, ?)',
        (admin_username, action, target_user, details)
    )
    conn.commit()
    conn.close()

def get_audit_logs(limit: int = 100) -> List[dict]:
    """Get recent audit logs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, admin_username, action, target_user, details, timestamp 
        FROM audit_log 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "admin_username": r[1], "action": r[2], "target_user": r[3], "details": r[4], "timestamp": r[5]}
        for r in rows
    ]

def submit_user_report(reporter: str, reported: str, reason: str) -> dict:
    """Submit a user report."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO user_reports (reporter_username, reported_username, reason) VALUES (?, ?, ?)',
            (reporter, reported, reason)
        )
        conn.commit()
        return {"success": True, "message": "Report submitted"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "Report already exists"}
    finally:
        conn.close()

def get_user_reports(status: str = 'pending') -> List[dict]:
    """Get user reports by status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, reporter_username, reported_username, reason, status, created_at 
        FROM user_reports 
        WHERE status = ? 
        ORDER BY created_at DESC
    ''', (status,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "reporter": r[1], "reported": r[2], "reason": r[3], "status": r[4], "created_at": r[5]}
        for r in rows
    ]

def resolve_user_report(report_id: int, admin_username: str, status: str) -> dict:
    """Resolve a user report."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE user_reports SET status = ?, resolved_at = CURRENT_TIMESTAMP, resolved_by = ? WHERE id = ?',
        (status, admin_username, report_id)
    )
    conn.commit()
    
    # Log the action
    cursor.execute(
        'INSERT INTO audit_log (admin_username, action, details) VALUES (?, ?, ?)',
        (admin_username, 'resolve_report', f'Report {report_id} resolved as {status}')
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Report resolved"}

def get_system_stats() -> dict:
    """Get system statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get total users
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Get blocked users
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
    blocked_users_count = cursor.fetchone()[0]
    
    # Get total chats
    cursor.execute('SELECT COUNT(*) FROM chats')
    total_chats = cursor.fetchone()[0]
    
    # Get total messages
    cursor.execute('SELECT COUNT(*) FROM messages')
    total_messages = cursor.fetchone()[0]
    
    # Get online users (from connected clients)
    online_users = len(clients)
    
    # Get pending reports
    cursor.execute("SELECT COUNT(*) FROM user_reports WHERE status = 'pending'")
    pending_reports = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_users": total_users,
        "blocked_users": blocked_users_count,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "online_users": online_users,
        "pending_reports": pending_reports
    }

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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#00f3ff">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="description" content="Secure Cyberpunk Messenger">
    <title>CYBER//MESSENGER</title>

    <!-- Favicon -->
    <link rel="icon" type="image/svg+xml" href="assets/favicon.svg">

    <!-- Google Fonts - Orbitron for cyberpunk look -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">

    <!-- Stylesheet -->
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <!-- Scanline overlay effect -->
    <div class="scanlines"></div>

    <!-- Glitch background elements -->
    <div class="cyber-grid"></div>

    <div class="login-modal" id="loginModal">
        <div class="login-box">
            <div class="cyber-title">
                <h2><span class="glitch" data-text="CYBER//MESSENGER">CYBER//MESSENGER</span></h2>
                <div class="subtitle">NEURAL LINK INTERFACE</div>
            </div>
            <div class="input-wrapper">
                <input type="text" id="usernameInput" placeholder="ENTER_CODENAME_" maxlength="20" autocomplete="off">
                <div class="input-glow"></div>
            </div>
            <button id="joinButton">
                <span class="btn-text">INITIALIZE_LINK</span>
                <span class="btn-glitch"></span>
            </button>
            <div class="decorative-corners"></div>
        </div>
    </div>

    <div class="container">
        <div class="header">
            <div class="header-top">
                <div class="system-status">
                    <span class="blink">●</span> SYSTEM ONLINE
                </div>
                <div class="time-display" id="timeDisplay">00:00:00</div>
            </div>
            <h1 class="cyber-heading"><span class="neon-text">CYBER</span>//<span class="neon-text-alt">MESSENGER</span></h1>
            <div class="users-list" id="usersList">
                <span class="label">[</span>CONNECTED_NETRUNNERS<span class="label">]:</span> <span id="userCount">0</span>
            </div>
            <div class="header-decoration"></div>
        </div>

        <div class="status disconnected" id="status">
            <span class="status-icon">◈</span>
            <span class="status-text">ESTABLISHING_NEURAL_CONNECTION...</span>
        </div>

        <div class="messages" id="messages">
            <div class="message system">
                <span class="system-prefix">>>></span>
                WELCOME_TO_THE_UNDERGROUND
                <span class="system-suffix"><<<</span>
            </div>
        </div>

        <div class="input-area">
            <div class="input-wrapper-cyber">
                <span class="input-prompt">></span>
                <input type="text" id="messageInput" placeholder="TRANSMIT_DATA..." maxlength="500" autocomplete="off">
                <div class="input-border"></div>
            </div>
            <button id="sendBtn">
                <span class="btn-text">TRANSMIT</span>
                <span class="btn-corners"></span>
            </button>
        </div>

        <!-- Decorative HUD elements -->
        <div class="hud-corner top-left"></div>
        <div class="hud-corner top-right"></div>
        <div class="hud-corner bottom-left"></div>
        <div class="hud-corner bottom-right"></div>
    </div>

    <!-- JavaScript -->
    <script src="js/app.js" defer></script>
</body>
</html>
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

async def serve_css(request: web.Request):
    """Serve the CSS stylesheet."""
    css_path = os.path.join(os.path.dirname(__file__), 'css', 'styles.css')
    try:
        with open(css_path, 'r') as f:
            css_content = f.read()
        return web.Response(text=css_content, content_type='text/css')
    except FileNotFoundError:
        return web.Response(text='CSS file not found', status=404)

async def serve_js(request: web.Request):
    """Serve the JavaScript file."""
    js_path = os.path.join(os.path.dirname(__file__), 'js', 'app.js')
    try:
        with open(js_path, 'r') as f:
            js_content = f.read()
        return web.Response(text=js_content, content_type='application/javascript')
    except FileNotFoundError:
        return web.Response(text='JS file not found', status=404)

# ============================================================================
# Admin API Handlers
# ============================================================================

async def admin_login_handler(request: web.Request):
    """Admin login handler."""
    try:
        data = await request.json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        # Check credentials
        if username != ADMIN_USERNAME:
            return web.json_response({'success': False, 'message': 'Invalid credentials'}, status=401)
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != ADMIN_PASSWORD_HASH:
            return web.json_response({'success': False, 'message': 'Invalid credentials'}, status=401)
        
        # Create admin session
        token = create_admin_session()
        
        # Log the action
        log_admin_action(username, 'admin_login', details='Admin logged in successfully')
        
        return web.json_response({'success': True, 'token': token, 'username': username})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_stats_handler(request: web.Request):
    """Get system statistics."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        stats = get_system_stats()
        return web.json_response({'success': True, 'stats': stats})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_users_handler(request: web.Request):
    """Get all users for admin panel."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        users = get_all_users()
        return web.json_response({'success': True, 'users': users})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_block_user_handler(request: web.Request):
    """Block or unblock a user."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        data = await request.json()
        username = data.get('username', '')
        blocked = data.get('blocked', True)
        
        if not username:
            return web.json_response({'success': False, 'message': 'Username required'}, status=400)
        
        # Get admin username from token (for logging)
        admin_username = ADMIN_USERNAME
        
        block_user(username, blocked, admin_username)
        
        return web.json_response({'success': True, 'message': f'User {username} {"blocked" if blocked else "unblocked"}'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_reports_handler(request: web.Request):
    """Get user reports."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        status = request.query.get('status', 'pending')
        reports = get_user_reports(status)
        return web.json_response({'success': True, 'reports': reports})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_resolve_report_handler(request: web.Request):
    """Resolve a user report."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        data = await request.json()
        report_id = data.get('report_id')
        status = data.get('status', 'resolved')
        
        if not report_id:
            return web.json_response({'success': False, 'message': 'Report ID required'}, status=400)
        
        result = resolve_user_report(report_id, ADMIN_USERNAME, status)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_logs_handler(request: web.Request):
    """Get audit logs."""
    try:
        # Validate admin session
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not validate_admin_session(token):
            return web.json_response({'success': False, 'message': 'Unauthorized'}, status=401)
        
        limit = int(request.query.get('limit', 100))
        logs = get_audit_logs(limit)
        return web.json_response({'success': True, 'logs': logs})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

async def admin_panel_handler(request: web.Request):
    """Serve admin panel HTML page."""
    admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - Secure Messenger</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .login-container { display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
        .login-box { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 400px; }
        .login-box h2 { color: #667eea; margin-bottom: 10px; text-align: center; }
        .login-box p { color: #6c757d; text-align: center; margin-bottom: 20px; }
        .login-box input { width: 100%; padding: 14px; margin-bottom: 15px; border: 2px solid #e9ecef; border-radius: 12px; font-size: 16px; }
        .login-box input:focus { outline: none; border-color: #667eea; }
        .login-box button { width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer; }
        .login-box button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }
        .login-box .hint { background: #fff3cd; border: 1px solid #ffc107; padding: 10px; border-radius: 8px; margin-bottom: 15px; font-size: 13px; color: #856404; }
        .login-box .hint strong { color: #667eea; }
        .admin-container { display: none; min-height: 100vh; }
        .admin-container.active { display: block; }
        .admin-header { background: white; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; justify-content: space-between; align-items: center; }
        .admin-header h1 { color: #667eea; }
        .logout-btn { background: #dc3545; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; }
        .admin-content { padding: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card h3 { color: #6c757d; font-size: 14px; margin-bottom: 10px; }
        .stat-card .value { font-size: 32px; font-weight: bold; color: #667eea; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { padding: 12px 24px; background: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .tab-btn.active { background: #667eea; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .data-table { width: 100%; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .data-table th, .data-table td { padding: 15px; text-align: left; border-bottom: 1px solid #f0f0f0; }
        .data-table th { background: #f8f9fa; font-weight: 600; color: #667eea; }
        .data-table tr:hover { background: #f8f9fa; }
        .status-badge { padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .status-badge.blocked { background: #f8d7da; color: #721c24; }
        .status-badge.active { background: #d4edda; color: #155724; }
        .status-badge.pending { background: #fff3cd; color: #856404; }
        .status-badge.resolved { background: #d1ecf1; color: #0c5460; }
        .action-btn { padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; margin-right: 5px; }
        .btn-block { background: #dc3545; color: white; }
        .btn-unblock { background: #28a745; color: white; }
        .btn-approve { background: #28a745; color: white; }
        .btn-reject { background: #dc3545; color: white; }
        .notification { position: fixed; top: 20px; right: 20px; padding: 15px 25px; background: #28a745; color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); z-index: 1000; display: none; }
        .log-entry { padding: 10px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: #6c757d; font-size: 12px; }
    </style>
</head>
<body>
    <div class="login-container" id="loginContainer">
        <div class="login-box">
            <h2>🔐 Admin Login</h2>
            <p>Enter your admin credentials</p>
            <div class="hint">💡 <strong>Password hint:</strong> Use special characters for better security! Default: admin123</div>
            <input type="text" id="adminUsername" placeholder="Username" value="admin">
            <input type="password" id="adminPassword" placeholder="Password">
            <button onclick="adminLogin()">Login</button>
            <p id="loginError" style="color: #dc3545; margin-top: 10px;"></p>
        </div>
    </div>

    <div class="admin-container" id="adminContainer">
        <div class="admin-header">
            <h1>🛡️ Admin Panel</h1>
            <button class="logout-btn" onclick="adminLogout()">Logout</button>
        </div>
        <div class="admin-content">
            <div class="stats-grid" id="statsGrid">
                <div class="stat-card"><h3>Total Users</h3><div class="value" id="statTotalUsers">-</div></div>
                <div class="stat-card"><h3>Blocked Users</h3><div class="value" id="statBlockedUsers">-</div></div>
                <div class="stat-card"><h3>Total Chats</h3><div class="value" id="statTotalChats">-</div></div>
                <div class="stat-card"><h3>Total Messages</h3><div class="value" id="statTotalMessages">-</div></div>
                <div class="stat-card"><h3>Online Users</h3><div class="value" id="statOnlineUsers">-</div></div>
                <div class="stat-card"><h3>Pending Reports</h3><div class="value" id="statPendingReports">-</div></div>
            </div>
            
            <div class="tabs">
                <button class="tab-btn active" onclick="showTab('users')">Users</button>
                <button class="tab-btn" onclick="showTab('reports')">Reports</button>
                <button class="tab-btn" onclick="showTab('logs')">Audit Logs</button>
            </div>
            
            <div class="tab-content active" id="usersTab">
                <div class="data-table">
                    <table>
                        <thead><tr><th>Username</th><th>Status</th><th>First Seen</th><th>Last Seen</th><th>Actions</th></tr></thead>
                        <tbody id="usersTableBody"></tbody>
                    </table>
                </div>
            </div>
            
            <div class="tab-content" id="reportsTab">
                <div class="data-table">
                    <table>
                        <thead><tr><th>ID</th><th>Reporter</th><th>Reported</th><th>Reason</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
                        <tbody id="reportsTableBody"></tbody>
                    </table>
                </div>
            </div>
            
            <div class="tab-content" id="logsTab">
                <div class="data-table" id="logsTable"></div>
            </div>
        </div>
    </div>

    <div class="notification" id="notification"></div>

    <script>
        let authToken = localStorage.getItem('adminToken');
        
        if (authToken) {
            showAdminPanel();
        }
        
        function showNotification(message, type = 'success') {
            const notif = document.getElementById('notification');
            notif.textContent = message;
            notif.style.background = type === 'error' ? '#dc3545' : '#28a745';
            notif.style.display = 'block';
            setTimeout(() => notif.style.display = 'none', 3000);
        }
        
        async function adminLogin() {
            const username = document.getElementById('adminUsername').value;
            const password = document.getElementById('adminPassword').value;
            
            try {
                const response = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                const data = await response.json();
                
                if (data.success) {
                    authToken = data.token;
                    localStorage.setItem('adminToken', authToken);
                    showAdminPanel();
                } else {
                    document.getElementById('loginError').textContent = data.message;
                }
            } catch (error) {
                document.getElementById('loginError').textContent = 'Connection error';
            }
        }
        
        function adminLogout() {
            localStorage.removeItem('adminToken');
            authToken = null;
            document.getElementById('loginContainer').style.display = 'flex';
            document.getElementById('adminContainer').classList.remove('active');
        }
        
        function showAdminPanel() {
            document.getElementById('loginContainer').style.display = 'none';
            document.getElementById('adminContainer').classList.add('active');
            loadStats();
            loadUsers();
        }
        
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabName + 'Tab').classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'reports') loadReports();
            if (tabName === 'logs') loadLogs();
        }
        
        async function loadStats() {
            const response = await fetch('/api/admin/stats', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            if (data.success) {
                const s = data.stats;
                document.getElementById('statTotalUsers').textContent = s.total_users;
                document.getElementById('statBlockedUsers').textContent = s.blocked_users;
                document.getElementById('statTotalChats').textContent = s.total_chats;
                document.getElementById('statTotalMessages').textContent = s.total_messages;
                document.getElementById('statOnlineUsers').textContent = s.online_users;
                document.getElementById('statPendingReports').textContent = s.pending_reports;
            }
        }
        
        async function loadUsers() {
            const response = await fetch('/api/admin/users', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            if (data.success) {
                const tbody = document.getElementById('usersTableBody');
                tbody.innerHTML = '';
                data.users.forEach(u => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${escapeHtml(u.username)}</td>
                        <td><span class="status-badge ${u.is_blocked ? 'blocked' : 'active'}">${u.is_blocked ? 'Blocked' : 'Active'}</span></td>
                        <td>${u.first_seen || '-'}</td>
                        <td>${u.last_seen || '-'}</td>
                        <td>
                            <button class="action-btn ${u.is_blocked ? 'btn-unblock' : 'btn-block'}" 
                                onclick="toggleUserBlock('${u.username}', ${!u.is_blocked})">
                                ${u.is_blocked ? 'Unblock' : 'Block'}
                            </button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
        }
        
        async function toggleUserBlock(username, blocked) {
            const response = await fetch('/api/admin/block', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({username, blocked})
            });
            const data = await response.json();
            if (data.success) {
                showNotification(`User ${username} ${blocked ? 'blocked' : 'unblocked'}`);
                loadUsers();
                loadStats();
            } else {
                showNotification(data.message, 'error');
            }
        }
        
        async function loadReports() {
            const response = await fetch('/api/admin/reports?status=pending', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            if (data.success) {
                const tbody = document.getElementById('reportsTableBody');
                tbody.innerHTML = '';
                data.reports.forEach(r => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>#${r.id}</td>
                        <td>${escapeHtml(r.reporter)}</td>
                        <td>${escapeHtml(r.reported)}</td>
                        <td>${escapeHtml(r.reason)}</td>
                        <td><span class="status-badge pending">Pending</span></td>
                        <td>${r.created_at}</td>
                        <td>
                            <button class="action-btn btn-approve" onclick="resolveReport(${r.id}, 'resolved')">Approve</button>
                            <button class="action-btn btn-reject" onclick="resolveReport(${r.id}, 'dismissed')">Dismiss</button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
        }
        
        async function resolveReport(reportId, status) {
            const response = await fetch('/api/admin/reports/resolve', {
                method: 'POST',
                headers: {'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json'},
                body: JSON.stringify({report_id: reportId, status})
            });
            const data = await response.json();
            if (data.success) {
                showNotification('Report resolved');
                loadReports();
                loadStats();
            }
        }
        
        async function loadLogs() {
            const response = await fetch('/api/admin/logs?limit=50', {
                headers: {'Authorization': 'Bearer ' + authToken}
            });
            const data = await response.json();
            if (data.success) {
                const container = document.getElementById('logsTable');
                container.innerHTML = '';
                data.logs.forEach(log => {
                    const entry = document.createElement('div');
                    entry.className = 'log-entry';
                    entry.innerHTML = `
                        <div><strong>${escapeHtml(log.admin_username)}</strong> - ${escapeHtml(log.action)} ${log.target_user ? 'on ' + escapeHtml(log.target_user) : ''}</div>
                        <div class="log-time">${log.timestamp} - ${log.details || ''}</div>
                    `;
                    container.appendChild(entry);
                });
            }
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
    """
    return web.Response(text=admin_html, content_type='text/html')

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
    app.router.add_get('/css/styles.css', serve_css)
    app.router.add_get('/js/app.js', serve_js)
    
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
    
    # Admin API routes
    app.router.add_post('/api/admin/login', admin_login_handler)
    app.router.add_get('/api/admin/stats', admin_stats_handler)
    app.router.add_get('/api/admin/users', admin_users_handler)
    app.router.add_post('/api/admin/block', admin_block_user_handler)
    app.router.add_get('/api/admin/reports', admin_reports_handler)
    app.router.add_post('/api/admin/reports/resolve', admin_resolve_report_handler)
    app.router.add_get('/api/admin/logs', admin_logs_handler)
    app.router.add_get('/admin', admin_panel_handler)
    
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
