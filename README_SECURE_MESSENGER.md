# Secure Messenger - Безопасный мессенджер с шифрованием

## Обзор

Это безопасный мессенджер с поддержкой:
- **Личных чатов** (1-на-1)
- **Групповых чатов** (множество участников)
- **Сквозного шифрования** AES-256-GCM
- **Хранения в SQLite** с правильной нормализацией
- **Аутентификации пользователей** с хешированием паролей

## Установка

### Требования
```bash
pip install aiohttp cryptography
```

### Запуск сервера
```bash
python secure_messenger.py
```

Сервер запустится на `http://localhost:8080`

## API Endpoints

### Аутентификация

#### Регистрация пользователя
```bash
POST /api/register
Content-Type: application/json

{
    "username": "alice",
    "password": "secure_password"
}
```

#### Вход
```bash
POST /api/login
Content-Type: application/json

{
    "username": "alice",
    "password": "secure_password"
}
```

### Чаты

#### Создать личный чат
```bash
POST /api/chats/personal
Content-Type: application/json

{
    "user1_id": 1,
    "user2_id": 2
}
```

#### Создать групповой чат
```bash
POST /api/chats/group
Content-Type: application/json

{
    "name": "Development Team",
    "creator_id": 1,
    "participant_ids": [2, 3, 4]
}
```

#### Получить все чаты пользователя
```bash
GET /api/chats?user_id=1
```

#### Добавить участника в групповой чат
```bash
POST /api/chats/participants/add
Content-Type: application/json

{
    "chat_id": 2,
    "user_id": 5,
    "added_by": 1
}
```

#### Удалить участника из группового чата
```bash
POST /api/chats/participants/remove
Content-Type: application/json

{
    "chat_id": 2,
    "user_id": 5,
    "removed_by": 1
}
```

### Сообщения

#### Получить сообщения чата
```bash
GET /api/messages?chat_id=1&limit=50&offset=0
```

### Пользователи

#### Получить всех пользователей
```bash
GET /api/users
```

## WebSocket API

Подключение к WebSocket: `ws://localhost:8080/ws`

### Сообщения клиента

#### Аутентификация
```json
{
    "type": "auth",
    "username": "alice",
    "password": "secure_password"
}
```

#### Отправить сообщение
```json
{
    "type": "send_message",
    "chat_id": 1,
    "encrypted_data": {
        "nonce": "base64_encoded_nonce",
        "ciphertext": "base64_encoded_ciphertext",
        "encrypted": true
    },
    "timestamp": "2024-01-01T12:00:00"
}
```

#### Присоединиться к чату
```json
{
    "type": "join_chat",
    "chat_id": 1
}
```

#### Индикатор набора текста
```json
{
    "type": "typing",
    "chat_id": 1,
    "is_typing": true
}
```

### Сообщения сервера

#### Успешная аутентификация
```json
{
    "type": "auth_success",
    "user_id": 1,
    "username": "alice"
}
```

#### Новое сообщение
```json
{
    "type": "new_message",
    "message_id": 1,
    "chat_id": 1,
    "sender_id": 1,
    "sender_username": "alice",
    "encrypted_data": {
        "nonce": "...",
        "ciphertext": "...",
        "encrypted": true
    },
    "timestamp": "2024-01-01T12:00:00"
}
```

#### Пользователь онлайн/офлайн
```json
{
    "type": "user_online",
    "user_id": 1,
    "username": "alice"
}
```

```json
{
    "type": "user_offline",
    "user_id": 1,
    "username": "alice"
}
```

#### Пользователь печатает
```json
{
    "type": "user_typing",
    "chat_id": 1,
    "user_id": 1,
    "username": "alice",
    "is_typing": true
}
```

## Шифрование

### Как это работает

1. **Генерация ключа чата**: При создании чата генерируется случайный 256-битный ключ
2. **Шифрование сообщений**: Каждое сообщение шифруется с помощью AES-256-GCM
3. **Хранение**: В базе данных хранятся только зашифрованные данные (nonce + ciphertext)
4. **Распределение ключей**: Ключ чата передаётся участникам при создании/добавлении в чат

### Функции шифрования

```python
from secure_messenger import encrypt_message, decrypt_message, derive_key, generate_salt

# Генерация соли и ключа
salt = generate_salt()
key = derive_key("shared_secret", salt)

# Шифрование
encrypted = encrypt_message("Secret message", key)
# Returns: {"nonce": "...", "ciphertext": "...", "encrypted": True}

# Дешифрование
decrypted = decrypt_message(encrypted, key)
# Returns: "Secret message"
```

## Структура базы данных

### Таблицы

1. **users** - Пользователи
   - id, username, password_hash, salt, public_key, is_blocked, is_online, first_seen, last_seen

2. **chats** - Чаты
   - id, chat_type (personal/group), name, encryption_key_salt, created_by, created_at

3. **chat_participants** - Участники чатов
   - id, chat_id, user_id, joined_at, role (owner/admin/member)

4. **messages** - Сообщения
   - id, chat_id, sender_id, message_nonce, message_ciphertext, timestamp, created_at, is_read

## Тестирование

Запустить тесты шифрования:
```bash
python test_encryption.py
```

## Пример использования

```python
import requests
import json

# Регистрация пользователей
requests.post('http://localhost:8080/api/register', 
              json={"username": "alice", "password": "pass123"})
requests.post('http://localhost:8080/api/register', 
              json={"username": "bob", "password": "pass456"})

# Вход
resp = requests.post('http://localhost:8080/api/login',
                     json={"username": "alice", "password": "pass123"})
alice = resp.json()

# Создание личного чата
chat = requests.post('http://localhost:8080/api/chats/personal',
                     json={"user1_id": alice["user_id"], "user2_id": 2})
chat_id = chat.json()["chat_id"]
encryption_key = chat.json()["encryption_key"]

# Шифрование и отправка сообщения
from secure_messenger import encrypt_message, derive_key
from datetime import datetime

key = bytes.fromhex(encryption_key)
encrypted = encrypt_message("Hello Bob!", key)

# Через WebSocket отправить сообщение...
```

## Безопасность

### Реализованные меры безопасности:

1. ✅ **AES-256-GCM шифрование** - современный стандарт шифрования
2. ✅ **PBKDF2-HMAC-SHA256** - для деривации ключей из паролей
3. ✅ **Случайные соли** - для каждого пользователя и чата
4. ✅ **Уникальные nonce** - для каждого зашифрованного сообщения
5. ✅ **Хеширование паролей** - пароли не хранятся в открытом виде
6. ✅ **Проверка прав доступа** - только участники могут читать сообщения
7. ✅ **Роли в чатах** - owner, admin, member с разными правами

### Рекомендации для production:

1. Используйте HTTPS/WSS вместо HTTP/WS
2. Добавьте rate limiting для предотвращения brute-force атак
3. Реализуйте refresh token для сессий
4. Добавьте двухфакторную аутентификацию
5. Используйте proper key exchange protocol (например, Double Ratchet)
6. Регулярно обновляйте зависимости

## Лицензия

MIT License
