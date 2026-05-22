package main

import (
	"math"

	"github.com/apollo/e-learning/shared"
)

func analyzeProgress(req shared.ProgressRequest) shared.ProgressOutput {
	output := shared.ProgressOutput{
		UserID:   req.UserID,
		CourseID: req.CourseID,
	}

	log := req.ActivityLog
	if len(log) == 0 {
		output.CompletionPct = 0
		output.AvgScore = 0
		output.Trend = "no_data"
		output.Recommendations = []string{"Начните изучение курса"}
		return output
	}

	completed := 0
	total := len(log)
	for _, entry := range log {
		if entry.Completed {
			completed++
		}
	}
	output.CompletionPct = math.Round(float64(completed)*10000/float64(total)) / 100

	var scores []int
	var scoreEntries []shared.ActivityEntry
	for _, entry := range log {
		if entry.Type == "assignment" && entry.Completed {
			scores = append(scores, entry.Score)
			scoreEntries = append(scoreEntries, entry)
		}
	}

	if len(scores) > 0 {
		sum := 0
		for _, s := range scores {
			sum += s
		}
		output.AvgScore = math.Round(float64(sum)*100/float64(len(scores))) / 100

		if len(scores) >= 2 {
			improving := true
			declining := true
			for i := 1; i < len(scores); i++ {
				if scores[i] < scores[i-1] {
					improving = false
				}
				if scores[i] > scores[i-1] {
					declining = false
				}
			}
			if improving && declining {
				output.Trend = "stable"
			} else if improving {
				output.Trend = "improving"
			} else if declining {
				output.Trend = "declining"
			} else {
				output.Trend = "stable"
			}
		} else {
			output.Trend = "stable"
		}

		for _, entry := range scoreEntries {
			if entry.Score < 60 {
				output.WeakTopics = append(output.WeakTopics, shared.WeakTopic{
					Title:      entry.Title,
					Score:      entry.Score,
					Suggestion: "Повторите тему: " + entry.Title,
				})
			}
		}

		if output.Trend == "declining" {
			output.Recommendations = append(output.Recommendations,
				"Ваши результаты снижаются. Рекомендуем повторить пройденный материал.")
		}
		if len(output.WeakTopics) > 0 {
			for _, wt := range output.WeakTopics {
				output.Recommendations = append(output.Recommendations, wt.Suggestion)
			}
		} else if output.Trend == "improving" {
			output.Recommendations = append(output.Recommendations,
				"Отличный прогресс! Продолжайте в том же духе.")
		}
	} else {
		output.AvgScore = 0
		output.Trend = "no_assignments"
		output.Recommendations = append(output.Recommendations,
			"Пройдите хотя бы одно задание для анализа прогресса.")
	}

	if output.CompletionPct < 50 && len(output.Recommendations) == 0 {
		output.Recommendations = append(output.Recommendations,
			"Вы прошли менее 50% курса. Продолжайте обучение.")
	}

	return output
}
