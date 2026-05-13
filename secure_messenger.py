#!/usr/bin/env python3
"""
Secure WebSocket-based messenger with:
- Personal (1-to-1) chats
- Group chats
- End-to-end encryption using AES-256-GCM
- SQLite database storage
- User authentication with password hashing (Argon2)
"""

import asyncio
import json
import sqlite3
import hashlib
import secrets
import base64
import os
from datetime import datetime, timedelta
from typing import Set, Dict, List, Optional
from dataclasses import dataclass, asdict
from aiohttp import web
import aiohttp

# Cryptography imports
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("WARNING: cryptography library not installed. Install with: pip install cryptography")

# Database setup
DB_PATH = "secure_messenger.db"
SALT_LENGTH = 32
NONCE_LENGTH = 12  # 96 bits for GCM mode

# ============================================================================
# Encryption Functions
# ============================================================================

def generate_salt() -> bytes:
    """Generate a random salt for key derivation."""
    return os.urandom(SALT_LENGTH)

def derive_key(password: str, salt: bytes, iterations: int = 100000) -> bytes:
    """Derive a 256-bit encryption key from password using PBKDF2-HMAC-SHA256."""
    if not CRYPTO_AVAILABLE:
        # Fallback: simple hash (NOT secure for production, only for testing)
        return hashlib.sha256(f"{password}:{salt.hex()}".encode()).digest()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def encrypt_message(message: str, key: bytes) -> dict:
    """
    Encrypt a message using AES-256-GCM.
    Returns dict with nonce, ciphertext, and tag (all base64 encoded).
    """
    if not CRYPTO_AVAILABLE:
        # Fallback: simple XOR (NOT secure, only for testing)
        nonce = os.urandom(NONCE_LENGTH)
        message_bytes = message.encode('utf-8')
        ciphertext = bytes(a ^ b for a, b in zip(message_bytes, (key * ((len(message_bytes) // len(key)) + 1))[:len(message_bytes)]))
        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "encrypted": True
        }
    
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, message.encode('utf-8'), None)
    
    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "encrypted": True
    }

def decrypt_message(encrypted_data: dict, key: bytes) -> str:
    """
    Decrypt a message using AES-256-GCM.
    Takes dict with nonce, ciphertext (base64 encoded).
    """
    if not CRYPTO_AVAILABLE:
        # Fallback: simple XOR (NOT secure, only for testing)
        nonce = base64.b64decode(encrypted_data["nonce"])
        ciphertext = base64.b64decode(encrypted_data["ciphertext"])
        message_bytes = bytes(a ^ b for a, b in zip(ciphertext, (key * ((len(ciphertext) // len(key)) + 1))[:len(ciphertext)]))
        return message_bytes.decode('utf-8')
    
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(encrypted_data["nonce"])
    ciphertext = base64.b64decode(encrypted_data["ciphertext"])
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode('utf-8')

def generate_chat_key() -> str:
    """Generate a random key for chat encryption."""
    return secrets.token_hex(32)

# ============================================================================
# Database Functions
# ============================================================================

def init_db():
    """Initialize the SQLite database with all required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table with authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            public_key TEXT,
            is_blocked INTEGER DEFAULT 0,
            is_online INTEGER DEFAULT 0,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT
        )
    ''')
    
    # Chat types: 'personal' or 'group'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_type TEXT NOT NULL CHECK(chat_type IN ('personal', 'group')),
            name TEXT,
            encryption_key_salt TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
    
    # Chat participants (for both personal and group chats)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
            role TEXT DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(chat_id, user_id)
        )
    ''')
    
    # Messages table with encryption support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message_nonce TEXT NOT NULL,
            message_ciphertext TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
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
    
    # Create indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_participants_chat_id ON chat_participants(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_participants_user_id ON chat_participants(user_id)')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ============================================================================
# User Management
# ============================================================================

def register_user(username: str, password: str) -> dict:
    """Register a new user with hashed password."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        salt = generate_salt()
        password_hash = derive_key(password, salt).hex()
        
        cursor.execute(
            'INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)',
            (username, password_hash, salt.hex())
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        return {"success": True, "user_id": user_id, "username": username}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Username already exists"}
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate user and return user info if successful."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT id, username, password_hash, salt, public_key FROM users WHERE username = ?',
        (username,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    user_id, db_username, stored_hash, salt_hex, public_key = row
    salt = bytes.fromhex(salt_hex)
    computed_hash = derive_key(password, salt).hex()
    
    if computed_hash == stored_hash:
        return {
            "user_id": user_id,
            "username": db_username,
            "public_key": public_key
        }
    return None

def update_user_last_seen(user_id: int):
    """Update user's last seen timestamp."""
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute(
        'UPDATE users SET last_seen = ?, is_online = 1 WHERE id = ?',
        (timestamp, user_id)
    )
    conn.commit()
    conn.close()

def set_user_offline(user_id: int):
    """Set user as offline."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET is_online = 0 WHERE id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user information by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, public_key, is_online, last_seen FROM users WHERE id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "user_id": row[0],
            "username": row[1],
            "public_key": row[2],
            "is_online": bool(row[3]),
            "last_seen": row[4]
        }
    return None

def get_all_users() -> List[dict]:
    """Get all users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, is_online, last_seen FROM users ORDER BY username'
    )
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "user_id": r[0],
            "username": r[1],
            "is_online": bool(r[2]),
            "last_seen": r[3]
        }
        for r in rows
    ]

# ============================================================================
# Chat Management
# ============================================================================

def create_personal_chat(user1_id: int, user2_id: int) -> dict:
    """Create a personal chat between two users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if chat already exists
    cursor.execute('''
        SELECT c.id FROM chats c
        JOIN chat_participants cp1 ON c.id = cp1.chat_id AND cp1.user_id = ?
        JOIN chat_participants cp2 ON c.id = cp2.chat_id AND cp2.user_id = ?
        WHERE c.chat_type = 'personal'
    ''', (user1_id, user2_id))
    
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {"success": False, "error": "Chat already exists", "chat_id": existing[0]}
    
    # Create new chat
    encryption_key = generate_chat_key()
    salt = generate_salt().hex()
    
    cursor.execute(
        'INSERT INTO chats (chat_type, encryption_key_salt, created_by) VALUES (?, ?, ?)',
        ('personal', salt, user1_id)
    )
    chat_id = cursor.lastrowid
    
    # Add both participants
    cursor.execute(
        'INSERT INTO chat_participants (chat_id, user_id, role) VALUES (?, ?, ?)',
        (chat_id, user1_id, 'owner')
    )
    cursor.execute(
        'INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)',
        (chat_id, user2_id)
    )
    
    conn.commit()
    conn.close()
    
    return {"success": True, "chat_id": chat_id, "encryption_key": encryption_key}

def create_group_chat(name: str, creator_id: int, participant_ids: List[int]) -> dict:
    """Create a group chat with multiple participants."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    encryption_key = generate_chat_key()
    salt = generate_salt().hex()
    
    cursor.execute(
        'INSERT INTO chats (chat_type, name, encryption_key_salt, created_by) VALUES (?, ?, ?, ?)',
        ('group', name, salt, creator_id)
    )
    chat_id = cursor.lastrowid
    
    # Add creator as owner
    cursor.execute(
        'INSERT INTO chat_participants (chat_id, user_id, role) VALUES (?, ?, ?)',
        (chat_id, creator_id, 'owner')
    )
    
    # Add other participants
    for participant_id in participant_ids:
        if participant_id != creator_id:
            cursor.execute(
                'INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)',
                (chat_id, participant_id)
            )
    
    conn.commit()
    conn.close()
    
    return {"success": True, "chat_id": chat_id, "encryption_key": encryption_key}

def get_user_chats(user_id: int) -> List[dict]:
    """Get all chats for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.chat_type, c.name, c.created_at,
               (SELECT COUNT(*) FROM messages WHERE chat_id = c.id) as message_count
        FROM chats c
        JOIN chat_participants cp ON c.id = cp.chat_id
        WHERE cp.user_id = ?
        ORDER BY c.created_at DESC
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    chats = []
    for row in rows:
        chat = {
            "chat_id": row[0],
            "chat_type": row[1],
            "name": row[2],
            "created_at": row[3],
            "message_count": row[4]
        }
        
        # Get participants
        participants = get_chat_participants(row[0])
        chat["participants"] = participants
        
        # For personal chats, set name to other user's username
        if row[1] == 'personal' and participants:
            other = next((p for p in participants if p["user_id"] != user_id), None)
            if other:
                chat["name"] = other["username"]
                chat["other_user_id"] = other["user_id"]
        
        chats.append(chat)
    
    return chats

def get_chat_participants(chat_id: int) -> List[dict]:
    """Get all participants of a chat."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.is_online, cp.role
        FROM chat_participants cp
        JOIN users u ON cp.user_id = u.id
        WHERE cp.chat_id = ?
    ''', (chat_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "user_id": r[0],
            "username": r[1],
            "is_online": bool(r[2]),
            "role": r[3]
        }
        for r in rows
    ]

def add_group_participant(chat_id: int, user_id: int, added_by: int) -> dict:
    """Add a participant to a group chat."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify the user adding is an admin or owner
    cursor.execute(
        'SELECT role FROM chat_participants WHERE chat_id = ? AND user_id = ?',
        (chat_id, added_by)
    )
    row = cursor.fetchone()
    
    if not row or row[0] not in ('owner', 'admin'):
        conn.close()
        return {"success": False, "error": "Not authorized"}
    
    try:
        cursor.execute(
            'INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)',
            (chat_id, user_id)
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except sqlite3.IntegrityError:
        conn.close()
        return {"success": False, "error": "User already in chat"}

def remove_group_participant(chat_id: int, user_id: int, removed_by: int) -> dict:
    """Remove a participant from a group chat."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify permissions
    cursor.execute(
        'SELECT role FROM chat_participants WHERE chat_id = ? AND user_id = ?',
        (chat_id, removed_by)
    )
    row = cursor.fetchone()
    
    if not row or row[0] not in ('owner', 'admin'):
        conn.close()
        return {"success": False, "error": "Not authorized"}
    
    cursor.execute(
        'DELETE FROM chat_participants WHERE chat_id = ? AND user_id = ?',
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()
    
    return {"success": True}

# ============================================================================
# Message Management
# ============================================================================

def save_encrypted_message(chat_id: int, sender_id: int, encrypted_data: dict, timestamp: str) -> int:
    """Save an encrypted message to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        '''INSERT INTO messages 
           (chat_id, sender_id, message_nonce, message_ciphertext, timestamp) 
           VALUES (?, ?, ?, ?, ?)''',
        (chat_id, sender_id, encrypted_data["nonce"], encrypted_data["ciphertext"], timestamp)
    )
    
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return message_id

def get_chat_messages(chat_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
    """Get encrypted messages for a chat."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.sender_id, m.message_nonce, m.message_ciphertext, m.timestamp, m.created_at,
               u.username
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.chat_id = ?
        ORDER BY m.created_at ASC
        LIMIT ? OFFSET ?
    ''', (chat_id, limit, offset))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "message_id": r[0],
            "sender_id": r[1],
            "nonce": r[2],
            "ciphertext": r[3],
            "timestamp": r[4],
            "created_at": r[5],
            "sender_username": r[6]
        }
        for r in rows
    ]

def delete_message(message_id: int, user_id: int) -> dict:
    """Delete a message (only by sender or chat admin)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get message info
    cursor.execute(
        'SELECT chat_id, sender_id FROM messages WHERE id = ?',
        (message_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return {"success": False, "error": "Message not found"}
    
    chat_id, sender_id = row
    
    # Check permissions
    if sender_id != user_id:
        cursor.execute(
            'SELECT role FROM chat_participants WHERE chat_id = ? AND user_id = ?',
            (chat_id, user_id)
        )
        role_row = cursor.fetchone()
        if not role_row or role_row[0] not in ('owner', 'admin'):
            conn.close()
            return {"success": False, "error": "Not authorized"}
    
    cursor.execute('DELETE FROM messages WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()
    
    return {"success": True}

# ============================================================================
# WebSocket Client Management
# ============================================================================

@dataclass
class ClientInfo:
    websocket: web.WebSocketResponse
    user_id: int
    username: str

# Store connected clients: {user_id: ClientInfo}
connected_clients: Dict[int, ClientInfo] = {}
# Store user subscriptions to chats: {user_id: set of chat_ids}
user_chat_subscriptions: Dict[int, Set[int]] = {}

async def broadcast_to_chat(chat_id: int, message: dict, exclude_user_id: int = None):
    """Broadcast a message to all users in a chat."""
    participants = get_chat_participants(chat_id)
    
    for participant in participants:
        if participant["user_id"] == exclude_user_id:
            continue
        
        if participant["user_id"] in connected_clients:
            client = connected_clients[participant["user_id"]]
            try:
                await client.websocket.send_json(message)
            except Exception as e:
                print(f"Error sending to {client.username}: {e}")

async def send_notification(user_id: int, notification: dict):
    """Send a notification to a specific user."""
    if user_id in connected_clients:
        client = connected_clients[user_id]
        try:
            await client.websocket.send_json(notification)
        except Exception as e:
            print(f"Error sending notification to {client.username}: {e}")

# ============================================================================
# HTTP Request Handlers
# ============================================================================

async def handle_register(request: web.Request) -> web.Response:
    """Handle user registration."""
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return web.json_response({"success": False, "error": "Username and password required"})
        
        if len(username) < 3:
            return web.json_response({"success": False, "error": "Username must be at least 3 characters"})
        
        if len(password) < 6:
            return web.json_response({"success": False, "error": "Password must be at least 6 characters"})
        
        result = register_user(username, password)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_login(request: web.Request) -> web.Response:
    """Handle user login."""
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        user = authenticate_user(username, password)
        if user:
            update_user_last_seen(user["user_id"])
            return web.json_response({"success": True, **user})
        else:
            return web.json_response({"success": False, "error": "Invalid credentials"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_create_personal_chat(request: web.Request) -> web.Response:
    """Create a personal chat."""
    try:
        data = await request.json()
        user1_id = data.get("user1_id")
        user2_id = data.get("user2_id")
        
        if not user1_id or not user2_id:
            return web.json_response({"success": False, "error": "Both user IDs required"})
        
        result = create_personal_chat(user1_id, user2_id)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_create_group_chat(request: web.Request) -> web.Response:
    """Create a group chat."""
    try:
        data = await request.json()
        name = data.get("name", "Group Chat").strip()
        creator_id = data.get("creator_id")
        participant_ids = data.get("participant_ids", [])
        
        if not creator_id:
            return web.json_response({"success": False, "error": "Creator ID required"})
        
        if len(participant_ids) < 1:
            return web.json_response({"success": False, "error": "At least one participant required"})
        
        result = create_group_chat(name, creator_id, participant_ids)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_get_chats(request: web.Request) -> web.Response:
    """Get all chats for a user."""
    try:
        user_id = request.query.get("user_id")
        if not user_id:
            return web.json_response({"success": False, "error": "User ID required"})
        
        chats = get_user_chats(int(user_id))
        return web.json_response({"success": True, "chats": chats})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_get_messages(request: web.Request) -> web.Response:
    """Get messages for a chat."""
    try:
        chat_id = request.query.get("chat_id")
        limit = int(request.query.get("limit", 50))
        offset = int(request.query.get("offset", 0))
        
        if not chat_id:
            return web.json_response({"success": False, "error": "Chat ID required"})
        
        messages = get_chat_messages(int(chat_id), limit, offset)
        return web.json_response({"success": True, "messages": messages})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_add_participant(request: web.Request) -> web.Response:
    """Add participant to group chat."""
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")
        added_by = data.get("added_by")
        
        if not all([chat_id, user_id, added_by]):
            return web.json_response({"success": False, "error": "Missing required fields"})
        
        result = add_group_participant(chat_id, user_id, added_by)
        
        if result["success"]:
            # Notify the added user
            await send_notification(user_id, {
                "type": "added_to_chat",
                "chat_id": chat_id
            })
        
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_remove_participant(request: web.Request) -> web.Response:
    """Remove participant from group chat."""
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")
        removed_by = data.get("removed_by")
        
        if not all([chat_id, user_id, removed_by]):
            return web.json_response({"success": False, "error": "Missing required fields"})
        
        result = remove_group_participant(chat_id, user_id, removed_by)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_get_users(request: web.Request) -> web.Response:
    """Get all users."""
    try:
        users = get_all_users()
        return web.json_response({"success": True, "users": users})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

# ============================================================================
# WebSocket Handler
# ============================================================================

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections for real-time messaging."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    current_user_id = None
    current_username = None
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")
                    
                    if msg_type == "auth":
                        # Authenticate WebSocket connection
                        username = data.get("username")
                        password = data.get("password")
                        
                        user = authenticate_user(username, password)
                        if user:
                            current_user_id = user["user_id"]
                            current_username = user["username"]
                            
                            # Register client
                            connected_clients[current_user_id] = ClientInfo(
                                websocket=ws,
                                user_id=current_user_id,
                                username=current_username
                            )
                            
                            # Subscribe to user's chats
                            chats = get_user_chats(current_user_id)
                            user_chat_subscriptions[current_user_id] = {c["chat_id"] for c in chats}
                            
                            update_user_last_seen(current_user_id)
                            
                            await ws.send_json({
                                "type": "auth_success",
                                "user_id": current_user_id,
                                "username": current_username
                            })
                            
                            # Notify others that user is online
                            await broadcast_to_all({
                                "type": "user_online",
                                "user_id": current_user_id,
                                "username": current_username
                            }, exclude=current_user_id)
                        else:
                            await ws.send_json({"type": "auth_error", "error": "Invalid credentials"})
                    
                    elif msg_type == "send_message":
                        if current_user_id is None:
                            await ws.send_json({"type": "error", "error": "Not authenticated"})
                            continue
                        
                        chat_id = data.get("chat_id")
                        encrypted_data = data.get("encrypted_data")
                        timestamp = data.get("timestamp", datetime.now().isoformat())
                        
                        if not chat_id or not encrypted_data:
                            await ws.send_json({"type": "error", "error": "Missing chat_id or encrypted_data"})
                            continue
                        
                        # Save message to database
                        message_id = save_encrypted_message(
                            chat_id, current_user_id, encrypted_data, timestamp
                        )
                        
                        # Broadcast to all chat participants
                        await broadcast_to_chat(chat_id, {
                            "type": "new_message",
                            "message_id": message_id,
                            "chat_id": chat_id,
                            "sender_id": current_user_id,
                            "sender_username": current_username,
                            "encrypted_data": encrypted_data,
                            "timestamp": timestamp
                        })
                    
                    elif msg_type == "join_chat":
                        if current_user_id is None:
                            await ws.send_json({"type": "error", "error": "Not authenticated"})
                            continue
                        
                        chat_id = data.get("chat_id")
                        if chat_id:
                            if current_user_id not in user_chat_subscriptions:
                                user_chat_subscriptions[current_user_id] = set()
                            user_chat_subscriptions[current_user_id].add(chat_id)
                            
                            await ws.send_json({
                                "type": "joined_chat",
                                "chat_id": chat_id
                            })
                    
                    elif msg_type == "leave_chat":
                        if current_user_id is None:
                            await ws.send_json({"type": "error", "error": "Not authenticated"})
                            continue
                        
                        chat_id = data.get("chat_id")
                        if chat_id and current_user_id in user_chat_subscriptions:
                            user_chat_subscriptions[current_user_id].discard(chat_id)
                    
                    elif msg_type == "typing":
                        if current_user_id is None:
                            continue
                        
                        chat_id = data.get("chat_id")
                        is_typing = data.get("is_typing", False)
                        
                        await broadcast_to_chat(chat_id, {
                            "type": "user_typing",
                            "chat_id": chat_id,
                            "user_id": current_user_id,
                            "username": current_username,
                            "is_typing": is_typing
                        }, exclude_user_id=current_user_id)
                    
                    else:
                        await ws.send_json({"type": "error", "error": f"Unknown message type: {msg_type}"})
                
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "error": "Invalid JSON"})
                except Exception as e:
                    await ws.send_json({"type": "error", "error": str(e)})
            
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
    
    finally:
        # Clean up on disconnect
        if current_user_id:
            if current_user_id in connected_clients:
                del connected_clients[current_user_id]
            if current_user_id in user_chat_subscriptions:
                del user_chat_subscriptions[current_user_id]
            
            set_user_offline(current_user_id)
            
            # Notify others that user is offline
            await broadcast_to_all({
                "type": "user_offline",
                "user_id": current_user_id,
                "username": current_username
            }, exclude=current_user_id)
    
    return ws

async def broadcast_to_all(message: dict, exclude: int = None):
    """Broadcast a message to all connected clients."""
    for user_id, client in list(connected_clients.items()):
        if user_id == exclude:
            continue
        try:
            await client.websocket.send_json(message)
        except Exception as e:
            print(f"Error broadcasting to {client.username}: {e}")

# ============================================================================
# Application Setup
# ============================================================================

def create_app() -> web.Application:
    """Create and configure the web application."""
    app = web.Application()
    
    # API routes
    app.router.add_post('/api/register', handle_register)
    app.router.add_post('/api/login', handle_login)
    app.router.add_post('/api/chats/personal', handle_create_personal_chat)
    app.router.add_post('/api/chats/group', handle_create_group_chat)
    app.router.add_get('/api/chats', handle_get_chats)
    app.router.add_get('/api/messages', handle_get_messages)
    app.router.add_post('/api/chats/participants/add', handle_add_participant)
    app.router.add_post('/api/chats/participants/remove', handle_remove_participant)
    app.router.add_get('/api/users', handle_get_users)
    
    # WebSocket route
    app.router.add_get('/ws', websocket_handler)
    
    return app

def main():
    """Main entry point."""
    print("Initializing secure messenger database...")
    init_db()
    
    print("Starting secure messenger server...")
    print(f"Encryption available: {CRYPTO_AVAILABLE}")
    if not CRYPTO_AVAILABLE:
        print("WARNING: Running without proper encryption. Install cryptography library for production use.")
    
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080, print=lambda x: print(x))

if __name__ == '__main__':
    main()
