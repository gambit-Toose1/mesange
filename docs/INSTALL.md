# Руководство по установке и запуску

## Системные требования

### Сервер
- Python 3.8 или выше
- 512 MB RAM (минимум)
- SQLite (встроен в Python)

### Веб-клиент
- Любой современный браузер (Chrome, Firefox, Safari, Edge)

### Десктоп-клиент
- Python 3.8 или выше
- PyQt6
- 1 GB RAM

### Мобильное приложение
- Flutter SDK 3.24 или выше
- Android SDK (для сборки APK)
- Xcode (для iOS, только на macOS)

---

## Установка сервера

### Шаг 1: Установка зависимостей

```bash
pip install sqlalchemy aiohttp pyjwt
```

Или используйте requirements.txt (если есть):

```bash
pip install -r requirements.txt
```

### Шаг 2: Настройка (опционально)

Создайте файл `.env` для хранения секретных ключей:

```bash
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///./messenger.db
HOST=0.0.0.0
PORT=8000
```

### Шаг 3: Запуск сервера

```bash
python server.py
```

Сервер запустится на `http://localhost:8000`

### Шаг 4: Проверка работы

Откройте в браузере:
- API документация: `http://localhost:8000/docs`
- Главная страница: `http://localhost:8000/`

---

## Установка веб-клиента

### Вариант 1: Простой запуск

Просто откройте файл `index.html` в браузере.

### Вариант 2: Локальный HTTP сервер

```bash
# Python 3
python -m http.server 8080

# Python 2
python -m SimpleHTTPServer 8080
```

Затем откройте `http://localhost:8080/index.html`

### Вариант 3: Использование Live Server (VS Code)

1. Установите расширение "Live Server" в VS Code
2. Откройте `index.html`
3. Нажмите "Go Live"

---

## Установка десктоп-клиента

### Шаг 1: Установка зависимостей

```bash
pip install PyQt6 websocket-client
```

### Шаг 2: Запуск приложения

```bash
python desktop.py
```

### Возможные проблемы

**Ошибка: PyQt6 не найден**
```bash
pip uninstall PyQt6
pip install PyQt6 --no-cache-dir
```

**Ошибка: нет отображения (Linux headless)**
```bash
# Используйте виртуальный дисплей
xvfb-run python desktop.py
```

---

## Установка мобильного приложения

### Предварительные требования

1. **Установите Flutter SDK**
   
   Следуйте официальной инструкции: https://docs.flutter.dev/get-started/install
   
2. **Проверьте установку**
   ```bash
   flutter doctor
   ```

3. **Настройте эмулятор или подключите устройство**

### Шаг 1: Перейдите в директорию mobile

```bash
cd mobile
```

### Шаг 2: Установите зависимости

```bash
flutter pub get
```

### Шаг 3: Запуск в режиме разработки

```bash
# Запуск на подключенном устройстве или эмуляторе
flutter run

# Запуск в режиме отладки с хот-релоадом
flutter run --hot
```

### Шаг 4: Сборка релизной версии

#### Для Android

```bash
# Сборка APK
flutter build apk --release

# Сборка App Bundle (для Google Play)
flutter build appbundle --release
```

Готовый APK будет находиться в:
```
mobile/build/app/outputs/flutter-apk/app-release.apk
```

#### Для iOS (только macOS)

```bash
flutter build ios --release
```

### Шаг 5: Установка на устройство

#### Android
```bash
# Установка через ADB
adb install build/app/outputs/flutter-apk/app-release.apk
```

#### iOS
Следуйте инструккам Flutter для деплоя на iOS устройства.

---

## Конфигурация

### Настройка подключения к серверу

#### Веб-клиент

Откройте `index.html` и найдите строку:

```javascript
const SERVER_URL = 'http://localhost:8000';
```

Замените на адрес вашего сервера.

#### Десктоп-клиент

В файле `desktop.py` найдите:

```python
SERVER_URL = 'http://localhost:8000'
WS_URL = 'ws://localhost:8000/ws'
```

Измените при необходимости.

#### Мобильное приложение

В файле `mobile/lib/config.dart`:

```dart
class Config {
  static const String serverUrl = 'http://localhost:8000';
  static const String wsUrl = 'ws://localhost:8000/ws';
}
```

**Важно:** Для тестирования на реальном устройстве используйте IP вашего компьютера вместо `localhost`.

---

## Production развертывание

### Сервер

#### Использование Gunicorn (рекомендуется)

```bash
pip install gunicorn uvicorn

gunicorn -w 4 -k uvicorn.workers.UvicornWorker server:app --bind 0.0.0.0:8000
```

#### Docker

Создайте `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "server.py"]
```

Сборка и запуск:

```bash
docker build -t messenger-server .
docker run -p 8000:8000 messenger-server
```

#### Docker Compose

Создайте `docker-compose.yml`:

```yaml
version: '3.8'

services:
  server:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - SECRET_KEY=your-production-secret-key
    restart: unless-stopped
```

Запуск:

```bash
docker-compose up -d
```

### Веб-клиент

Разместите `index.html` на любом статическом хостинге:
- Nginx
- Apache
- Netlify
- Vercel
- GitHub Pages

#### Пример конфигурации Nginx

```nginx
server {
    listen 80;
    server_name messenger.example.com;

    root /var/www/messenger;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Устранение неполадок

### Сервер не запускается

**Проблема:** Порт 8000 занят
```bash
# Найдите процесс, использующий порт
lsof -i :8000

# Или измените порт в server.py
```

**Проблема:** Ошибка импорта модулей
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Веб-клиент не подключается

**Проблема:** CORS ошибки
- Убедитесь, что сервер настроен на разрешение CORS
- Проверьте, что используете правильный URL сервера

**Проблема:** WebSocket не соединяется
- Проверьте, что WS URL правильный
- Убедитесь, что фаервол не блокирует соединение

### Мобильное приложение

**Проблема:** Flutter не найден
```bash
export PATH="$PATH:`pwd`/flutter/bin"
```

**Проблема:** Ошибки при сборке APK
```bash
flutter clean
flutter pub get
flutter build apk --release
```

**Проблема:** Не удается подключиться к локальному серверу
- Используйте IP компьютера вместо localhost
- Убедитесь, что сервер слушает на 0.0.0.0
- Проверьте настройки фаервола

---

## Обновление

### Сервер

```bash
git pull origin master
pip install -r requirements.txt --upgrade
# Перезапустите сервер
```

### Мобильное приложение

```bash
git pull origin master
cd mobile
flutter pub get
flutter build apk --release
```

---

## Безопасность

### Рекомендации для production

1. **Измените SECRET_KEY** на случайную строку
2. **Используйте HTTPS** для всех соединений
3. **Настройте фаервол** для ограничения доступа
4. **Регулярно обновляйте** зависимости
5. **Используйте переменные окружения** для конфиденциальных данных
6. **Настройте логирование** для мониторинга

### Генерация безопасного SECRET_KEY

```python
import secrets
print(secrets.token_urlsafe(32))
```

---

## Дополнительная помощь

- Документация API: `/docs` на запущенном сервере
- Issues на GitHub для сообщений об ошибках
- Обсуждения в Discord/Telegram канале проекта
