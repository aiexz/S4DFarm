FROM node:20-slim AS front-base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /app

COPY front/package.json front/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

FROM front-base AS front-build
COPY front .
RUN pnpm run build

FROM nginx:1.21.0-alpine

COPY ./docker/front/proxy_params /etc/nginx/proxy_params
COPY ./docker/front/app.conf /etc/nginx/conf.d/default.conf
COPY --from=front-build /app/dist /front
