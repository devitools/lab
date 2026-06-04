FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/floofy-sun ./

FROM scratch
COPY --from=build /out/floofy-sun /floofy-sun
EXPOSE 8080
ENTRYPOINT ["/floofy-sun"]
