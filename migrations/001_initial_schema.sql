-- Initial database schema for Secure Messenger
-- Migration 001: Create all tables

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_blocked INTEGER DEFAULT 0,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT
);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    session_token TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users(username)
);

-- Admin sessions table
CREATE TABLE IF NOT EXISTS admin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Audit log table for admin actions
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_username TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user TEXT,
    details TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- User reports table
CREATE TABLE IF NOT EXISTS user_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_username TEXT NOT NULL,
    reported_username TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    resolved_by TEXT
);

-- System statistics table
CREATE TABLE IF NOT EXISTS system_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_name TEXT UNIQUE NOT NULL,
    stat_value TEXT,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Friend requests table
CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_username TEXT NOT NULL,
    receiver_username TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_username) REFERENCES users(username),
    FOREIGN KEY (receiver_username) REFERENCES users(username),
    UNIQUE(sender_username, receiver_username)
);

-- Friends table
CREATE TABLE IF NOT EXISTS friends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1 TEXT NOT NULL,
    user2 TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user1) REFERENCES users(username),
    FOREIGN KEY (user2) REFERENCES users(username),
    UNIQUE(user1, user2)
);

-- Chats table (for group chats)
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    creator_username TEXT NOT NULL,
    is_group INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_username) REFERENCES users(username)
);

-- Chat members table
CREATE TABLE IF NOT EXISTS chat_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (username) REFERENCES users(username),
    UNIQUE(chat_id, username)
);

-- Messages table (for all chat types)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    sender_username TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id),
    FOREIGN KEY (sender_username) REFERENCES users(username)
);
