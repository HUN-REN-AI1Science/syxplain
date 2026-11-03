# syntax=docker/dockerfile:1
# Stage 1: Build
FROM node:26-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

ARG VITE_KEYCLOAK_URL
ARG VITE_KEYCLOAK_REALM
ARG VITE_KEYCLOAK_CLIENT_ID

ENV VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL
ENV VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM
ENV VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID

COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# Copy both nginx configs into the image
COPY nginx.conf /etc/nginx/nginx-configs/nginx.conf
COPY nginx.ssl.conf /etc/nginx/nginx-configs/nginx.ssl.conf

# Entrypoint picks the right config based on whether SSL certs exist
COPY docker-entrypoint.sh /docker-entrypoint-custom.sh
RUN chmod +x /docker-entrypoint-custom.sh

EXPOSE 80 443
ENTRYPOINT ["/docker-entrypoint-custom.sh"]
