FROM node:18-alpine

WORKDIR /app

COPY package.json .

RUN npm install --production

COPY server.js client.html ./

EXPOSE 3000

ENV PORT=3000

CMD ["npm", "start"]
