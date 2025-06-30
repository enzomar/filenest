# nginx/Dockerfile
FROM nginx:stable-alpine

# Copy custom NGINX config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy frontend static files from backend/static
COPY ../backend/static /usr/share/nginx/html
