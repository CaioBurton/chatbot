# =============================================================================
# PROPESQI Frontend — Node 20 + React/Vite  (multi-stage build)
#
# Stage 1 (builder): compiles the Vite project into static assets under /dist.
# Stage 2 (runner):  serves /dist with the `serve` static file server.
#
# VITE_API_URL is a build-time argument; Vite replaces all import.meta.env.*
# references at bundle time, so it must be provided during `docker build`.
# =============================================================================

# =============================================================================
# Stage 1 — builder
# =============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Layer-cache optimisation: install dependencies before copying source.
# This layer is only invalidated when package-lock.json changes.
COPY package*.json ./
RUN npm ci

# Inject the public API URL at Vite build time.
# The value is passed via `build.args` in docker-compose.yml.
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Copy remaining source files and produce the production bundle.
COPY . .
RUN npm run build


# =============================================================================
# Stage 2 — runner
# =============================================================================
FROM nginx:1.27-alpine AS runner

# Copy custom nginx configuration.
# This config proxies /api/* to backend:8000 on the internal Docker network,
# solving the problem that the browser cannot reach unpublished port 8000.
COPY nginx.conf /etc/nginx/nginx.conf

# Copy only the compiled assets — no source, no node_modules, no secrets.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3000

# `daemon off` keeps nginx in the foreground so Docker can manage the process
CMD ["nginx", "-g", "daemon off;"]
