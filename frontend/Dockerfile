# Frontend image for running the whole app locally with Docker.
# (In production the frontend is deployed by Vercel, not this image.)
#
# Stage 1: build the React app into static files.
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Vite bakes this URL into the built files, so it must be set at build time.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: serve the built files with nginx (a small, fast web server).
# Node and node_modules are not included in this final image.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
