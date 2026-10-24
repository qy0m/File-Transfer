FROM node:24-bookworm-slim AS assets

WORKDIR /build

COPY package.json package-lock.json ./

RUN npm ci

COPY frontend/tsconfig.json frontend/tsconfig.json
COPY frontend/src frontend/src

COPY gateway/tsconfig.json gateway/tsconfig.json
COPY gateway/src gateway/src

COPY scripts/clone-bootstrap.mjs scripts/clone-bootstrap.mjs

RUN npm run build


FROM php:8.4-fpm-bookworm AS php

WORKDIR /var/www/html

COPY frontend/public ./public
COPY frontend/includes ./includes

COPY --from=assets /build/frontend/public/assets ./public/assets

RUN find /var/www/html -type f -name '*.php' -print0 \
    | xargs -0 -r -n 1 php -l

FROM nginx:stable-bookworm AS web

COPY nginx/default.conf /etc/nginx/conf.d/default.conf

COPY frontend/public /var/www/html/public

COPY --from=assets /build/frontend/public/assets /var/www/html/public/assets
