FROM node:22-alpine

WORKDIR /app

COPY apps/api-server/package.json .

CMD ["sh", "-c", "echo api-server placeholder"]
