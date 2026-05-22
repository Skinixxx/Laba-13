module github.com/apollo/e-learning/agents/certificate-gen

go 1.26.2

require (
	github.com/apollo/e-learning/shared v0.0.0
	github.com/google/uuid v1.6.0
	github.com/nats-io/nats.go v1.41.1
)

require (
	github.com/klauspost/compress v1.18.0 // indirect
	github.com/nats-io/nkeys v0.4.9 // indirect
	github.com/nats-io/nuid v1.0.1 // indirect
	golang.org/x/crypto v0.31.0 // indirect
	golang.org/x/sys v0.28.0 // indirect
)

replace github.com/apollo/e-learning/shared => ../../shared
