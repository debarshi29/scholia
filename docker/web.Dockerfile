# Scholia web app: build with Node, serve the static bundle with nginx, forward /api to the API.
#   docker build -f docker/web.Dockerfile -t scholia-web .
FROM node:24-alpine AS build
RUN npm install -g pnpm@12
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
