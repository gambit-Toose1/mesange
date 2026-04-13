#!/usr/bin/env python3
"""
Mesange Desktop App with Game Overlay
Требуется: pip install PyQt6 pystray
"""
import sys
import os
import json
import threading
import time
import subprocess
import websocket
import requests
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from pystray import MenuItem as Item
import pystray

# Конфигурация
SERVER_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

# Игры для отслеживания
GAME_PROCESSES = {
    'Dota 2': {'icon': '🎮', 'color': '#e44c2c'},
    'Fortnite': {'icon': '🏝️', 'color': '#9c4dbc'},
    'War Thunder': {'icon': '✈️', 'color': '#f5a623'},
    'cs2': {'icon': '🔫', 'color': '#de9b35'},
    'GTAV': {'icon': '🚗', 'color': '#6cd300'},
    'Minecraft': {'icon': '⛏️', 'color': '#62b47a'},
    'League of Legends': {'icon': '⚔️', 'color': '#c89b3c'},
    'Valorant': {'icon': '🎯', 'color': '#ff4655'},
}

class MesangeDesktop(QApplication):
    def __init__(self):
        super().__init__(sys.argv)
        self.setApplicationName("Mesange")
        self.setApplicationVersion("1.0.0")
        
        self.username = None
        self.user_id = None
        self.is_admin = False
        self.current_room = None
        self.ws = None
        self.online_users = []
        self.current_game = None
        
        # Окна
        self.auth_window = None
        self.main_window = None
        self.overlay = None
        self.tray = None
        
        self.show_auth()

    def show_auth(self):
        self.auth_window = AuthWindow(self)
        self.auth_window.show()

    def show_main(self):
        self.auth_window.close()
        self.main_window = MainWindow(self)
        self.main_window.show()
        self.start_overlay()
        self.start_system_tray()
        self.connect_websocket()
        self.start_game_detection()

    def connect_websocket(self):
        def run_ws():
            while True:
                try:
                    self.ws = websocket.WebSocketApp(
                        WS_URL,
                        on_message=self.on_ws_message,
                        on_open=self.on_ws_open,
                        on_close=self.on_ws_close,
                        on_error=self.on_ws_error
                    )
                    self.ws.run_forever()
                except Exception as e:
                    print(f"WS Error: {e}")
                    time.sleep(5)

        threading.Thread(target=run_ws, daemon=True).start()

    def on_ws_open(self, ws):
        print("WebSocket connected")
        if self.current_room:
            ws.send(json.dumps({
                "action": "join_room",
                "room_id": self.current_room,
                "username": self.username,
                "user_id": self.user_id
            }))

    def on_ws_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "message":
            if self.main_window:
                self.main_window.add_message(data)
        elif msg_type == "system":
            if self.main_window:
                self.main_window.add_system_message(data.get("content"))
        elif msg_type == "dm":
            self.show_notification(f"ЛС от {data.get('sender')}", data.get("content"))

    def on_ws_close(self, ws, close_status_code, close_msg):
        print("WebSocket disconnected")

    def on_ws_error(self, ws, error):
        print(f"WS Error: {error}")

    def start_overlay(self):
        self.overlay = GameOverlay(self)
        self.overlay.show()

    def start_system_tray(self):
        def create_tray():
            menu = (
                Item('Показать', self.show_from_tray),
                Item('В игре', lambda: None),
                Item('Выход', self.quit_app)
            )
            
            self.tray = pystray.Icon(
                "mesange",
                QIcon(),  # Можно добавить иконку
                "Mesange",
                menu
            )
            self.tray.run()
        
        threading.Thread(target=create_tray, daemon=True).start()

    def show_from_tray(self):
        if self.main_window:
            self.main_window.show()
        if self.overlay:
            self.overlay.show()

    def quit_app(self):
        self.quit()

    def start_game_detection(self):
        def detect():
            while True:
                try:
                    # Windows: tasklist
                    result = subprocess.run(
                        ['tasklist'],
                        capture_output=True,
                        text=True,
                        shell=True
                    )
                    processes = result.stdout.lower()
                    
                    detected = None
                    for game_name, game_info in GAME_PROCESSES.items():
                        if game_name.lower() in processes:
                            detected = game_name
                            break
                    
                    if detected != self.current_game:
                        self.current_game = detected
                        self.update_overlay()
                        
                        # Отправить статус игры на сервер (опционально)
                        if self.ws and self.ws.sock and self.ws.sock.connected:
                            self.ws.send(json.dumps({
                                "action": "game_status",
                                "game": detected
                            }))
                            
                except Exception as e:
                    print(f"Game detection error: {e}")
                
                time.sleep(5)
        
        threading.Thread(target=detect, daemon=True).start()

    def update_overlay(self):
        if self.overlay:
            self.overlay.update_game(self.current_game, self.online_users)

    def show_notification(self, title, message):
        if self.tray:
            self.tray.notify(title, message)


class AuthWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Mesange - Вход")
        self.setFixedSize(400, 450)
        self.center()
        
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Заголовок
        title = QLabel("Mesange")
        title.setStyleSheet("font-size: 36px; font-weight: bold; color: #00d9ff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Мессенджер нового поколения")
        subtitle.setStyleSheet("color: #a0a0b0;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # Форма
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Логин")
        self.username_input.setStyleSheet("padding: 12px; border-radius: 8px; background: #1a1a2e; border: 1px solid #333; color: white;")
        layout.addWidget(self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet("padding: 12px; border-radius: 8px; background: #1a1a2e; border: 1px solid #333; color: white;")
        layout.addWidget(self.password_input)
        
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #ff6b6b;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Кнопки
        self.login_btn = QPushButton("Войти")
        self.login_btn.setStyleSheet("padding: 14px; border-radius: 8px; background: #00d9ff; color: #0f0f23; font-weight: bold;")
        self.login_btn.clicked.connect(self.login)
        layout.addWidget(self.login_btn)
        
        self.register_btn = QPushButton("Регистрация")
        self.register_btn.setStyleSheet("padding: 14px; border-radius: 8px; background: transparent; border: 1px solid #00d9ff; color: #00d9ff;")
        self.register_btn.clicked.connect(self.register)
        layout.addWidget(self.register_btn)
        
        self.setStyleSheet("background: #0f0f23;")
        self.setLayout(layout)

    def center(self):
        qr = self.frameGeometry()
        cp = QScreen.availableGeometry(QApplication.primaryScreen()).center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def login(self):
        self.auth_request("/api/login")

    def register(self):
        self.auth_request("/api/register")

    def auth_request(self, endpoint):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            self.error_label.setText("Заполните все поля")
            self.error_label.show()
            return
        
        try:
            response = requests.post(
                f"{SERVER_URL}{endpoint}",
                data={"username": username, "password": password}
            )
            data = response.json()
            
            if data.get("success"):
                self.app.username = username
                self.app.user_id = data.get("user_id")
                self.app.is_admin = data.get("is_admin", False)
                self.app.show_main()
            else:
                self.error_label.setText(data.get("error", "Ошибка"))
                self.error_label.show()
        except Exception as e:
            self.error_label.setText("Ошибка соединения")
            self.error_label.show()


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Mesange")
        self.setGeometry(100, 100, 900, 600)
        self.setStyleSheet("background: #0f0f23;")
        
        # Центральный виджет
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QHBoxLayout()
        
        # Сайдбар
        sidebar = QWidget()
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet("background: #1a1a2e;")
        
        sidebar_layout = QVBoxLayout()
        
        # Инфо пользователя
        user_info = QLabel(f"Привет, {app.username}!")
        user_info.setStyleSheet("padding: 20px; color: #00d9ff; font-size: 16px; font-weight: bold;")
        sidebar_layout.addWidget(user_info)
        
        # Список комнат
        self.rooms_list = QListWidget()
        self.rooms_list.setStyleSheet("background: transparent; border: none; color: white;")
        sidebar_layout.addWidget(self.rooms_list)
        
        # Загрузка комнат
        self.load_rooms()
        
        sidebar.setLayout(sidebar_layout)
        layout.addWidget(sidebar)
        
        # Чат
        chat_widget = QWidget()
        chat_layout = QVBoxLayout()
        
        # Заголовок чата
        self.chat_header = QLabel("#general")
        self.chat_header.setStyleSheet("padding: 15px; color: #00d9ff; font-size: 18px; font-weight: bold; background: #16213e;")
        chat_layout.addWidget(self.chat_header)
        
        # Сообщения
        self.messages_area = QScrollArea()
        self.messages_area.setStyleSheet("background: #0f0f23; border: none;")
        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout()
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.messages_widget.setLayout(self.messages_layout)
        self.messages_area.setWidget(self.messages_widget)
        self.messages_area.setWidgetResizable(True)
        chat_layout.addWidget(self.messages_area)
        
        # Ввод сообщения
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Введите сообщение...")
        self.message_input.setStyleSheet("padding: 12px; border-radius: 8px; background: #1a1a2e; border: 1px solid #333; color: white;")
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        
        send_btn = QPushButton("➤")
        send_btn.setStyleSheet("padding: 12px 20px; border-radius: 8px; background: #00d9ff; color: #0f0f23; font-weight: bold;")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        
        chat_layout.addLayout(input_layout)
        chat_widget.setLayout(chat_layout)
        layout.addWidget(chat_widget)
        
        central.setLayout(layout)

    def load_rooms(self):
        try:
            response = requests.get(f"{SERVER_URL}/api/rooms")
            rooms = response.json()
            
            for room in rooms:
                item = QListWidgetItem(f"{'🔒 ' if room.get('is_private') else '💬 '}{room['name']}")
                item.setData(Qt.ItemDataRole.UserRole, room['id'])
                self.rooms_list.addItem(item)
            
            self.rooms_list.itemClicked.connect(self.join_room)
            
            # Присоединиться к первой комнате
            if rooms:
                self.join_room(self.rooms_list.item(0))
                
        except Exception as e:
            print(f"Error loading rooms: {e}")

    def join_room(self, item):
        room_id = item.data(Qt.ItemDataRole.UserRole)
        room_name = item.text().replace('🔒 ', '').replace('💬 ', '')
        
        self.app.current_room = room_id
        self.chat_header.setText(f"#{room_name}")
        
        if self.app.ws and self.app.ws.sock and self.app.ws.sock.connected:
            self.app.ws.send(json.dumps({
                "action": "join_room",
                "room_id": room_id,
                "username": self.app.username,
                "user_id": self.app.user_id
            }))
        
        # Загрузить историю
        self.load_messages(room_id)

    def load_messages(self, room_id):
        try:
            response = requests.get(f"{SERVER_URL}/api/messages/{room_id}")
            messages = response.json()
            
            # Очистить
            while self.messages_layout.count():
                item = self.messages_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            for msg in messages:
                self.add_message(msg, False)
                
        except Exception as e:
            print(f"Error loading messages: {e}")

    def add_message(self, data, animate=True):
        is_own = data.get("username") == self.app.username
        
        msg_widget = QWidget()
        msg_layout = QVBoxLayout()
        
        if is_own:
            msg_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Имя пользователя
        if not is_own:
            username = QLabel(data.get("username", "Unknown"))
            username.setStyleSheet("color: #00d9ff; font-size: 12px;")
            msg_layout.addWidget(username)
        
        # Сообщение
        content = QLabel(data.get("content", ""))
        content.setWordWrap(True)
        
        if is_own:
            content.setStyleSheet("background: #00d9ff; color: #0f0f23; padding: 10px 15px; border-radius: 15px 15px 4px 15px;")
        else:
            content.setStyleSheet("background: #1a1a2e; color: white; padding: 10px 15px; border-radius: 15px 15px 15px 4px;")
        
        msg_layout.addWidget(content)
        
        # Время
        time_label = QLabel(datetime.now().strftime("%H:%M"))
        time_label.setStyleSheet("color: #666; font-size: 11px;")
        msg_layout.addWidget(time_label)
        
        msg_widget.setLayout(msg_layout)
        self.messages_layout.addWidget(msg_widget)
        
        # Прокрутка вниз
        QTimer.singleShot(100, self.scroll_to_bottom)

    def add_system_message(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #666; font-style: italic; padding: 10px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.messages_layout.addWidget(label)

    def scroll_to_bottom(self):
        self.messages_area.verticalScrollBar().setValue(
            self.messages_area.verticalScrollBar().maximum()
        )

    def send_message(self):
        content = self.message_input.text().strip()
        if not content or not self.app.ws:
            return
        
        self.app.ws.send(json.dumps({
            "action": "message",
            "content": content
        }))
        
        self.message_input.clear()


class GameOverlay(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Mesange Overlay")
        self.setFixedSize(300, 180)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        # Позиция справа внизу
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 320, screen.height() - 220)
        
        self.setStyleSheet("""
            background: rgba(15, 15, 35, 0.95);
            border: 1px solid #00d9ff;
            border-radius: 16px;
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        # Заголовок
        header = QHBoxLayout()
        
        self.game_icon = QLabel("🎮")
        self.game_icon.setStyleSheet("font-size: 24px;")
        header.addWidget(self.game_icon)
        
        self.game_name = QLabel("Mesange")
        self.game_name.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        header.addWidget(self.game_name)
        
        header.addStretch()
        
        # Кнопка закрытия
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("background: transparent; border: none; color: #666;")
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        
        layout.addLayout(header)
        
        # Статус
        status_layout = QHBoxLayout()
        
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color: #51cf66; font-size: 14px;")
        status_layout.addWidget(status_dot)
        
        self.status_text = QLabel("В сети")
        self.status_text.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        status_layout.addWidget(self.status_text)
        
        status_layout.addStretch()
        
        layout.addLayout(status_layout)
        
        # Онлайн пользователи
        online_label = QLabel("Сейчас онлайн:")
        online_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(online_label)
        
        self.online_list = QLabel("Нет пользователей")
        self.online_list.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        layout.addWidget(self.online_list)
        
        self.setLayout(layout)

    def update_game(self, game, online_users):
        if game:
            game_info = GAME_PROCESSES.get(game, {'icon': '🎮', 'color': '#00d9ff'})
            self.game_icon.setText(game_info['icon'])
            self.game_name.setText(game)
            self.status_text.setText("Играю прямо сейчас")
        else:
            self.game_icon.setText("💬")
            self.game_name.setText("Mesange")
            self.status_text.setText("В сети")
        
        if online_users:
            self.online_list.setText(", ".join(online_users[:5]))
        else:
            self.online_list.setText("Нет пользователей")


if __name__ == "__main__":
    app = MesangeDesktop()
    sys.exit(app.exec())
