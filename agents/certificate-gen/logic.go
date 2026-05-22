package main

import (
	"fmt"
	"time"

	"github.com/apollo/e-learning/shared"
	"github.com/google/uuid"
)

func generateCertificate(req shared.CertificateRequest) shared.CertificateOutput {
	if !req.RequirementsMet {
		grade := req.Grade
		if grade == "" {
			grade = "F"
		}
		return shared.CertificateOutput{
			CertificateID:  "",
			UserID:         req.UserID,
			UserName:       req.UserName,
			CourseID:       req.CourseID,
			CourseName:     req.CourseName,
			Grade:          grade,
			IssuedAt:       time.Now(),
			ValidUntil:     time.Now(),
			CertificateURL: "",
		}
	}

	grade := req.Grade
	if grade == "" {
		grade = "B"
	}

	certID := uuid.New().String()
	now := time.Now()

	return shared.CertificateOutput{
		CertificateID:  certID,
		UserID:         req.UserID,
		UserName:       req.UserName,
		CourseID:       req.CourseID,
		CourseName:     req.CourseName,
		Grade:          grade,
		IssuedAt:       now,
		ValidUntil:     now.AddDate(3, 0, 0),
		CertificateURL: fmt.Sprintf("/certificates/%s.pdf", certID),
	}
}
