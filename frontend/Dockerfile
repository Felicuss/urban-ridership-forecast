# syntax=docker/dockerfile:1
# Интерфейс и шлюз одним образом: nginx раздаёт собранный фронт и проксирует /api на реплики сервиса.
# Сборка из корня репозитория: docker build -f frontend/Dockerfile .

FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
# типы клиента уже лежат в src/api/schema.d.ts, сервис для сборки не нужен
RUN npm run build \
    && find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.geojson' -o -name '*.svg' \) \
       -exec gzip -9 -k {} \;

FROM nginx:1.30-alpine
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
