FROM node:16.13.1-slim

ENV NODE_ENV=production
WORKDIR /app
COPY ["package.json", "package-lock.json*", "./"]
RUN npm install
COPY . .
CMD ["node", "ws_server.js"]
