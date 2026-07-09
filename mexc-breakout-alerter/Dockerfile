FROM node:20-slim
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY public ./public
COPY .env.example .env
ENV PORT=8000
EXPOSE 8000
CMD ["node", "src/index.js"]
