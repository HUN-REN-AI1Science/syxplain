# Stage 1: Build
FROM node:24-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm install

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

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
