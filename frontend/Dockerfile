# ---- build the SPA ---------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# VITE_API_BASE defaults to "/api" (see src/api/client.ts) — nginx proxies it.
RUN npm run build

# ---- serve it -------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# nginx:alpine runs envsubst on *.template at startup -> conf.d/
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# API_UPSTREAM is the host:port of the Chairscore API (compose service name).
ENV API_UPSTREAM=backend:8000

EXPOSE 80
