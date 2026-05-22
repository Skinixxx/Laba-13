package main

import (
	"encoding/json"
	"log"
	"os"
	"os/signal"

	"github.com/apollo/e-learning/shared"
	"github.com/nats-io/nats.go"
)

func main() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	log.Printf("Course Recommendation Agent connected to NATS at %s", natsURL)

	_, err = nc.Subscribe("tasks.course.recommend", func(m *nats.Msg) {
		var task shared.Task
		if err := json.Unmarshal(m.Data, &task); err != nil {
			log.Printf("Failed to unmarshal task: %v", err)
			return
		}
		log.Printf("Received task %s", task.ID)

		var req shared.RecommendationRequest
		if err := json.Unmarshal([]byte(task.Payload), &req); err != nil {
			log.Printf("Failed to unmarshal payload: %v", err)
			publishError(nc, task.ID, "invalid payload: "+err.Error())
			return
		}

		output := recommendCourses(req)
		result := shared.Result{
			TaskID:  task.ID,
			Success: true,
			Output:  mustJSON(output),
		}
		response, _ := json.Marshal(result)
		nc.Publish("tasks.completed", response)
		log.Printf("Completed task %s with %d recommendations", task.ID, len(output.Recommendations))
	})
	if err != nil {
		log.Fatalf("Failed to subscribe: %v", err)
	}

	log.Println("Course Recommendation Agent ready. Waiting for tasks...")

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)
	<-sig
	log.Println("Shutting down...")
}

func publishError(nc *nats.Conn, taskID, errMsg string) {
	result := shared.Result{
		TaskID:  taskID,
		Success: false,
		Error:   errMsg,
	}
	response, _ := json.Marshal(result)
	nc.Publish("tasks.completed", response)
}

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}
