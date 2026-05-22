package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/apollo/e-learning/shared"
	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type AgentBid struct {
	AgentID        string  `json:"agent_id"`
	CPULoad        float64 `json:"cpu_load"`
	TasksProcessed int64   `json:"tasks_processed"`
	UptimeSeconds  int     `json:"uptime_seconds"`
	Goroutines     int     `json:"goroutines"`
	Specialization string  `json:"specialization"`
	MatchBonus     float64 `json:"match_bonus"`
	Score          float64 `json:"score"`
}

type AuctionRequest struct {
	AuctionID       string `json:"auction_id"`
	AssignmentType string `json:"assignment_type,omitempty"`
}

var (
	startTime       = time.Now()
	tasksProcessed  atomic.Int64
	specializations = []string{"test", "essay", "code"}
	specialization  string
)

func main() {
	tp, err := shared.InitTracer("assignment-check")
	if err != nil {
		log.Fatalf("Failed to init tracer: %v", err)
	}
	defer shared.ShutdownTracer(tp)

	instanceID, _ := os.Hostname()
	lastChar := byte('a')
	if len(instanceID) > 0 {
		lastChar = instanceID[len(instanceID)-1]
	}
	specialization = specializations[int(lastChar)%len(specializations)]
	log.Printf("Assignment Check Agent starting (instance: %s, specialization: %s)", instanceID, specialization)

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	log.Printf("Connected to NATS at %s", natsURL)

	taskHandler := func(m *nats.Msg) {
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
		tasksProcessed.Add(1)
		log.Printf("Completed task %s — passed: %v, score: %d/%d",
			task.ID, output.Passed, output.Score, output.MaxScore)
	}

	_, err = nc.Subscribe("tasks.assignment.check", taskHandler)
	if err != nil {
		log.Fatalf("Failed to subscribe: %v", err)
	}

	_, err = nc.Subscribe("tasks.assignment.check.direct."+instanceID, taskHandler)
	if err != nil {
		log.Fatalf("Failed to subscribe to direct subject: %v", err)
	}

	_, err = nc.Subscribe("tasks.auction.check", func(m *nats.Msg) {
		var req AuctionRequest
		if err := json.Unmarshal(m.Data, &req); err != nil {
			log.Printf("Failed to unmarshal auction request: %v", err)
			return
		}
		if req.AuctionID == "" {
			return
		}

		tp := tasksProcessed.Load()
		uptime := time.Since(startTime).Seconds()
		goros := runtime.NumGoroutine()

		cpuLoad := float64(goros) / 20.0
		if cpuLoad > 1.0 {
			cpuLoad = 1.0
		}
		if tp == 0 {
			cpuLoad = 0.1
		}

		matchBonus := 0.0
		if req.AssignmentType != "" {
			if req.AssignmentType == specialization {
				matchBonus = -5.0
			} else {
				matchBonus = 2.0
			}
		}

		score := cpuLoad*100 + uptime*0.001 - float64(tp)*0.01 + matchBonus
		if score < 0 {
			score = 0
		}

		bid := AgentBid{
			AgentID:        instanceID,
			CPULoad:        cpuLoad,
			TasksProcessed: tp,
			UptimeSeconds:  int(uptime),
			Goroutines:     goros,
			Specialization: specialization,
			MatchBonus:     matchBonus,
			Score:          score,
		}
		bidData, _ := json.Marshal(bid)

		bidSubject := "tasks.auction.bid." + req.AuctionID
		if err := nc.Publish(bidSubject, bidData); err != nil {
			log.Printf("Failed to publish bid: %v", err)
			return
		}
		log.Printf("Auction %s: bid placed (score=%.2f, cpu=%.2f, tasks=%d, spec=%s, match=%.1f)",
			req.AuctionID[:8], bid.Score, bid.CPULoad, tp, specialization, matchBonus)
	})
	if err != nil {
		log.Fatalf("Failed to subscribe to auction: %v", err)
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
