FROM golang:1.26-alpine AS builder
WORKDIR /app
COPY shared/ /app/shared/
COPY agents/progress-analysis/ /app/agents/progress-analysis/
WORKDIR /app/agents/progress-analysis
RUN go build -o /agent .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
COPY --from=builder /agent .
CMD ["./agent"]
