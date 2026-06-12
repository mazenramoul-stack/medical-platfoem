# syntax=docker/dockerfile:1
#
# Frontend image — dev server only. For production builds use a multi-stage
# Dockerfile that runs `npm run build` and serves the dist/ folder with nginx.

FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

# Vite must bind to 0.0.0.0 inside the container so the host port mapping works.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
