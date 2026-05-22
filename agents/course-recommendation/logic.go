package main

import (
	"strings"

	"github.com/apollo/e-learning/shared"
)

type course struct {
	ID       string
	Title    string
	Tags     []string
	Level    string
	Rating   float64
	Duration int
}

var courseCatalog = []course{
	{ID: "c-001", Title: "Python для начинающих", Tags: []string{"python", "programming"}, Level: "beginner", Rating: 4.5, Duration: 20},
	{ID: "c-002", Title: "SQL и базы данных", Tags: []string{"sql", "databases"}, Level: "beginner", Rating: 4.3, Duration: 15},
	{ID: "c-003", Title: "Java Core", Tags: []string{"java", "programming", "oop"}, Level: "intermediate", Rating: 4.6, Duration: 30},
	{ID: "c-004", Title: "Веб-разработка на JavaScript", Tags: []string{"javascript", "web", "frontend"}, Level: "intermediate", Rating: 4.4, Duration: 25},
	{ID: "c-005", Title: "Машинное обучение с Python", Tags: []string{"python", "machine learning", "data science"}, Level: "advanced", Rating: 4.8, Duration: 40},
	{ID: "c-006", Title: "React.js", Tags: []string{"javascript", "react", "frontend"}, Level: "intermediate", Rating: 4.7, Duration: 20},
	{ID: "c-007", Title: "Go для микросервисов", Tags: []string{"go", "microservices", "backend"}, Level: "advanced", Rating: 4.5, Duration: 35},
	{ID: "c-008", Title: "Продвинутый Python", Tags: []string{"python", "advanced", "oop"}, Level: "advanced", Rating: 4.6, Duration: 25},
	{ID: "c-009", Title: "Docker и Kubernetes", Tags: []string{"docker", "kubernetes", "devops"}, Level: "intermediate", Rating: 4.9, Duration: 20},
	{ID: "c-010", Title: "Основы алгоритмов", Tags: []string{"algorithms", "data structures"}, Level: "intermediate", Rating: 4.2, Duration: 30},
}

var levelOrder = map[string]int{"beginner": 1, "intermediate": 2, "advanced": 3}

func recommendCourses(req shared.RecommendationRequest) shared.RecommendationOutput {
	completedIDs := make(map[string]bool)
	for _, h := range req.History {
		if h.Completed {
			completedIDs[h.CourseID] = true
		}
	}

	type scored struct {
		course
		score int
		reason string
	}

	var scoredCourses []scored
	userLevel := levelOrder[req.Profile.SkillLevel]
	interestSet := make(map[string]bool)
	for _, i := range req.Profile.Interests {
		interestSet[strings.ToLower(i)] = true
	}

	for _, c := range courseCatalog {
		if completedIDs[c.ID] {
			continue
		}

		var matchScore int
		var reasons []string

		for _, tag := range c.Tags {
			for interest := range interestSet {
				if strings.Contains(strings.ToLower(tag), interest) || strings.Contains(interest, strings.ToLower(tag)) {
					matchScore += 40
					reasons = append(reasons, "Совпадает с вашими интересами")
					goto interestDone
				}
			}
		}
	interestDone:

		courseLevel := levelOrder[c.Level]
		levelDiff := courseLevel - userLevel
		if levelDiff == 0 {
			matchScore += 30
			reasons = append(reasons, "Идеально подходит вашему уровню")
		} else if levelDiff == 1 {
			matchScore += 15
			reasons = append(reasons, "Немного выше вашего уровня")
		} else if levelDiff == -1 {
			matchScore += 10
		}

		matchScore += int(c.Rating * 5)
		if c.Rating >= 4.5 {
			reasons = append(reasons, "Высокий рейтинг курса")
		}

		courseLevelMatch := strings.ToLower(c.Level) == req.Profile.SkillLevel
		if courseLevelMatch {
			matchScore += 10
		}

		if len(reasons) == 0 {
			reasons = append(reasons, "Рекомендуем для расширения навыков")
		}

		scoredCourses = append(scoredCourses, scored{c, matchScore, reasons[0]})
	}

	for i := 0; i < len(scoredCourses); i++ {
		for j := i + 1; j < len(scoredCourses); j++ {
			if scoredCourses[j].score > scoredCourses[i].score {
				scoredCourses[i], scoredCourses[j] = scoredCourses[j], scoredCourses[i]
			}
		}
	}

	topN := 5
	if len(scoredCourses) < topN {
		topN = len(scoredCourses)
	}
	scoredCourses = scoredCourses[:topN]

	recs := make([]shared.Recommendation, topN)
	for i, s := range scoredCourses {
		recs[i] = shared.Recommendation{
			CourseID: s.ID,
			Title:    s.Title,
			Score:    s.score,
			Reason:   s.reason,
		}
	}

	return shared.RecommendationOutput{
		UserID:          req.UserID,
		Recommendations: recs,
	}
}
