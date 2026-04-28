const express = require('express');
const http = require('http');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

// Хранилище пользователей и их публичных ключей
const users = new Map();

app.get('/', (req, res) => {
  res.sendFile(__dirname + '/client.html');
});

io.on('connection', (socket) => {
  console.log('Пользователь подключился:', socket.id);

  // Регистрация пользователя
  socket.on('register', (username) => {
    users.set(socket.id, { username, publicKey: null });
    socket.emit('registered', socket.id);
    io.emit('user-list', Array.from(users.values()).map(u => u.username));
    console.log(`Пользователь ${username} зарегистрирован`);
  });

  // Обмен публичными ключами для E2E шифрования
  socket.on('public-key', (data) => {
    const user = users.get(socket.id);
    if (user) {
      user.publicKey = data.publicKey;
    }
    // Рассылаем публичный ключ всем остальным
    socket.broadcast.emit('public-key', {
      userId: socket.id,
      username: users.get(socket.id)?.username,
      publicKey: data.publicKey
    });
  });

  // Получение списка пользователей с их ключами
  socket.on('request-keys', () => {
    const keys = {};
    users.forEach((user, id) => {
      if (user.publicKey) {
        keys[id] = { username: user.username, publicKey: user.publicKey };
      }
    });
    socket.emit('keys-list', keys);
  });

  // Отправка зашифрованного сообщения
  socket.on('encrypted-message', (data) => {
    const sender = users.get(socket.id);
    console.log(`Сообщение от ${sender?.username} к ${data.to}`);
    
    // Пересылаем зашифрованное сообщение получателю
    io.to(data.to).emit('message', {
      from: socket.id,
      fromUsername: sender?.username,
      encryptedData: data.encryptedData,
      timestamp: new Date().toISOString()
    });
  });

  socket.on('disconnect', () => {
    const user = users.get(socket.id);
    if (user) {
      console.log(`Пользователь ${user.username} отключился`);
      users.delete(socket.id);
      io.emit('user-list', Array.from(users.values()).map(u => u.username));
    }
  });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`Сервер запущен на порту ${PORT}`);
});
