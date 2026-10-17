# Web image. Build from the repository root:
#   docker build -f apps/web/Dockerfile --build-arg GURU_API_ORIGIN=https://<api-url> .
# GURU_API_ORIGIN is needed at BUILD time: next.config.ts bakes the /api proxy rewrite into the build.
FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

COPY apps/web apps/web
ARG GURU_API_ORIGIN
ENV GURU_API_ORIGIN=${GURU_API_ORIGIN}
RUN npm run build --workspace apps/web

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
COPY --from=build /app /app
EXPOSE 3000
# `next start --port 3000` (apps/web/package.json); tell Cloud Run the container port is 3000.
CMD ["npm", "run", "start", "--workspace", "apps/web"]
