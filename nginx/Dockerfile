# nginx/Dockerfile
FROM nginx:stable-alpine

RUN apk add --no-cache lua-resty-core lua-resty-lrucache lua-resty-string

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY backend/static /usr/share/nginx/html
