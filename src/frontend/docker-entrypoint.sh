#!/bin/sh
set -e

# HTTPS is enabled when SERVER_NAME is set and a Let's Encrypt certificate exists for it
# (mounted at /etc/letsencrypt). Otherwise nginx serves plain HTTP.
CERT_PATH="/etc/letsencrypt/live/${SERVER_NAME}/fullchain.pem"

if [ -n "$SERVER_NAME" ] && [ -f "$CERT_PATH" ]; then
    echo "SSL certificate found for ${SERVER_NAME} — enabling HTTPS"
    # Substitute only SERVER_NAME, so nginx variables like $host stay intact
    envsubst '${SERVER_NAME}' < /etc/nginx/nginx-configs/nginx.ssl.conf > /etc/nginx/conf.d/default.conf
else
    if [ -n "$SERVER_NAME" ]; then
        echo "No SSL certificate at ${CERT_PATH} — serving HTTP only"
    else
        echo "SERVER_NAME not set — serving HTTP only"
    fi
    cp /etc/nginx/nginx-configs/nginx.conf /etc/nginx/conf.d/default.conf
fi

exec nginx -g "daemon off;"
