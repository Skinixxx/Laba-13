package shared

import "time"

type Task struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Payload string `json:"payload"`
}

type Result struct {
	TaskID  string `json:"task_id"`
	Success bool   `json:"success"`
	Output  string `json:"output"`
	Error   string `json:"error,omitempty"`
}

// --- Course Recommendation ---

type UserProfile struct {
	Interests    []string `json:"interests"`
	SkillLevel   string   `json:"skill_level"`
	PreferredLang string  `json:"preferred_lang"`
}

type CourseHistory struct {
	CourseID  string `json:"course_id"`
	Title     string `json:"title"`
	Completed bool   `json:"completed"`
	Score     int    `json:"score"`
}

type RecommendationRequest struct {
	UserID  string          `json:"user_id"`
	Profile UserProfile     `json:"profile"`
	History []CourseHistory `json:"history"`
}

type Recommendation struct {
	CourseID string `json:"course_id"`
	Title    string `json:"title"`
	Score    int    `json:"score"`
	Reason   string `json:"reason"`
}

type RecommendationOutput struct {
	UserID          string           `json:"user_id"`
	Recommendations []Recommendation `json:"recommendations"`
}

// --- Assignment Check ---

type AssignmentRequest struct {
	AssignmentID   string `json:"assignment_id"`
	UserID         string `json:"user_id"`
	CourseID       string `json:"course_id"`
	AssignmentType string `json:"assignment_type"`
	Answer         Answer `json:"answer"`
}

type Answer struct {
	Choices []string `json:"choices"`
	Code    string   `json:"code"`
	Essay   string   `json:"essay"`
}

type AssignmentOutput struct {
	AssignmentID string    `json:"assignment_id"`
	UserID       string    `json:"user_id"`
	Passed       bool      `json:"passed"`
	Score        int       `json:"score"`
	MaxScore     int       `json:"max_score"`
	Feedback     string    `json:"feedback"`
	CheckedAt    time.Time `json:"checked_at"`
}

// --- Progress Analysis ---

type ActivityEntry struct {
	Date      string `json:"date"`
	Type      string `json:"type"`
	Title     string `json:"title"`
	Score     int    `json:"score,omitempty"`
	Completed bool   `json:"completed"`
}

type ProgressRequest struct {
	UserID      string          `json:"user_id"`
	CourseID    string          `json:"course_id"`
	ActivityLog []ActivityEntry `json:"activity_log"`
}

type WeakTopic struct {
	Title      string `json:"title"`
	Score      int    `json:"score"`
	Suggestion string `json:"suggestion"`
}

type ProgressOutput struct {
	UserID         string      `json:"user_id"`
	CourseID       string      `json:"course_id"`
	CompletionPct  float64     `json:"completion_pct"`
	AvgScore       float64     `json:"avg_score"`
	Trend          string      `json:"trend"`
	WeakTopics     []WeakTopic `json:"weak_topics"`
	Recommendations []string   `json:"recommendations"`
}

// --- Certificate Generation ---

type CertificateRequest struct {
	UserID          string `json:"user_id"`
	UserName        string `json:"user_name"`
	CourseID        string `json:"course_id"`
	CourseName      string `json:"course_name"`
	CompletionDate  string `json:"completion_date"`
	Grade           string `json:"grade"`
	Credits         int    `json:"credits"`
	RequirementsMet bool   `json:"requirements_met"`
}

type CertificateOutput struct {
	CertificateID  string    `json:"certificate_id"`
	UserID         string    `json:"user_id"`
	UserName       string    `json:"user_name"`
	CourseID       string    `json:"course_id"`
	CourseName     string    `json:"course_name"`
	Grade          string    `json:"grade"`
	IssuedAt       time.Time `json:"issued_at"`
	ValidUntil     time.Time `json:"valid_until"`
	CertificateURL string    `json:"certificate_url"`
}
