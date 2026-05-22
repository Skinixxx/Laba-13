FROM golang:1.26-alpine AS builder
WORKDIR /app
COPY shared/ /app/shared/
COPY agents/assignment-check/ /app/agents/assignment-check/
WORKDIR /app/agents/assignment-check
RUN go build -o /agent .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
COPY --from=builder /agent .
CMD ["./agent"]
