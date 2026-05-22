package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/apollo/e-learning/shared"
	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	tp, err := shared.InitTracer("assignment-check")
	if err != nil {
		log.Fatalf("Failed to init tracer: %v", err)
	}
	defer shared.ShutdownTracer(tp)

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	log.Printf("Assignment Check Agent connected to NATS at %s", natsURL)

	_, err = nc.Subscribe("tasks.assignment.check", func(m *nats.Msg) {
		headers := make(map[string]string)
		for k, v := range m.Header {
			if len(v) > 0 {
				headers[k] = v[0]
			}
		}
		ctx := shared.ExtractTraceContext(context.Background(), headers)
		ctx, span := shared.Tracer().Start(ctx, "assignment-check.process",
			trace.WithAttributes(
				attribute.String("messaging.system", "nats"),
				attribute.String("messaging.destination", m.Subject),
			),
		)
		defer span.End()

		var task shared.Task
		if err := json.Unmarshal(m.Data, &task); err != nil {
			log.Printf("Failed to unmarshal task: %v", err)
			span.RecordError(err)
			publishError(ctx, nc, "", "failed to unmarshal task: "+err.Error())
			return
		}
		span.SetAttributes(
			attribute.String("task.id", task.ID),
			attribute.String("task.type", task.Type),
		)
		log.Printf("Received task %s (assignment: %s)", task.ID, extractAssignmentID(task.Payload))

		var req shared.AssignmentRequest
		if err := json.Unmarshal([]byte(task.Payload), &req); err != nil {
			log.Printf("Failed to unmarshal payload: %v", err)
			publishError(ctx, nc, task.ID, "invalid payload: "+err.Error())
			return
		}
		span.SetAttributes(
			attribute.String("assignment.id", req.AssignmentID),
			attribute.String("assignment.type", req.AssignmentType),
			attribute.String("user.id", req.UserID),
		)

		output := checkAssignment(req)
		span.SetAttributes(
			attribute.Bool("assignment.passed", output.Passed),
			attribute.Int("assignment.score", output.Score),
			attribute.Int("assignment.max_score", output.MaxScore),
		)

		result := shared.Result{
			TaskID:  task.ID,
			Success: true,
			Output:  mustJSON(output),
		}
		response, _ := json.Marshal(result)
		publishResult(ctx, nc, task.ID, response)
		log.Printf("Completed task %s — passed: %v, score: %d/%d",
			task.ID, output.Passed, output.Score, output.MaxScore)
	})
	if err != nil {
		log.Fatalf("Failed to subscribe: %v", err)
	}

	log.Println("Assignment Check Agent ready. Waiting for tasks...")
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	log.Println("Shutting down...")
}

func publishError(ctx context.Context, nc *nats.Conn, taskID, errMsg string) {
	result := shared.Result{
		TaskID:  taskID,
		Success: false,
		Error:   errMsg,
	}
	response, _ := json.Marshal(result)
	publishResult(ctx, nc, taskID, response)
}

func publishResult(ctx context.Context, nc *nats.Conn, taskID string, data []byte) {
	msg := nats.NewMsg("tasks.completed")
	msg.Data = data
	for k, v := range shared.InjectTraceContext(ctx) {
		msg.Header.Set(k, v)
	}
	nc.PublishMsg(msg)
}

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}
