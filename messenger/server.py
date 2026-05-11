#!/usr/bin/env python3
"""Simple WebSocket-based messenger server."""

import asyncio
import json
from datetime import datetime
from typing import Set, Dict
import websockets

# Store connected clients: {username: websocket}
clients: Dict[str, websockets.WebSocketServerProtocol] = {}
# Store all usernames
usernames: Set[str] = set()


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


async def main():
    """Start the WebSocket server."""
    print("🚀 Messenger server starting on ws://0.0.0.0:8765")
    async with websockets.serve(handle_client, "0.0.0.0", 8765):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
