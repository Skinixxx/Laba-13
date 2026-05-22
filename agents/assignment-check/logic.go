package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/apollo/e-learning/shared"
)

type answerKey struct {
	Choices []string `json:"choices"`
}

type assignmentMeta struct {
	AnswerKey answerKey `json:"answer_key"`
	Keywords  []string  `json:"keywords"`
	MaxScore  int       `json:"max_score"`
	TestCount int       `json:"test_count"`
}

var assignmentDB = map[string]assignmentMeta{
	"a-042": {AnswerKey: answerKey{Choices: []string{"b", "c", "a", "d", "b"}}, MaxScore: 100, TestCount: 5},
	"a-043": {AnswerKey: answerKey{Choices: []string{"true", "false", "true", "true"}}, MaxScore: 100, TestCount: 4},
	"a-044": {Keywords: []string{"функция", "аргумент", "возврат", "рекурсия"}, MaxScore: 100},
	"a-045": {Keywords: []string{"класс", "объект", "наследование", "полиморфизм"}, MaxScore: 100, TestCount: 3},
}

func checkAssignment(req shared.AssignmentRequest) shared.AssignmentOutput {
	meta, exists := assignmentDB[req.AssignmentID]
	if !exists {
		meta = assignmentMeta{MaxScore: 100, TestCount: 3}
	}

	output := shared.AssignmentOutput{
		AssignmentID: req.AssignmentID,
		UserID:       req.UserID,
		MaxScore:     meta.MaxScore,
		CheckedAt:    time.Now(),
	}

	switch req.AssignmentType {
	case "test":
		checkTest(req, meta, &output)
	case "code":
		checkCode(req, meta, &output)
	case "essay":
		checkEssay(req, meta, &output)
	default:
		output.Score = 0
		output.Passed = false
		output.Feedback = "Неизвестный тип задания: " + req.AssignmentType
	}

	return output
}

func checkTest(req shared.AssignmentRequest, meta assignmentMeta, output *shared.AssignmentOutput) {
	correct := 0
	total := len(meta.AnswerKey.Choices)
	if total == 0 {
		total = meta.TestCount
	}

	wrongIndices := []int{}
	for i, expected := range meta.AnswerKey.Choices {
		if i < len(req.Answer.Choices) {
			if strings.EqualFold(req.Answer.Choices[i], expected) {
				correct++
			} else {
				wrongIndices = append(wrongIndices, i+1)
			}
		} else {
			wrongIndices = append(wrongIndices, i+1)
		}
	}

	if total == 0 {
		output.Score = 0
		output.Passed = false
		output.Feedback = "Нет тестов для проверки"
		return
	}
	output.Score = (correct * output.MaxScore) / total
	output.Passed = output.Score >= 80

	if len(wrongIndices) == 0 {
		output.Feedback = "Все ответы верны! Отличная работа."
	} else {
		output.Feedback = fmt.Sprintf("Верно: %d/%d. Ошибки в вопросах: %v", correct, total, wrongIndices)
	}
}

func checkCode(req shared.AssignmentRequest, meta assignmentMeta, output *shared.AssignmentOutput) {
	testCount := meta.TestCount
	if testCount == 0 {
		testCount = 5
	}

	passedTests := 0
	codeLen := len(strings.TrimSpace(req.Answer.Code))
	if codeLen > 0 {
		passedTests = testCount
		if codeLen < 10 {
			passedTests = testCount / 2
		} else if codeLen < 50 {
			passedTests = testCount * 3 / 4
		}
	}

	output.Score = (passedTests * output.MaxScore) / testCount
	output.Passed = output.Score >= 80

	if passedTests == testCount {
		output.Feedback = "Все тесты пройдены. Код корректный."
	} else {
		output.Feedback = fmt.Sprintf("Пройдено тестов: %d/%d. Проверьте логику кода.", passedTests, testCount)
	}
}

func checkEssay(req shared.AssignmentRequest, meta assignmentMeta, output *shared.AssignmentOutput) {
	text := strings.TrimSpace(req.Answer.Essay)
	wordCount := len(strings.Fields(text))

	if wordCount < 20 {
		output.Score = 20
		output.Passed = false
		output.Feedback = "Эссе слишком короткое. Минимум 20 слов."
		return
	}

	keywordMatches := 0
	for _, kw := range meta.Keywords {
		if strings.Contains(strings.ToLower(text), strings.ToLower(kw)) {
			keywordMatches++
		}
	}

	baseScore := 50
	if wordCount >= 100 {
		baseScore += 20
	}
	keywordScore := 0
	if len(meta.Keywords) > 0 {
		keywordScore = (keywordMatches * 30) / len(meta.Keywords)
	}

	output.Score = baseScore + keywordScore
	if output.Score > output.MaxScore {
		output.Score = output.MaxScore
	}
	output.Passed = output.Score >= 70

	output.Feedback = fmt.Sprintf("Слов: %d, раскрыто тем: %d/%d. Оценка: %d/100",
		wordCount, keywordMatches, len(meta.Keywords), output.Score)
}

func extractAssignmentID(payload string) string {
	var req shared.AssignmentRequest
	if err := json.Unmarshal([]byte(payload), &req); err == nil {
		return req.AssignmentID
	}
	return "unknown"
}
