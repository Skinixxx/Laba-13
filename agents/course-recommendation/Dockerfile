FROM golang:1.26-alpine AS builder
WORKDIR /app
COPY shared/ /app/shared/
COPY agents/course-recommendation/ /app/agents/course-recommendation/
WORKDIR /app/agents/course-recommendation
RUN go build -o /agent .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
COPY --from=builder /agent .
CMD ["./agent"]
