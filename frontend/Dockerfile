# 1) Next.js statik build
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

# 2) Nginx: statik mini app + /api va /webhooks ni backendga proxy
FROM nginx:1.27-alpine
COPY --from=build /web/out /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
