from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from database import engine, get_db, SessionLocal, init_db
from models import Base, User, Room, Message, hash_password, verify_password
from sqlalchemy.orm import Session
from datetime import datetime
import uvicorn
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("📦 Инициализация базы данных...")
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
    print("❌ ОШИБКА: Файл index.html не найден!")
else:
    print("✅ Файл index.html найден.")

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.online_users = {}

    async def connect(self, websocket, room_id, username, user_id):
        # ⚠️ НЕТ websocket.accept() - вызывается ТОЛЬКО в endpoint!
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
        logger.info(f"✅ {username} подключился к комнате {room_id}")

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
        logger.info(f"❌ {username} отключился")

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
                    "content": "Вы были заблокированы администратором"
                })
                await self.online_users[username]["websocket"].close()
            except:
                pass
            del self.online_users[username]
            logger.info(f"🚫 {username} был кикнут")

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
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    return user

def check_admin(user: User):
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Требуется права администратора")

@app.get("/")
async def get():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>❌ index.html не найден!</h1>", status_code=500)

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Сервер работает",
        "online_users": manager.get_online_count(),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/register")
async def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if len(username) < 3:
        return JSONResponse({"success": False, "error": "Имя слишком короткое (минимум 3 символа)"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"success": False, "error": "Пароль слишком короткий (минимум 6 символов)"}, status_code=400)

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return JSONResponse({"success": False, "error": "Пользователь уже существует"}, status_code=400)

    is_first_user = db.query(User).count() == 0

    user = User(username=username, password_hash=hash_password(password), is_admin=is_first_user)
    db.add(user)
    db.commit()
    db.refresh(user)

    personal_room = Room(name=f"private_{username}", description=f"Личный чат {username}", is_private=True, created_by=user.id)
    db.add(personal_room)
    db.commit()

    if not db.query(Room).filter(Room.name == "general").first():
        general_room = Room(name="general", description="Общий чат", created_by=user.id)
        db.add(general_room)
        db.commit()

    logger.info(f"✅ Зарегистрирован: {username} (Админ: {is_first_user})")
    return {"success": True, "username": username, "is_admin": is_first_user, "user_id": user.id}

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return JSONResponse({"success": False, "error": "Пользователь не найден"}, status_code=401)
    if user.is_banned:
        return JSONResponse({"success": False, "error": "Аккаунт заблокирован"}, status_code=403)
    if not verify_password(password, user.password_hash):
        return JSONResponse({"success": False, "error": "Неверный пароль"}, status_code=401)
    logger.info(f"✅ Вход: {username}")
    return {"success": True, "username": username, "user_id": user.id, "is_admin": user.is_admin}

@app.get("/api/rooms")
async def get_rooms(db: Session = Depends(get_db)):
    rooms = db.query(Room).all()
    return [{"id": r.id, "name": r.name, "description": r.description, "is_private": r.is_private, "created_by": r.created_by} for r in rooms]

@app.post("/api/rooms")
async def create_room(name: str = Form(...), description: str = Form(""), username: str = Form(None), db: Session = Depends(get_db)):
    if len(name) < 3:
        return JSONResponse({"success": False, "error": "Название слишком короткое"}, status_code=400)
    existing = db.query(Room).filter(Room.name == name).first()
    if existing:
        return JSONResponse({"success": False, "error": "Комната уже существует"}, status_code=400)
    user = db.query(User).filter(User.username == username).first()
    room = Room(name=name, description=description, created_by=user.id if user else None)
    db.add(room)
    db.commit()
    logger.info(f"🏠 Создана комната: {name}")
    return {"success": True, "room_id": room.id, "name": name}

@app.get("/api/messages/{room_id}")
async def get_messages(room_id: int, limit: int = 50, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(Message.room_id == room_id, Message.is_deleted == False).order_by(Message.created_at.desc()).limit(limit).all()
    result = []
    for msg in reversed(messages):
        result.append({
            "id": msg.id, "content": msg.content, "username": msg.user.username if msg.user else "Unknown",
            "user_id": msg.user_id, "created_at": msg.created_at.isoformat()
        })
    return result

@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return JSONResponse({"success": False, "error": "Комната не найдена"}, status_code=404)
    if room.name == "general":
        return JSONResponse({"success": False, "error": "Нельзя удалить общую комнату"}, status_code=403)
    db.delete(room)
    db.commit()
    await manager.broadcast_to_room(room_id, {"type": "system", "content": f"Комната #{room.name} была удалена администратором"})
    logger.info(f"🗑️ Комната {room.name} удалена")
    return {"success": True}

@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        return JSONResponse({"success": False, "error": "Сообщение не найдено"}, status_code=404)
    message.is_deleted = True
    message.content = "[Сообщение удалено администратором]"
    db.commit()
    await manager.broadcast_to_room(message.room_id, {"type": "system", "content": f"Сообщение от {message.user.username} было удалено"})
    return {"success": True}

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
        return JSONResponse({"success": False, "error": "Пользователь не найден"}, status_code=404)
    if user.is_admin:
        return JSONResponse({"success": False, "error": "Нельзя забанить администратора"}, status_code=403)
    user.is_banned = True
    db.commit()
    await manager.kick_user(user.username)
    logger.info(f"🚫 {user.username} забанен")
    return {"success": True}

@app.post("/api/admin/unban/{user_id}")
async def unban_user(user_id: int, username: str, db: Session = Depends(get_db)):
    current_user = get_current_user(username, db)
    check_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"success": False, "error": "Пользователь не найден"}, status_code=404)
    user.is_banned = False
    db.commit()
    logger.info(f"✅ {user.username} разбанен")
    return {"success": True}

@app.post("/api/admin/make-admin/{user_id}")
async def make_admin(user_id: int, username: str, db: Session = Depends(get_db)):
    current_user = get_current_user(username, db)
    check_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"success": False, "error": "Пользователь не найден"}, status_code=404)
    user.is_admin = True
    db.commit()
    logger.info(f"👑 {user.username} стал админом")
    return {"success": True}

@app.get("/api/admin/online")
async def get_online_users(username: str, db: Session = Depends(get_db)):
    user = get_current_user(username, db)
    check_admin(user)
    return {"online": manager.get_online_users(), "count": manager.get_online_count()}

# ✅ ДОБАВЛЕН ОТСУТСТВУЮЩИЙ ENDPOINT
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
    # ✅ ПРИНИМАЕМ СОЕДИНЕНИЕ ТОЛЬКО ЗДЕСЬ (ОДИН РАЗ!)
    await websocket.accept()
    logger.info("🔌 WebSocket подключен")

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
                    await websocket.send_json({"type": "kicked", "content": "Ваш аккаунт заблокирован"})
                    await websocket.close()
                    db.close()
                    return
                db.close()

                if current_room:
                    manager.disconnect(websocket, current_room, current_username)

                current_room = room_id
                # ✅ НЕТ websocket.accept() в manager.connect()!
                await manager.connect(websocket, room_id, current_username, current_user_id)
                await manager.broadcast_to_room(room_id, {"type": "system", "content": f"{current_username} присоединился к чату"})

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
                            "type": "message", "content": content, "username": current_username,
                            "user_id": current_user_id, "created_at": datetime.utcnow().isoformat()
                        })
                    else:
                        db.close()
                        await websocket.send_json({"type": "kicked", "content": "Ваш аккаунт заблокирован"})
                        await websocket.close()
                        return

            elif action == "leave_room":
                if current_room:
                    await manager.broadcast_to_room(current_room, {"type": "system", "content": f"{current_username} покинул чат"})
                    manager.disconnect(websocket, current_room, current_username)
                    current_room = None

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket отключен")
        if current_room and current_username:
            await manager.broadcast_to_room(current_room, {"type": "system", "content": f"{current_username} отключился"})
            manager.disconnect(websocket, current_room, current_username)
    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        if current_room and current_username:
            manager.disconnect(websocket, current_room, current_username)

if __name__ == "__main__":
    print("🚀 Запуск сервера на http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)