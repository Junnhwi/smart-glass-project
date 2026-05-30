FROM node:22-alpine AS build

WORKDIR /repo

COPY package.json package-lock.json ./
COPY apps/admin-web/package.json apps/admin-web/package.json
RUN npm ci --workspace=apps/admin-web --include-workspace-root=false

COPY apps/admin-web apps/admin-web
RUN npm run build --workspace=apps/admin-web

FROM nginx:1.27-alpine

COPY infra/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/admin-web/dist /usr/share/nginx/html

EXPOSE 80
