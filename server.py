#!/usr/bin/env python3
"""
Mesange Messenger Server
FastAPI backend with WebSocket, Admin Panel, Game Status & Overlay Support
"""
import asyncio
import json
import psutil
import platform
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, joinedload
from database import Base, get_db, engine
from models import User, Room, Message, DirectMessage, hash_password, verify_password, generate_salt
import jwt
import secrets

# Конфигурация
SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 дней

app = FastAPI(title="Mesange Messenger API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

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

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    is_admin: bool

class MessageCreate(BaseModel):
    content: str
    room_id: Optional[int] = None
    receiver_id: Optional[int] = None

class GameStatusUpdate(BaseModel):
    game_name: Optional[str] = None
    is_playing: bool
    details: Optional[str] = None

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

# Утилиты
def create_access_token(data: dict, expires_delta: Optional[int] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=(expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.is_banned:
        raise HTTPException(status_code=401, detail="User not found or banned")
    return user

def require_admin(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Auth endpoints
@app.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    salt = generate_salt()
    password_hash = hash_password(request.password, salt)
    
    # Первый пользователь становится админом
    is_first_user = db.query(User).count() == 0
    user = User(
        username=request.username,
        password_hash=password_hash,
        salt=salt,
        is_admin=is_first_user
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_access_token({"sub": user.id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin
    )

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash, user.salt):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account is banned")
    
    user.is_online = True
    user.last_seen = datetime.utcnow()
    db.commit()
    
    token = create_access_token({"sub": user.id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin
    )

# User endpoints
@app.get("/users/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat(),
        "last_seen": user.last_seen.isoformat(),
        "is_online": user.is_online,
        "status": user_status.get(user.id, {})
    }

@app.get("/users")
async def get_all_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "username": u.username,
        "is_admin": u.is_admin,
        "is_banned": u.is_banned,
        "created_at": u.created_at.isoformat(),
        "last_seen": u.last_seen.isoformat(),
        "is_online": u.id in connected_users,
        "status": user_status.get(u.id, {})
    } for u in users]

@app.post("/users/{user_id}/ban")
async def ban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot ban admin")
    
    user.is_banned = True
    user.is_online = False
    
    # Disconnect WebSocket
    if user_id in connected_users:
        await connected_users[user_id].close(code=4003, reason="Banned")
        del connected_users[user_id]
    
    db.commit()
    return {"message": f"User {user.username} banned"}

@app.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = False
    db.commit()
    return {"message": f"User {user.username} unbanned"}

@app.post("/users/{user_id}/toggle-admin")
async def toggle_admin(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    room = Room(name=name, description=description, created_by=user.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "name": room.name, "description": room.description}

@app.delete("/rooms/{room_id}")
async def delete_room(room_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
async def get_dms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
async def delete_message(message_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message.is_deleted = True
    message.content = "[Сообщение удалено модератором]"
    db.commit()
    
    # Уведомить подключенных пользователей в комнате
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
async def get_server_stats(admin: User = Depends(require_admin)):
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    
    return ServerStats(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=psutil.virtual_memory().percent,
        memory_total=psutil.virtual_memory().total,
        memory_available=psutil.virtual_memory().available,
        disk_percent=psutil.disk_usage('/').percent,
        uptime=uptime,
        active_users=len(connected_users),
        total_users=engine.execute(text("SELECT COUNT(*) FROM users")).scalar(),
        total_rooms=engine.execute(text("SELECT COUNT(*) FROM rooms")).scalar(),
        total_messages=engine.execute(text("SELECT COUNT(*) FROM messages")).scalar(),
        platform=f"{platform.system()} {platform.release()}",
        python_version=platform.python_version()
    )

# Game status endpoint
@app.post("/user/status/game")
async def update_game_status(game_status: GameStatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_status = user_status.get(user.id, {})
    
    if game_status.is_playing and game_status.game_name:
        current_status["game"] = game_status.game_name
        current_status["is_playing"] = True
        current_status["details"] = game_status.details
        current_status["started_at"] = datetime.utcnow().isoformat()
    else:
        current_status["game"] = None
        current_status["is_playing"] = False
        current_status["details"] = None
    
    user_status[user.id] = current_status
    user.last_seen = datetime.utcnow()
    db.commit()
    
    # Broadcast status update
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
        "type": "user_status_update",
        "user_id": user_id,
        "status": status_data
    }
    await broadcast_to_room(None, data)  # Отправить всем

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    user_id = None
    
    try:
        # Ждем авторизацию
        auth_data = await websocket.receive_text()
        auth = json.loads(auth_data)
        
        if auth.get("type") != "auth":
            await websocket.close(code=4001, reason="Expected auth first")
            return
        
        token = auth.get("token")
        if not token:
            await websocket.close(code=4002, reason="No token")
            return
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except:
            await websocket.close(code=4002, reason="Invalid token")
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
        
        # Отправляем подтверждение
        await websocket.send_text(json.dumps({
            "type": "auth_success",
            "user_id": user_id,
            "username": user.username,
            "is_admin": user.is_admin
        }))
        
        # Отправляем текущие статусы всех пользователей
        await websocket.send_text(json.dumps({
            "type": "all_statuses",
            "statuses": user_status
        }))
        
        # Основной цикл
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                action = message.get("action")
                
                if action == "join_room":
                    room_id = message.get("room_id")
                    if room_id:
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
                            user_id=user_id,
                            room_id=room_id
                        )
                        db.add(msg)
                        db.commit()
                        db.refresh(msg)
                        
                        await broadcast_to_room(room_id, {
                            "type": "new_message",
                            "message": {
                                "id": msg.id,
                                "content": msg.content,
                                "user_id": user_id,
                                "username": user.username,
                                "room_id": room_id,
                                "created_at": msg.created_at.isoformat()
                            }
                        })
                
                elif action == "send_dm":
                    content = message.get("content")
                    receiver_id = message.get("receiver_id")
                    
                    if receiver_id and content:
                        dm = DirectMessage(
                            sender_id=user_id,
                            receiver_id=receiver_id,
                            content=content
                        )
                        db.add(dm)
                        db.commit()
                        
                        # Отправить получателю если онлайн
                        if receiver_id in connected_users:
                            await connected_users[receiver_id].send_text(json.dumps({
                                "type": "new_dm",
                                "message": {
                                    "id": dm.id,
                                    "sender_id": user_id,
                                    "sender_username": user.username,
                                    "content": content,
                                    "created_at": dm.created_at.isoformat()
                                }
                            }))
                
                elif action == "typing":
                    room_id = message.get("room_id")
                    is_typing = message.get("is_typing", False)
                    if room_id:
                        await broadcast_to_room(room_id, {
                            "type": "user_typing",
                            "user_id": user_id,
                            "username": user.username,
                            "is_typing": is_typing
                        })
                        
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        pass
    finally:
        if user_id:
            if user_id in connected_users:
                del connected_users[user_id]
            
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_online = False
                db.commit()
            
            if user_id in admin_connections:
                admin_connections.discard(user_id)
            
            # Очистить статус игры
            if user_id in user_status:
                user_status[user_id]["is_playing"] = False
                await broadcast_user_status(user_id, user_status[user_id])

# Admin panel HTML
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mesange Admin Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            background: rgba(255,255,255,0.05);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color: #4ecca3; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.08);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            transition: transform 0.3s;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-value { font-size: 2em; font-weight: bold; color: #4ecca3; }
        .stat-label { opacity: 0.7; margin-top: 5px; }
        .panel {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .panel h2 { color: #4ecca3; margin-bottom: 15px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { background: rgba(78, 204, 163, 0.2); color: #4ecca3; }
        tr:hover { background: rgba(255,255,255,0.05); }
        .btn {
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 2px;
            transition: all 0.3s;
        }
        .btn-ban { background: #e74c3c; color: white; }
        .btn-unban { background: #27ae60; color: white; }
        .btn-admin { background: #3498db; color: white; }
        .btn-delete { background: #e67e22; color: white; }
        .btn:hover { opacity: 0.8; transform: scale(1.05); }
        .status-online { color: #27ae60; }
        .status-offline { color: #7f8c8d; }
        .game-playing { 
            background: rgba(231, 76, 60, 0.2);
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.9em;
        }
        .progress-bar {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin-top: 5px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4ecca3, #45b393);
            transition: width 0.5s;
        }
        .refresh-btn {
            background: #4ecca3;
            color: #1a1a2e;
            padding: 10px 20px;
            font-weight: bold;
        }
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.7);
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: #16213e;
            padding: 30px;
            border-radius: 10px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .close-modal { float: right; font-size: 1.5em; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🛡️ Mesange Admin Panel</h1>
            <button class="btn refresh-btn" onclick="loadData()">🔄 Обновить</button>
        </header>

        <div class="stats-grid" id="statsGrid">
            <div class="stat-card">
                <div class="stat-value" id="cpuStat">-</div>
                <div class="stat-label">CPU Load</div>
                <div class="progress-bar"><div class="progress-fill" id="cpuBar" style="width: 0%"></div></div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="memStat">-</div>
                <div class="stat-label">Memory</div>
                <div class="progress-bar"><div class="progress-fill" id="memBar" style="width: 0%"></div></div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="diskStat">-</div>
                <div class="stat-label">Disk</div>
                <div class="progress-bar"><div class="progress-fill" id="diskBar" style="width: 0%"></div></div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="uptimeStat">-</div>
                <div class="stat-label">Uptime</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="usersStat">-</div>
                <div class="stat-label">Active Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="messagesStat">-</div>
                <div class="stat-label">Total Messages</div>
            </div>
        </div>

        <div class="panel">
            <h2>👥 Пользователи</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Статус</th>
                        <th>Игра</th>
                        <th>Роль</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="usersTable"></tbody>
            </table>
        </div>

        <div class="panel">
            <h2>💬 Последние сообщения</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Пользователь</th>
                        <th>Сообщение</th>
                        <th>Время</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="messagesTable"></tbody>
            </table>
        </div>

        <div class="panel">
            <h2>🏠 Комнаты</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Название</th>
                        <th>Создатель</th>
                        <th>Сообщений</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="roomsTable"></tbody>
            </table>
        </div>
    </div>

    <div id="messageModal" class="modal">
        <div class="modal-content">
            <span class="close-modal" onclick="closeModal()">&times;</span>
            <h2>Просмотр сообщения</h2>
            <pre id="messageContent" style="background: rgba(0,0,0,0.3); padding: 15px; border-radius: 5px; margin-top: 15px;"></pre>
        </div>
    </div>

    <script>
        const API_URL = window.location.origin;
        let token = localStorage.getItem('admin_token');

        async function checkAuth() {
            if (!token) {
                token = prompt('Введите ваш токен администратора:');
                if (token) localStorage.setItem('admin_token', token);
            }
            try {
                const res = await fetch(`${API_URL}/users/me`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error();
                const user = await res.json();
                if (!user.is_admin) {
                    alert('Требуется права администратора!');
                    localStorage.removeItem('admin_token');
                    location.reload();
                }
            } catch {
                localStorage.removeItem('admin_token');
                location.reload();
            }
        }

        async function loadData() {
            await loadStats();
            await loadUsers();
            await loadMessages();
            await loadRooms();
        }

        async function loadStats() {
            try {
                const res = await fetch(`${API_URL}/admin/stats`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const stats = await res.json();
                
                document.getElementById('cpuStat').textContent = stats.cpu_percent.toFixed(1) + '%';
                document.getElementById('cpuBar').style.width = stats.cpu_percent + '%';
                
                document.getElementById('memStat').textContent = stats.memory_percent.toFixed(1) + '%';
                document.getElementById('memBar').style.width = stats.memory_percent + '%';
                
                document.getElementById('diskStat').textContent = stats.disk_percent.toFixed(1) + '%';
                document.getElementById('diskBar').style.width = stats.disk_percent + '%';
                
                const hours = Math.floor(stats.uptime / 3600);
                const mins = Math.floor((stats.uptime % 3600) / 60);
                document.getElementById('uptimeStat').textContent = `${hours}ч ${mins}м`;
                
                document.getElementById('usersStat').textContent = `${stats.active_users}/${stats.total_users}`;
                document.getElementById('messagesStat').textContent = stats.total_messages;
            } catch (e) { console.error('Stats error:', e); }
        }

        async function loadUsers() {
            try {
                const res = await fetch(`${API_URL}/users`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const users = await res.json();
                
                const tbody = document.getElementById('usersTable');
                tbody.innerHTML = users.map(u => `
                    <tr>
                        <td>${u.id}</td>
                        <td>${u.username}</td>
                        <td class="${u.is_online ? 'status-online' : 'status-offline'}">
                            ${u.is_online ? '🟢 Онлайн' : '⚫ Офлайн'}
                        </td>
                        <td>${u.status?.is_playing ? 
                            `<span class="game-playing">🎮 ${u.status.game || 'Unknown'}</span>` : 
                            '-'}</td>
                        <td>${u.is_admin ? '👑 Админ' : '👤 Пользователь'} ${u.is_banned ? '🚫 Забанен' : ''}</td>
                        <td>
                            ${!u.is_admin ? `
                                <button class="btn ${u.is_banned ? 'btn-unban' : 'btn-ban'}" 
                                    onclick="toggleBan(${u.id}, ${u.is_banned})">
                                    ${u.is_banned ? 'Разбанить' : 'Забанить'}
                                </button>
                            ` : ''}
                            <button class="btn btn-admin" onclick="toggleAdmin(${u.id})">
                                ${u.is_admin ? 'Снять админа' : 'Сделать админом'}
                            </button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) { console.error('Users error:', e); }
        }

        async function loadMessages() {
            try {
                const res = await fetch(`${API_URL}/rooms/1/messages?limit=20`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) return;
                const messages = await res.json();
                
                const tbody = document.getElementById('messagesTable');
                tbody.innerHTML = messages.map(m => `
                    <tr>
                        <td>${m.id}</td>
                        <td>${m.username}</td>
                        <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">
                            ${m.content.substring(0, 50)}${m.content.length > 50 ? '...' : ''}
                        </td>
                        <td>${new Date(m.created_at).toLocaleString()}</td>
                        <td>
                            <button class="btn" onclick="viewMessage(${m.id})">👁️</button>
                            <button class="btn btn-delete" onclick="deleteMessage(${m.id})">🗑️</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) { console.error('Messages error:', e); }
        }

        async function loadRooms() {
            try {
                const res = await fetch(`${API_URL}/rooms`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const rooms = await res.json();
                
                const tbody = document.getElementById('roomsTable');
                tbody.innerHTML = rooms.map(r => `
                    <tr>
                        <td>${r.id}</td>
                        <td>${r.name}</td>
                        <td>${r.created_by || '-'}</td>
                        <td>${r.message_count}</td>
                        <td>
                            <button class="btn btn-delete" onclick="deleteRoom(${r.id})">🗑️</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) { console.error('Rooms error:', e); }
        }

        async function toggleBan(userId, isBanned) {
            const endpoint = isBanned ? 'unban' : 'ban';
            await fetch(`${API_URL}/users/${userId}/${endpoint}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            loadData();
        }

        async function toggleAdmin(userId) {
            await fetch(`${API_URL}/users/${userId}/toggle-admin`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            loadData();
        }

        async function deleteMessage(msgId) {
            if (!confirm('Удалить это сообщение?')) return;
            await fetch(`${API_URL}/messages/delete/${msgId}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            loadMessages();
        }

        async function deleteRoom(roomId) {
            if (!confirm('Удалить эту комнату?')) return;
            await fetch(`${API_URL}/rooms/${roomId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            loadRooms();
        }

        function viewMessage(msgId) {
            // Загрузка полного текста сообщения
            document.getElementById('messageModal').style.display = 'flex';
            document.getElementById('messageContent').textContent = 'Загрузка...';
        }

        function closeModal() {
            document.getElementById('messageModal').style.display = 'none';
        }

        // Auto-refresh каждые 5 секунд
        setInterval(loadData, 5000);

        // Init
        checkAuth();
        loadData();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск Mesange Server v2.0...")
    print("📊 Admin Panel: http://localhost:8000/admin")
    print("🔌 WebSocket: ws://localhost:8000/ws")
    print("📚 API Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
