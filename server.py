#!/usr/bin/env python3
"""
Mesange Messenger Server - Без токенов, упрощённая авторизация
FastAPI backend with WebSocket, Admin Panel, Game Status & Overlay Support
"""
import asyncio
import json
import psutil
import platform
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, joinedload
from database import Base, get_db, engine, init_db
from models import User, Room, Message, DirectMessage, hash_password, verify_password, generate_salt
import secrets

# Конфигурация
SECRET_KEY = secrets.token_hex(32)
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 дней

app = FastAPI(title="Mesange Messenger API", version="2.0.0")

# Инициализация БД при старте
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные состояния
connected_users: Dict[int, WebSocket] = {}
user_status: Dict[int, Dict[str, Any]] = {}  # user_id -> {game, status, last_seen}
admin_connections: set = set()

# Pydantic модели
class AuthRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    user_id: int
    username: str
    is_admin: bool
    message: str

class MessageCreate(BaseModel):
    content: str
    room_id: Optional[int] = None
    receiver_id: Optional[int] = None

class GameStatusUpdate(BaseModel):
    game_name: Optional[str] = None
    is_playing: bool = False
    details: Optional[str] = None
    confidence: Optional[int] = 100
    method: Optional[str] = "manual"

class ServerStats(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_total: int
    memory_available: int
    disk_percent: float
    uptime: float
    active_users: int
    total_users: int
    total_rooms: int
    total_messages: int
    platform: str
    python_version: str

# Утилиты для упрощённой авторизации
def get_current_user_from_header(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Получает пользователя из заголовка X-User-ID"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return None
    try:
        user_id = int(user_id)
    except ValueError:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.is_banned:
        return None
    return user

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Требует авторизацию"""
    user = get_current_user_from_header(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authorization required")
    return user

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Требует права администратора"""
    user = get_current_user_from_header(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authorization required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Главная страница
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mesange Messenger</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }
        h1 { color: #667eea; margin-bottom: 10px; }
        p { color: #666; margin-bottom: 30px; }
        a {
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 10px;
            transition: background 0.3s;
        }
        a:hover { background: #5568d3; }
        .links { margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🕊️ Mesange Messenger</h1>
        <p>Добро пожаловать в мессенджер нового поколения</p>
        <div class="links">
            <a href="/index.html">Войти в мессенджер</a>
            <a href="/admin">Админ-панель</a>
        </div>
    </div>
</body>
</html>
""")

# Маршрут для index.html - отдает основной интерфейс
@app.get("/index.html", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Маршрут для админ-панели
@app.get("/admin", response_class=HTMLResponse)
async def get_admin():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Auth endpoints
@app.post("/api/register", response_model=LoginResponse)
async def register(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    salt = generate_salt()
    password_hash = hash_password(password, salt)
    
    is_first_user = db.query(User).count() == 0
    user = User(
        username=username,
        password_hash=password_hash,
        salt=salt,
        is_admin=is_first_user
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return LoginResponse(
        success=True,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        message="Registration successful"
    )

@app.post("/api/login", response_model=LoginResponse)
async def login(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash, user.salt):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account is banned")
    
    user.is_online = True
    user.last_seen = datetime.now(timezone.utc)
    db.commit()
    
    return LoginResponse(
        success=True,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        message="Login successful"
    )

# User endpoints
@app.get("/users/me")
async def get_me(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat(),
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
        "is_online": user.is_online,
        "status": user_status.get(user.id, {})
    }

@app.get("/users")
async def get_all_users(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    users = db.query(User).all()
    return [{
        "id": u.id,
        "username": u.username,
        "is_admin": u.is_admin,
        "is_banned": u.is_banned,
        "created_at": u.created_at.isoformat(),
        "last_seen": u.last_seen.isoformat() if u.last_seen else None,
        "is_online": u.id in connected_users,
        "status": user_status.get(u.id, {})
    } for u in users]

@app.post("/users/{user_id}/ban")
async def ban_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot ban admin")
    
    user.is_banned = True
    user.is_online = False
    
    if user_id in connected_users:
        await connected_users[user_id].close(code=4003, reason="Banned")
        del connected_users[user_id]
    
    db.commit()
    return {"message": f"User {user.username} banned"}

@app.post("/users/{user_id}/unban")
async def unban_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = False
    db.commit()
    return {"message": f"User {user.username} unbanned"}

@app.post("/users/{user_id}/toggle-admin")
async def toggle_admin(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_admin = not user.is_admin
    db.commit()
    return {"message": f"User {user.username} admin status: {user.is_admin}"}

# Room endpoints
@app.get("/rooms")
async def get_rooms(db: Session = Depends(get_db)):
    rooms = db.query(Room).filter(Room.is_private == False).all()
    return [{
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "created_by": r.creator.username if r.creator else None,
        "created_at": r.created_at.isoformat(),
        "message_count": len(r.messages)
    } for r in rooms]

@app.post("/rooms")
async def create_room(name: str, description: Optional[str] = None, 
                      request: Request = None, db: Session = Depends(get_db)):
    user = require_user(request, db)
    room = Room(name=name, description=description, created_by=user.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "name": room.name, "description": room.description}

@app.delete("/rooms/{room_id}")
async def delete_room(room_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    db.delete(room)
    db.commit()
    return {"message": f"Room {room.name} deleted"}

# Message endpoints
@app.get("/rooms/{room_id}/messages")
async def get_room_messages(room_id: int, limit: int = 50, offset: int = 0,
                            db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        Message.room_id == room_id,
        Message.is_deleted == False
    ).order_by(Message.created_at.desc()).offset(offset).limit(limit).all()
    
    return [{
        "id": m.id,
        "content": m.content,
        "user_id": m.user_id,
        "username": m.user.username,
        "created_at": m.created_at.isoformat(),
        "is_edited": m.is_edited
    } for m in reversed(messages)]

@app.get("/dms")
async def get_dms(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    dms = db.query(DirectMessage).filter(
        ((DirectMessage.sender_id == user.id) | (DirectMessage.receiver_id == user.id)) &
        (DirectMessage.is_read == False)
    ).all()
    return [{
        "id": dm.id,
        "sender_id": dm.sender_id,
        "sender_username": dm.sender.username,
        "receiver_id": dm.receiver_id,
        "content": dm.content,
        "created_at": dm.created_at.isoformat()
    } for dm in dms]

@app.post("/messages/delete/{message_id}")
async def delete_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message.is_deleted = True
    message.content = "[Сообщение удалено модератором]"
    db.commit()
    
    if message.room_id:
        broadcast_data = {
            "type": "message_deleted",
            "message_id": message_id,
            "room_id": message.room_id
        }
        await broadcast_to_room(message.room_id, broadcast_data)
    
    return {"message": "Message deleted"}

# Server stats endpoint
@app.get("/admin/stats", response_model=ServerStats)
async def get_server_stats(request: Request):
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    
    db = next(get_db())
    try:
        total_users = db.query(User).count()
        total_rooms = db.query(Room).count()
        total_messages = db.query(Message).count()
    finally:
        db.close()
    
    return ServerStats(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=psutil.virtual_memory().percent,
        memory_total=psutil.virtual_memory().total,
        memory_available=psutil.virtual_memory().available,
        disk_percent=psutil.disk_usage('/').percent,
        uptime=uptime,
        active_users=len(connected_users),
        total_users=total_users,
        total_rooms=total_rooms,
        total_messages=total_messages,
        platform=f"{platform.system()} {platform.release()}",
        python_version=platform.python_version()
    )

# Game status endpoint
@app.post("/user/status/game")
async def update_game_status(game_status: GameStatusUpdate, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    current_status = user_status.get(user.id, {})
    
    now = datetime.now(timezone.utc)
    
    if game_status.is_playing and game_status.game_name:
        current_status["game"] = game_status.game_name
        current_status["is_playing"] = True
        current_status["details"] = game_status.details
        current_status["confidence"] = game_status.confidence
        current_status["method"] = game_status.method
        current_status["started_at"] = now.isoformat()
        print(f"🎮 User {user.username} started playing {game_status.game_name} ({game_status.method}, {game_status.confidence}%)")
    else:
        old_game = current_status.get("game")
        current_status["game"] = None
        current_status["is_playing"] = False
        current_status["details"] = None
        current_status["confidence"] = None
        current_status["method"] = None
        if old_game:
            print(f"❌ User {user.username} stopped playing {old_game}")
    
    user_status[user.id] = current_status
    user.last_seen = now
    db.commit()
    
    await broadcast_user_status(user.id, current_status)
    
    return current_status

@app.get("/users/status")
async def get_all_users_status():
    return user_status

# WebSocket управление
async def broadcast_to_room(room_id: int, data: dict):
    message = json.dumps(data)
    disconnected = []
    for uid, ws in connected_users.items():
        try:
            await ws.send_text(message)
        except:
            disconnected.append(uid)
    for uid in disconnected:
        del connected_users[uid]

async def broadcast_user_status(user_id: int, status_data: dict):
    data = {
        "type": "user_status",
        "user_id": user_id,
        "status": status_data
    }
    await broadcast_to_room(None, data)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    user_id = None
    
    try:
        auth_data = await websocket.receive_text()
        auth = json.loads(auth_data)
        
        if auth.get("type") != "auth":
            await websocket.close(code=4001, reason="Expected auth first")
            return
        
        user_id = auth.get("user_id")
        if not user_id:
            await websocket.close(code=4002, reason="No user_id")
            return
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_banned:
            await websocket.close(code=4003, reason="User not found or banned")
            return
        
        connected_users[user_id] = websocket
        user.is_online = True
        db.commit()
        
        if user.is_admin:
            admin_connections.add(user_id)
        
        await websocket.send_text(json.dumps({
            "type": "auth_success",
            "user_id": user_id,
            "username": user.username,
            "is_admin": user.is_admin
        }))
        
        await websocket.send_text(json.dumps({
            "type": "all_statuses",
            "statuses": user_status
        }))
        
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                action = message.get("action")
                
                if action == "join_room":
                    room_id = message.get("room_id")
                    await websocket.send_text(json.dumps({
                        "type": "room_joined",
                        "room_id": room_id
                    }))
                elif action == "send_message":
                    content = message.get("content")
                    room_id = message.get("room_id")
                    
                    if room_id and content:
                        msg = Message(
                            content=content,
                            room_id=room_id,
                            user_id=user_id
                        )
                        db.add(msg)
                        db.commit()
                        db.refresh(msg)
                        
                        broadcast_data = {
                            "type": "new_message",
                            "room_id": room_id,
                            "message": {
                                "id": msg.id,
                                "content": msg.content,
                                "user_id": user_id,
                                "username": user.username,
                                "created_at": msg.created_at.isoformat()
                            }
                        }
                        await broadcast_to_room(room_id, broadcast_data)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
    
    finally:
        if user_id and user_id in connected_users:
            del connected_users[user_id]
            if user_id in admin_connections:
                admin_connections.remove(user_id)
            
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_online = False
                user.last_seen = datetime.now(timezone.utc)
                db.commit()

# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск Mesange Server v2.0...")
    print("📊 Admin Panel: http://localhost:8000/admin")
    print("🔌 WebSocket: ws://localhost:8000/ws")
    print("📚 API Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
