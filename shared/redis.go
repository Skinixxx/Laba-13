package shared

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
)

type ProgressState struct {
	TasksProcessed  int     `json:"tasks_processed"`
	TotalCompletion float64 `json:"total_completion"`
	TotalAvgScore   float64 `json:"total_avg_score"`
	LastTrend       string  `json:"last_trend"`
	InstanceID      string  `json:"instance_id"`
}

func ConnectRedis(addr string) (*redis.Client, error) {
	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     "",
		DB:           0,
		ReadTimeout:  6 * time.Second,
		WriteTimeout: 6 * time.Second,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	log.Printf("Connected to Redis at %s", addr)
	return client, nil
}

func SaveStateAgent(client *redis.Client, key string, state *ProgressState) error {
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	data, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("marshal state: %w", err)
	}
	if err := client.Set(ctx, key, data, 0).Err(); err != nil {
		return fmt.Errorf("redis set: %w", err)
	}
	log.Printf("State saved [%s]: %d tasks processed, trend=%s",
		key, state.TasksProcessed, state.LastTrend)
	return nil
}

func LoadStateAgent(client *redis.Client, key string) (*ProgressState, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	data, err := client.Get(ctx, key).Bytes()
	if err != nil {
		if err == redis.Nil {
			return nil, nil
		}
		return nil, fmt.Errorf("redis get: %w", err)
	}
	var state ProgressState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("unmarshal state: %w", err)
	}
	log.Printf("State restored [%s]: %d tasks processed, trend=%s",
		key, state.TasksProcessed, state.LastTrend)
	return &state, nil
}
