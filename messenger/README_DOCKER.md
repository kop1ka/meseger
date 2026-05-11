# Secure Messenger with End-to-End Encryption

Простой мессенджер с поддержкой end-to-end шифрования сообщений.

## Структура проекта

```
messenger/
├── server.js        # Сервер на Node.js + Socket.IO
├── client.html      # Веб-клиент с интерфейсом чата
├── package.json     # Зависимости Node.js
├── Dockerfile       # Docker образ для сервера
└── docker-compose.yml # Docker Compose конфигурация
```

## Запуск без Docker

1. Установите зависимости:
```bash
npm install
```

2. Запустите сервер:
```bash
npm start
```

3. Откройте браузер по адресу: http://localhost:3000

## Запуск с Docker

### Вариант 1: Использование docker build

```bash
# Сборка образа
docker build -t secure-messenger .

# Запуск контейнера
docker run -p 3000:3000 secure-messenger
```

### Вариант 2: Использование Docker Compose

```bash
docker-compose up -d
```

Сервер будет доступен по адресу: http://localhost:3000

## Возможности

- 🔐 End-to-End шифрование сообщений (AES)
- 👥 Список пользователей онлайн
- 💬 Обмен сообщениями в реальном времени
- 🎨 Современный UI с градиентным дизайном
- 📱 Адаптивный интерфейс

## Технологии

- **Backend**: Node.js, Express, Socket.IO
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Шифрование**: CryptoJS (AES)
- **Контейнеризация**: Docker, Docker Compose

## Порты

- `3000` - Порт веб-сервера и WebSocket соединений
