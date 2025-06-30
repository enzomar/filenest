# nginx/Dockerfile
FROM openresty/openresty:alpine

RUN apk add --no-cache curl bash

# The nginx.conf is mounted via volume, so no need to COPY it here.
# If you prefer copying instead of mounting, uncomment below:
COPY nginx/nginx.conf /usr/local/openresty/nginx/conf/nginx.conf

# Static frontend is copied via volume too, but optionally:
COPY backend/static /usr/share/nginx/html
