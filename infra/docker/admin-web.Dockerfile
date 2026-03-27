FROM node:22-alpine

WORKDIR /app

COPY apps/admin-web/package.json .

CMD ["sh", "-c", "echo admin-web placeholder"]
