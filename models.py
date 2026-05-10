from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import hashlib

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_online = Column(Boolean, default=False)
    
    # Game status fields
    current_game = Column(String, nullable=True)
    game_details = Column(String, nullable=True)
    is_playing = Column(Boolean, default=False)
    
    # Theme preference
    theme = Column(String, default="light")  # "light" or "dark"

    messages = relationship("Message", back_populates="user", foreign_keys="[Message.user_id]", cascade="all, delete-orphan")
    sent_dms = relationship("DirectMessage", foreign_keys="DirectMessage.sender_id", back_populates="sender")
    received_dms = relationship("DirectMessage", foreign_keys="DirectMessage.receiver_id", back_populates="receiver")

class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    is_private = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


    messages = relationship("Message", back_populates="room", cascade="all, delete-orphan")
    creator = relationship("User")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)  # Может быть NULL для личных сообщений
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_deleted = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    
    # Статусы прочтения
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    
    # Цитирование и ответы
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    
    # Закрепленные сообщения
    is_pinned = Column(Boolean, default=False)
    pinned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    pinned_at = Column(DateTime, nullable=True)
    
    # Файлы
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)  # image, video, audio, document
    file_data = Column(LargeBinary, nullable=True)  # Для хранения файлов в БД (опционально)

    user = relationship("User", back_populates="messages", foreign_keys=[user_id])
    room = relationship("Room", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id], backref="replies")
    pinned_by_user = relationship("User", foreign_keys=[pinned_by])


class DirectMessage(Base):
    __tablename__ = "direct_messages"


    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    
    # Файлы в личных сообщениях
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    file_data = Column(LargeBinary, nullable=True)
    
    # Цитирование
    reply_to_id = Column(Integer, ForeignKey("direct_messages.id"), nullable=True)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_dms")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_dms")
    reply_to = relationship("DirectMessage", remote_side=[id], backref="replies")


def generate_salt() -> str:
    """Generate random salt for password hashing"""
    import secrets
    return secrets.token_hex(16)

def hash_password(password: str, salt: str) -> str:
    """Hash password with salt"""
    return hashlib.sha256((password + salt).encode()).hexdigest()

def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify password against hash"""
    return hash_password(password, salt) == hashed
