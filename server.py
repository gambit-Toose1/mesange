from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Dependencies, HTTPException, status, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from database import engine, get_db, SessionLocal, init_db
from models import Base, User, Room, Message, hash_password, verify_password, generate_salt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uvicorn
import os
import logging
import time
from collections import defaultdict
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("\uD83D\uDCE2 Python Messenger Pro")
init_db()

app = FastAPI(title="Python Messenger Pro")

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"],
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("index.html"):
    print("\u26A0\uFE0F No index.html found!")
else:
    print("\u2705 index.html found")

# Rate limiting storage
rate_limit_store = defaultdict(list)
rate_limit_lock = Lock()

def check_rate_limit(username: str, limit: int = 5, window_seconds: int = 60) -> bool:
    """Check if user exceeded rate limit"""
    now = time.time()
    with rate_limit_lock:
        # Clean old entries
        rate_limit_store[username] = [t for t in rate_limit_store[username] if now - t < window_seconds]
        if len(rate_limit_store[username]) >= limit:
            return False
        rate_limit_store[username].append(now)
        return True

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.online_users = {}

    async def connect(self, websocket, room_id, username, user_id):
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append({
            "websocket": websocket,
            "username": username,
            "user_id": user_id
        })
        self.online_users[username] = {
            "websocket": websocket,
            "room_id": room_id,
            "user_id": user_id,
            "joined_at": datetime.utcnow()
        }
        logger.info(f"\u2705 {username} joined room {room_id}")

    def disconnect(self, websocket, room_id, username):
        if room_id in self.active_connections:
            self.active_connections[room_id] = [
                conn for conn in self.active_connections[room_id]
                if conn["websocket"] != websocket
            ]
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        if username in self.online_users:
            del self.online_users[username]
        logger.info(f"\uD83D\uDC4B {username} disconnected")

    async def broadcast_to_room(self, room_id, message):
        if room_id in self.active_connections:
            for conn in self.active_connections[room_id]:
                try:
                    await conn["websocket"].send_json(message)
                except:
                    pass

    async def kick_user(self, username):
        if username in self.online_users:
            try:
                await self.online_users[username]["websocket"].send_json({
                    "type": "kicked",
                    "content": "You have been banned from the chat"
                })
                await self.online_users[username]["websocket"].close()
            except:
                pass
            del self.online_users[username]
            logger.info(f"\uD83D\uDEAB {username} kicked")

    def get_online_users(self):
        return list(self.online_users.keys())

    def get_online_count(self):
        return len(self.online_users)

manager = ConnectionManager()

def get_current_user(username: str, db: Session):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if user.is_banned:
        raise HTTPException(status_code=403, detail="You are banned")
    return user

def check_admin(user: User):
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

def check_room_access(room: Room, user: User, db: Session):
    """Check if user has access to private room"""
    if not room.is_private:
        return True
    if room.created_by == user.id:
        return True
    # Check if user is in the room's allowed users (future feature)
    return False

# Pydantic models for validation
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(default="", max_length=500)
    is_private: bool = Field(default=False)

class EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

@app.get("/")
async def get():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>\u26A0\uFE0F index.html not found</h1>", status_code=500)

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Server is running",
        "online_users": manager.get_online_count(),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    username = request.username.strip()
    password = request.password
    
    # Rate limiting
    if not check_rate_limit(f"register_{username}"):
        return JSONResponse({"success": False, "error": "Too many requests. Try again later."}, status_code=429)
    
    if len(username) < 3:
        return JSONResponse({"success": False, "error": "Username must be at least 3 characters"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"success": False, "error": "Password must be at least 6 characters"}, status_code=400)

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return JSONResponse({"success": False, "error": "Username already exists"}, status_code=400)

    is_first_user = db.query(User).count() == 0
    
    # Generate salt and hash password
    salt = generate_salt()
    password_hash = hash_password(password, salt)
    
    user = User(username=username, password_hash=password_hash, salt=salt, is_admin=is_first_user)
    db.add(user)
    db.commit()
    db.refresh(user)

    personal_room = Room(name=f"private_{username}", description=f"Private room for {username}", is_private=True, created_by=user.id)
    db.add(personal_room)
    db.commit()

    if not db.query(Room).filter(Room.name == "general").first():
        general_room = Room(name="general", description="General chat", created_by=user.id)
        db.add(general_room)
        db.commit()

    logger.info(f"\u2705 User registered: {username} (admin: {is_first_user})")
    return {"success": True, "username": username, "is_admin": is_first_user, "user_id": user.id}

@app.post("/api/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    username = request.username.strip()
    password = request.password
    
    # Rate limiting
    if not check_rate_limit(f"login_{username}"):
        return JSONResponse({"success": False, "error": "Too many login attempts. Try again later."}, status_code=429)
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return JSONResponse({"success": False, "error": "Invalid credentials"}, status_code=401)
    if user.is_banned:
        return JSONResponse({"success": False, "error": "You are banned"}, status_code=403)
    if not verify_password(password, user.password_hash, user.salt):
        return JSONResponse({"success": False, "error": "Invalid credentials"}, status_code=401)
    logger.info(f"\u2705 User logged in: {username}")
    return {"success": True, "username": username, "user_id": user.id, "is_admin": user.is_admin}

@app.get("/api/rooms")
async def get_rooms(username: str = Query(None), db: Session = Depends(get_db)):
    rooms = db.query(Room).all()
    result = []
    for r in rooms:
        # Check access for private rooms
        if r.is_private and username:
            user = db.query(User).filter(User.username == username).first()
            if user and r.created_by != user.id:
                continue  # Skip private rooms user doesn't own
        result.append({
            "id": r.id, 
            "name": r.name, 
            "description": r.description, 
            "is_private": r.is_private, 
            "created_by": r.created_by
        })
    return result

@app.post("/api/rooms")
async def create_room(request: CreateRoomRequest, username: str = Form(None), db: Session = Depends(get_db)):
    name = request.name.strip()
    description = request.description.strip()
    is_private = request.is_private
    
    if len(name) < 3:
        return JSONResponse({"success": False, "error": "Room name must be at least 3 characters"}, status_code=400)
    existing = db.query(Room).filter(Room.name == name).first()
    if existing:
        return JSONResponse({"success": False, "error": "Room already exists"}, status_code=400)
    user = db.query(User).filter(User.username == username).first()
    room = Room(name=name, description=description, is_private=is_private, created_by=user.id if user else None)
    db.add(room)
    db.commit()
    logger.info(f"\uD83D\uDCCE Room created: {name} (private: {is_private})")
    return {"success": True, "room_id": room.id, "name": name}

@app.get("/api/messages/{room_id}")
async def get_messages(room_id: int, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        Message.room_id == room_id, 
        Message.is_deleted == False
    ).order_by(Message.created_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for msg in reversed(messages):
        result.append({
            "id": msg.id, 
            "content": msg.content, 
            "username": msg.user.username if msg.user else "Unknown",
            "user_id": msg.user_id, 
            "created_at": msg.created_at.isoformat(),
            "is_edited": msg.is_edited
        })
    return result

@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return JSONResponse({"success": False, "error": "Room not found"}, status_code=404)
    if room.name == "general":
        return JSONResponse({"success": False, "error": "Cannot delete general room"}, status_code=403)
    db.delete(room)
    db.commit()
    await manager.broadcast_to_room(room_id, {"type": "system", "content": f"Room #{room.name} has been deleted"})
    logger.info(f"\uD83D\uDDD1\uFE0F Room {room.name} deleted")
    return {"success": True}

@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        return JSONResponse({"success": False, "error": "Message not found"}, status_code=404)
    
    # Allow user to delete own message or admin to delete any
    if message.user_id != user.id and not user.is_admin:
        return JSONResponse({"success": False, "error": "You can only delete your own messages"}, status_code=403)
    
    message.is_deleted = True
    message.content = "[Message deleted]"
    db.commit()
    await manager.broadcast_to_room(message.room_id, {"type": "system", "content": f"Message was deleted"})
    return {"success": True}

@app.put("/api/messages/{message_id}")
async def edit_message(message_id: int, request: EditMessageRequest, username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        return JSONResponse({"success": False, "error": "Message not found"}, status_code=404)
    
    # Allow user to edit own message or admin to edit any
    if message.user_id != user.id and not user.is_admin:
        return JSONResponse({"success": False, "error": "You can only edit your own messages"}, status_code=403)
    
    message.content = request.content.strip()
    message.is_edited = True
    db.commit()
    await manager.broadcast_to_room(message.room_id, {
        "type": "message_edited",
        "message_id": message.id,
        "content": message.content,
        "edited_by": username
    })
    return {"success": True, "content": message.content, "is_edited": True}

@app.get("/api/admin/users")
async def get_all_users(username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    users = db.query(User).all()
    return [{
        "id": u.id, "username": u.username, "is_admin": u.is_admin, "is_banned": u.is_banned,
        "created_at": u.created_at.isoformat(), "is_online": u.username in manager.get_online_users()
    } for u in users]

@app.post("/api/admin/ban/{user_id}")
async def ban_user(user_id: int, username: str, db: Session = Depends(get_db)):
    current_user = get_current_user(username, db)
    check_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)
    if user.is_admin:
        return JSONResponse({"success": False, "error": "Cannot ban admin"}, status_code=403)
    user.is_banned = True
    db.commit()
    await manager.kick_user(user.username)
    logger.info(f"\uD83D\uDEAB {user.username} banned")
    return {"success": True}

@app.post("/api/admin/unban/{user_id}")
async def unban_user(user_id: int, username: str, db: Session = Depends(get_db)):
    current_user = get_current_user(username, db)
    check_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)
    user.is_banned = False
    db.commit()
    logger.info(f"\u2705 {user.username} unbanned")
    return {"success": True}

@app.post("/api/admin/make-admin/{user_id}")
async def make_admin(user_id: int, username: str, db: Session = Depends(get_db)):
    current_user = get_current_user(username, db)
    check_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)
    user.is_admin = True
    db.commit()
    logger.info(f"\uD83D\uDC51 {user.username} made admin")
    return {"success": True}

@app.get("/api/admin/online")
async def get_online_users(username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    return {"online": manager.get_online_users(), "count": manager.get_online_count()}

@app.get("/api/admin/stats")
async def get_stats(username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    return {
        "total_users": db.query(User).count(),
        "total_rooms": db.query(Room).count(),
        "total_messages": db.query(Message).count(),
        "online_users": manager.get_online_count(),
        "banned_users": db.query(User).filter(User.is_banned == True).count()
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("\uD83D\uDC4C WebSocket connected")

    current_room = None
    current_username = None
    current_user_id = None

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")


            if action == "join_room":
                room_id = data.get("room_id")
                current_username = data.get("username")
                current_user_id = data.get("user_id")

                db = SessionLocal()
                user = db.query(User).filter(User.username == current_username).first()
                if user and user.is_banned:
                    await websocket.send_json({"type": "kicked", "content": "You are banned"})
                    await websocket.close()
                    db.close()
                    return
                
                # Check private room access
                room = db.query(Room).filter(Room.id == room_id).first()
                if room and room.is_private and room.created_by != user.id:
                    await websocket.send_json({"type": "kicked", "content": "Access denied to private room"})
                    await websocket.close()
                    db.close()
                    return
                
                db.close()

                if current_room:
                    manager.disconnect(websocket, current_room, current_username)

                current_room = room_id
                await manager.connect(websocket, room_id, current_username, current_user_id)
                await manager.broadcast_to_room(room_id, {"type": "system", "content": f"{current_username} joined the chat"})

            elif action == "message":
                if current_room and current_username:
                    content = data.get("content")
                    if not content or len(content.strip()) == 0:
                        continue
                    db = SessionLocal()
                    user = db.query(User).filter(User.username == current_username).first()
                    if user and not user.is_banned:
                        message = Message(content=content, user_id=user.id, room_id=current_room)
                        db.add(message)
                        db.commit()
                        db.close()
                        await manager.broadcast_to_room(current_room, {
                            "type": "message", 
                            "content": content, 
                            "username": current_username,
                            "user_id": current_user_id, 
                            "created_at": datetime.utcnow().isoformat(),
                            "is_edited": False
                        })
                    else:
                        db.close()
                        await websocket.send_json({"type": "kicked", "content": "You are banned"})
                        await websocket.close()
                        return

            elif action == "leave_room":
                if current_room:
                    await manager.broadcast_to_room(current_room, {"type": "system", "content": f"{current_username} left the chat"})
                    manager.disconnect(websocket, current_room, current_username)
                    current_room = None

    except WebSocketDisconnect:
        logger.info("\uD83D\uDC4C WebSocket disconnected")
        if current_room and current_username:
            await manager.broadcast_to_room(current_room, {"type": "system", "content": f"{current_username} disconnected"})
            manager.disconnect(websocket, current_room, current_username)
    except Exception as e:
        logger.error(f"\u26A0\uFE0F WebSocket error: {e}")
        if current_room and current_username:
            manager.disconnect(websocket, current_room, current_username)

if __name__ == "__main__":
    print("\uD83D\uDCF0 Server running at http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
