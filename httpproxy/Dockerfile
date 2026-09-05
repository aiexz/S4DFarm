FROM golang:1.22-alpine AS build

WORKDIR /app
COPY go.* ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY proxy proxy
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o cacheproxy proxy/main.go

FROM alpine:3.20

COPY --from=build /app/cacheproxy /cacheproxy
RUN chmod +x /cacheproxy

CMD ["/cacheproxy"]


