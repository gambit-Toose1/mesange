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
import psutil

# Конфигурация
SERVER_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

# Расширенная база данных игр для точного определения
# Формат: 'Название': {'icon': 'эмодзи', 'color': 'hex', 'processes': ['имя_процесса'], 'titles': ['часть_заголовка_окна']}
GAME_DATABASE = {
    # Шутеры
    'Counter-Strike 2': {'icon': '🔫', 'color': '#de9b35', 'processes': ['cs2', 'csgo'], 'titles': ['Counter-Strike']},
    'Counter-Strike: Global Offensive': {'icon': '🔫', 'color': '#de9b35', 'processes': ['csgo'], 'titles': ['CS:GO']},
    'Valorant': {'icon': '🎯', 'color': '#ff4655', 'processes': ['valorant', 'vgc', 'vgtray'], 'titles': ['VALORANT']},
    'Overwatch 2': {'icon': '🛡️', 'color': '#f99e1a', 'processes': ['overwatch', 'overwatch2'], 'titles': ['Overwatch']},
    'Apex Legends': {'icon': '🏃', 'color': '#d92027', 'processes': ['r5apex'], 'titles': ['Apex Legends']},
    'Call of Duty: Warzone': {'icon': '💣', 'color': '#6aa84f', 'processes': ['cod', 'warzone', 'modernwarfare'], 'titles': ['Call of Duty', 'Warzone']},
    'Rainbow Six Siege': {'icon': '🚨', 'color': '#333333', 'processes': ['rainbowsix', 'siege'], 'titles': ['Rainbow Six', 'Siege']},
    'Team Fortress 2': {'icon': '🎩', 'color': '#b88636', 'processes': ['hl2', 'tf2'], 'titles': ['Team Fortress']},
    'Destiny 2': {'icon': '🌌', 'color': '#ce2829', 'processes': ['destiny2', 'destiny'], 'titles': ['Destiny']},
    
    # MOBA
    'League of Legends': {'icon': '⚔️', 'color': '#c89b3c', 'processes': ['leagueoflegends', 'lolclient', 'leagueclient'], 'titles': ['League of Legends']},
    'Dota 2': {'icon': '🎮', 'color': '#e44c2c', 'processes': ['dota2', 'dota'], 'titles': ['Dota 2']},
    'Heroes of the Storm': {'icon': '⛈️', 'color': '#a332c7', 'processes': ['heroesofthestorm', 'heroes'], 'titles': ['Heroes of the Storm']},
    
    # Королевские битвы / Выживание
    'Fortnite': {'icon': '🏝️', 'color': '#9c4dbc', 'processes': ['fortnite', 'epicgameslauncher'], 'titles': ['Fortnite']},
    'PUBG: BATTLEGROUNDS': {'icon': '🪖', 'color': '#f2a900', 'processes': ['tslgame', 'pubg'], 'titles': ['PUBG']},
    'Rust': {'icon': '🔨', 'color': '#cd3232', 'processes': ['rustclient', 'rust'], 'titles': ['Rust']},
    'ARK: Survival Evolved': {'icon': '🦕', 'color': '#008080', 'processes': ['arkse', 'shooter_game'], 'titles': ['ARK']},
    'Minecraft': {'icon': '⛏️', 'color': '#62b47a', 'processes': ['minecraft', 'javaw'], 'titles': ['Minecraft']},
    'Terraria': {'icon': '⚒️', 'color': '#5b9bd5', 'processes': ['terraria'], 'titles': ['Terraria']},
    
    # RPG
    'The Witcher 3': {'icon': '🗡️', 'color': '#8b0000', 'processes': ['witcher3', 'cyberpunk'], 'titles': ['Witcher']},
    'Cyberpunk 2077': {'icon': '🤖', 'color': '#fcee0a', 'processes': ['cyberpunk2077'], 'titles': ['Cyberpunk']},
    'Elden Ring': {'icon': '💍', 'color': '#c9a66b', 'processes': ['eldenring'], 'titles': ['ELDEN RING']},
    'Skyrim': {'icon': '🐉', 'color': '#5a5a5a', 'processes': ['skyrimse', 'skyrimvr', 'tesv'], 'titles': ['Skyrim', 'Elder Scrolls']},
    'Genshin Impact': {'icon': '✨', 'color': '#7a8fa3', 'processes': ['genshinimpact', 'yuan_shen'], 'titles': ['Genshin Impact']},
    'World of Warcraft': {'icon': '🛡️', 'color': '#f8b700', 'processes': ['wow', 'worldofwarcraft'], 'titles': ['World of Warcraft']},
    'Final Fantasy XIV': {'icon': '⭐', 'color': '#0057ff', 'processes': ['ffxiv', 'finalfantasy'], 'titles': ['FINAL FANTASY XIV']},
    
    # Стратегии / Симуляторы
    'StarCraft II': {'icon': '🚀', 'color': '#0044bb', 'processes': ['starcraft', 'sc2'], 'titles': ['StarCraft']},
    'Civilization VI': {'icon': '🏛️', 'color': '#6a5acd', 'processes': ['civilization', 'civ6'], 'titles': ['Civilization']},
    'The Sims 4': {'icon': '🏠', 'color': '#00a8e1', 'processes': ['ts4', 'thesims4'], 'titles': ['The Sims']},
    'Cities: Skylines': {'icon': '🏙️', 'color': '#ff6600', 'processes': ['cities', 'skylines'], 'titles': ['Cities: Skylines']},
    
    # Песочницы / Творчество
    'Roblox': {'icon': '🧱', 'color': '#de2828', 'processes': ['robloxplayerbeta', 'roblox'], 'titles': ['Roblox']},
    'Stardew Valley': {'icon': '🌾', 'color': '#ff9933', 'processes': ['stardewvalley'], 'titles': ['Stardew Valley']},
    
    # Гонки / Спорт
    'Grand Theft Auto V': {'icon': '🚗', 'color': '#6cd300', 'processes': ['gta5', 'gtav'], 'titles': ['Grand Theft Auto', 'GTA V']},
    'Forza Horizon 5': {'icon': '🏎️', 'color': '#ff6b00', 'processes': ['forza', 'horizon5'], 'titles': ['Forza']},
    'FIFA 23': {'icon': '⚽', 'color': '#000000', 'processes': ['fifa23', 'fifa'], 'titles': ['FIFA']},
    'Rocket League': {'icon': '🚀⚽', 'color': '#0077be', 'processes': ['rocketleague'], 'titles': ['Rocket League']},
    
    # Лаунчеры (резервное определение)
    'Steam': {'icon': '🎮', 'color': '#171a21', 'processes': ['steam', 'steamwebhelper'], 'titles': ['Steam']},
    'Discord': {'icon': '💬', 'color': '#5865f2', 'processes': ['discord', 'discordcanary'], 'titles': ['Discord']},
    'Epic Games': {'icon': '🎯', 'color': '#333333', 'processes': ['epicgameslauncher'], 'titles': ['Epic Games']},
}

# Эвристика для универсальных процессов
GENERIC_PROCESS_HEURISTICS = {
    'javaw.exe': ['Minecraft', 'Old School RuneScape', 'Runescape'],
    'unity.exe': ['Unity Game'],
    'unrealengine.exe': ['Unreal Engine Game'],
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
        elif msg_type == "kicked":
            QMessageBox.warning(None, "Ошибка", data.get("content", "Вы были исключены"))
            if self.main_window:
                self.main_window.close()

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
        """Запускает поток обнаружения игр с улучшенной эвристикой"""
        def detect():
            last_check = {}  # Для debounce (предотвращение мерцания)
            consecutive_matches = {}  # Счётчик последовательных совпадений
            
            while True:
                try:
                    # Получаем список процессов через psutil (кроссплатформенно)
                    running_processes = []
                    window_titles = []
                    
                    try:
                        # Используем psutil для получения процессов
                        for proc in psutil.process_iter(['pid', 'name', 'exe']):
                            try:
                                proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                                proc_exe = proc.info['exe'] or ''
                                running_processes.append({
                                    'name': proc_name,
                                    'exe': proc_exe.lower(),
                                    'pid': proc.info['pid']
                                })
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        
                        # Получаем заголовки окон (только Windows)
                        if sys.platform == 'win32':
                            import subprocess
                            result = subprocess.run(
                                ['powershell', '-Command', 
                                 'Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object MainWindowTitle -ExpandProperty MainWindowTitle'],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            window_titles = [line.strip().lower() for line in result.stdout.split('\n') if line.strip()]
                    except Exception as e:
                        print(f"Process enumeration error: {e}")
                        time.sleep(5)
                        continue
                    
                    detected_game = None
                    confidence = 0
                    detection_method = None
                    
                    # Метод 1: Точное совпадение по имени процесса
                    for game_name, game_info in GAME_DATABASE.items():
                        processes = game_info.get('processes', [])
                        for proc in running_processes:
                            proc_name = proc['name']
                            if any(p.lower() in proc_name or proc_name in p.lower() for p in processes):
                                # Высокая уверенность - точное совпадение процесса
                                if proc_name in [p.lower() for p in processes]:
                                    new_confidence = 100
                                else:
                                    new_confidence = 80
                                
                                if new_confidence > confidence:
                                    detected_game = game_name
                                    confidence = new_confidence
                                    detection_method = 'process'
                    
                    # Метод 2: Совпадение по заголовку окна (если процесс не найден)
                    if not detected_game and window_titles:
                        for game_name, game_info in GAME_DATABASE.items():
                            titles = game_info.get('titles', [])
                            for title in window_titles:
                                if any(t.lower() in title for t in titles):
                                    new_confidence = 70
                                    if new_confidence > confidence:
                                        detected_game = game_name
                                        confidence = new_confidence
                                        detection_method = 'window'
                    
                    # Метод 3: Эвристика для универсальных процессов (Java, Unity, Unreal)
                    if not detected_game:
                        for proc in running_processes:
                            proc_name = proc['name']
                            if proc_name in GENERIC_PROCESS_HEURISTICS:
                                candidates = GENERIC_PROCESS_HEURISTICS[proc_name]
                                # Проверяем путь к исполняемому файлу для уточнения
                                proc_exe = proc['exe']
                                for candidate in candidates:
                                    if candidate.lower() in proc_exe or any(c.lower() in proc_exe for c in GAME_DATABASE.get(candidate, {}).get('processes', [])):
                                        detected_game = candidate
                                        confidence = 60
                                        detection_method = 'heuristic'
                                        break
                    
                    # Debounce логика: требуем 3 последовательных совпадения для подтверждения
                    if detected_game:
                        consecutive_matches[detected_game] = consecutive_matches.get(detected_game, 0) + 1
                        if consecutive_matches[detected_game] >= 3:
                            # Игра подтверждена
                            if detected_game != self.current_game:
                                old_game = self.current_game
                                self.current_game = detected_game
                                self.update_overlay()
                                
                                # Отправить статус игры на сервер
                                if self.ws and hasattr(self.ws, 'sock') and self.ws.sock and self.ws.sock.connected:
                                    try:
                                        self.ws.send(json.dumps({
                                            "action": "game_status",
                                            "game": detected_game,
                                            "confidence": confidence,
                                            "method": detection_method
                                        }))
                                        print(f"🎮 Game detected: {detected_game} ({detection_method}, {confidence}%)")
                                    except Exception as e:
                                        print(f"WebSocket send error: {e}")
                        else:
                            # Ещё не достаточно подтверждений
                            pass
                    else:
                        # Сбрасываем счётчики если игра не найдена
                        consecutive_matches.clear()
                        if self.current_game is not None:
                            old_game = self.current_game
                            self.current_game = None
                            self.update_overlay()
                            
                            if self.ws and hasattr(self.ws, 'sock') and self.ws.sock and self.ws.sock.connected:
                                try:
                                    self.ws.send(json.dumps({
                                        "action": "game_status",
                                        "game": None
                                    }))
                                    print(f"❌ Game ended: {old_game}")
                                except Exception as e:
                                    print(f"WebSocket send error: {e}")
                    
                except Exception as e:
                    print(f"Game detection error: {e}")
                
                time.sleep(2)  # Уменьшили интервал для более быстрого обнаружения
        
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
            # Используем новую расширенную базу данных GAME_DATABASE
            game_info = GAME_DATABASE.get(game, {'icon': '🎮', 'color': '#00d9ff'})
            self.game_icon.setText(game_info['icon'])
            self.game_name.setText(game)
            self.status_text.setText("Играю прямо сейчас")
            
            # Обновляем цвет оверлея в соответствии с игрой
            self.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 {game_info['color']}dd, 
                        stop:1 {game_info['color']}88);
                    border-radius: 15px;
                    border: 2px solid {game_info['color']};
                }}
                QLabel {{
                    color: white;
                    font-weight: bold;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
                }}
            """)
        else:
            self.game_icon.setText("💬")
            self.game_name.setText("Mesange")
            self.status_text.setText("В сети")
            
            # Стандартный стиль когда не в игре
            self.setStyleSheet("""
                QWidget {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #667eeaDD, 
                        stop:1 #764ba288);
                    border-radius: 15px;
                    border: 2px solid #667eea;
                }
                QLabel {
                    color: white;
                    font-weight: bold;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
                }
            """)
        
        if online_users:
            self.online_list.setText(", ".join(online_users[:5]))
        else:
            self.online_list.setText("Нет пользователей")


if __name__ == "__main__":
    app = MesangeDesktop()
    sys.exit(app.exec())
