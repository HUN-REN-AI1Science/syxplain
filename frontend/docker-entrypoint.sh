#!/bin/sh
set -e

CERT_PATH="/etc/letsencrypt/live/syxplain.ai1science.net/fullchain.pem"

if [ -f "$CERT_PATH" ]; then
    echo "SSL certificates found — enabling HTTPS"
    cp /etc/nginx/nginx-configs/nginx.ssl.conf /etc/nginx/conf.d/default.conf
else
    echo "No SSL certificates — serving HTTP only"
    cp /etc/nginx/nginx-configs/nginx.conf /etc/nginx/conf.d/default.conf
fi

exec nginx -g "daemon off;"
