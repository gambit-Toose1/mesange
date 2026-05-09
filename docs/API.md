# Документация API мессенджера

## Обзор

Сервер предоставляет REST API для работы с мессенджером. Все запросы, кроме регистрации и входа, требуют JWT токен аутентификации.

## Базовый URL

```
http://localhost:8000
```

## Аутентификация

### Регистрация нового пользователя

**POST** `/auth/register`

**Тело запроса:**
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

**Ответ (201 Created):**
```json
{
  "user_id": 1,
  "username": "string",
  "email": "string",
  "is_admin": false
}
```

### Вход в систему

**POST** `/auth/login`

**Тело запроса:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Ответ (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

## Использование токена

Добавляйте JWT токен в заголовок каждого запроса:

```
Authorization: Bearer <ваш_токен>
```

## Пользователи

### Получить информацию о текущем пользователе

**GET** `/users/me`

**Ответ (200 OK):**
```json
{
  "user_id": 1,
  "username": "string",
  "email": "string",
  "is_admin": false,
  "status": "online"
}
```

### Получить список всех пользователей

**GET** `/users`

**Параметры:**
- `skip` (int, опционально) - количество пропускаемых записей
- `limit` (int, опционально) - максимальное количество записей

**Ответ (200 OK):**
```json
[
  {
    "user_id": 1,
    "username": "string",
    "status": "online"
  },
  {
    "user_id": 2,
    "username": "string",
    "status": "offline"
  }
]
```

## Чаты и комнаты

### Получить список комнат

**GET** `/rooms`

**Ответ (200 OK):**
```json
[
  {
    "room_id": 1,
    "name": "Общий чат",
    "type": "group",
    "members_count": 5,
    "last_message": {
      "text": "Привет!",
      "timestamp": "2024-01-01T12:00:00"
    }
  },
  {
    "room_id": 2,
    "name": "Личный чат с user2",
    "type": "private",
    "members_count": 2,
    "last_message": null
  }
]
```

### Создать новую комнату

**POST** `/rooms`

**Тело запроса:**
```json
{
  "name": "string",
  "type": "group|private",
  "member_ids": [1, 2, 3]
}
```

**Ответ (201 Created):**
```json
{
  "room_id": 3,
  "name": "string",
  "type": "group",
  "created_at": "2024-01-01T12:00:00"
}
```

### Получить историю сообщений

**GET** `/rooms/{room_id}/messages`

**Параметры:**
- `skip` (int, опционально)
- `limit` (int, опционально)

**Ответ (200 OK):**
```json
[
  {
    "message_id": 1,
    "room_id": 1,
    "sender_id": 1,
    "sender_username": "user1",
    "text": "Привет всем!",
    "timestamp": "2024-01-01T12:00:00"
  },
  {
    "message_id": 2,
    "room_id": 1,
    "sender_id": 2,
    "sender_username": "user2",
    "text": "Привет!",
    "timestamp": "2024-01-01T12:01:00"
  }
]
```

### Отправить сообщение

**POST** `/rooms/{room_id}/messages`

**Тело запроса:**
```json
{
  "text": "string"
}
```

**Ответ (201 Created):**
```json
{
  "message_id": 3,
  "room_id": 1,
  "sender_id": 1,
  "text": "string",
  "timestamp": "2024-01-01T12:02:00"
}
```

### Удалить сообщение

**DELETE** `/rooms/{room_id}/messages/{message_id}`

**Ответ (200 OK):**
```json
{
  "success": true,
  "message": "Сообщение удалено"
}
```

## Администрирование

### Получить статистику системы

**GET** `/admin/stats`

**Требуются права:** Администратор

**Ответ (200 OK):**
```json
{
  "total_users": 150,
  "active_users": 45,
  "total_rooms": 30,
  "total_messages": 5000,
  "server_uptime": "7d 12h 30m"
}
```

### Назначить/снять права администратора

**POST** `/admin/users/{user_id}/toggle-admin`

**Требуются права:** Администратор

**Ответ (200 OK):**
```json
{
  "user_id": 5,
  "username": "user5",
  "is_admin": true
}
```

### Получить список всех пользователей (админ)

**GET** `/admin/users`

**Требуются права:** Администратор

**Ответ (200 OK):**
```json
[
  {
    "user_id": 1,
    "username": "string",
    "email": "string",
    "is_admin": false,
    "status": "online",
    "registered_at": "2024-01-01T00:00:00"
  }
]
```

### Заблокировать/разблокировать пользователя

**POST** `/admin/users/{user_id}/toggle-ban`

**Требуются права:** Администратор

**Ответ (200 OK):**
```json
{
  "user_id": 5,
  "username": "user5",
  "is_banned": true
}
```

## WebSocket подключение

Для получения сообщений в реальном времени используйте WebSocket:

```
ws://localhost:8000/ws?token=<ваш_токен>
```

### Формат сообщений

**Входящее сообщение:**
```json
{
  "type": "new_message",
  "data": {
    "message_id": 1,
    "room_id": 1,
    "sender_id": 1,
    "text": "Привет!",
    "timestamp": "2024-01-01T12:00:00"
  }
}
```

**Статус пользователя:**
```json
{
  "type": "user_status",
  "data": {
    "user_id": 1,
    "status": "online|offline"
  }
}
```

## Коды ошибок

| Код | Описание |
|-----|----------|
| 200 | Успешный запрос |
| 201 | Ресурс создан |
| 400 | Некорректный запрос |
| 401 | Не авторизован |
| 403 | Нет доступа |
| 404 | Ресурс не найден |
| 409 | Конфликт (например, пользователь уже существует) |
| 500 | Внутренняя ошибка сервера |

## Примеры использования

### Python (requests)

```python
import requests

# Регистрация
response = requests.post('http://localhost:8000/auth/register', json={
    'username': 'newuser',
    'email': 'newuser@example.com',
    'password': 'password123'
})

# Вход
response = requests.post('http://localhost:8000/auth/login', json={
    'username': 'newuser',
    'password': 'password123'
})
token = response.json()['access_token']

# Получение списка комнат
headers = {'Authorization': f'Bearer {token}'}
response = requests.get('http://localhost:8000/rooms', headers=headers)
rooms = response.json()

# Отправка сообщения
response = requests.post(
    'http://localhost:8000/rooms/1/messages',
    headers=headers,
    json={'text': 'Привет!'}
)
```

### JavaScript (fetch)

```javascript
// Вход
const loginResponse = await fetch('http://localhost:8000/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        username: 'user1',
        password: 'password123'
    })
});
const { access_token } = await loginResponse.json();

// Получение пользователей
const usersResponse = await fetch('http://localhost:8000/users', {
    headers: {'Authorization': `Bearer ${access_token}`}
});
const users = await usersResponse.json();

// Создание личного чата
const roomResponse = await fetch('http://localhost:8000/rooms', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${access_token}`
    },
    body: JSON.stringify({
        name: 'Чат с user2',
        type: 'private',
        member_ids: [1, 2]
    })
});
```

---

**Версия API**: 1.0  
**Дата обновления**: 2024
