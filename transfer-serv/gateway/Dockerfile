FROM node:24-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY gateway gateway

RUN npx tsc -p gateway/tsconfig.json


FROM node:24-bookworm-slim

ENV NODE_ENV=production

WORKDIR /app

COPY --from=build /app/gateway/dist ./dist

USER node

EXPOSE 3000

CMD ["node", "dist/server.js"]
