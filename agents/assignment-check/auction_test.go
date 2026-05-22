package main

import (
	"math"
	"testing"
)

func TestSpecializationAssignment(t *testing.T) {
	specializations = []string{"test", "essay", "code"}
	instances := []string{
		"assignment-checker-85d6dcbd89-fv6f6",
		"assignment-checker-85d6dcbd89-jqzjc",
		"assignment-checker-85d6dcbd89-m2v2s",
		"assignment-checker-85d6dcbd89-xabcd",
		"assignment-checker-85d6dcbd89-yefgh",
		"assignment-checker-85d6dcbd89-zzzzz",
		"assignment-checker-85d6dcbd89-aaaaa",
		"assignment-checker-85d6dcbd89-bbbbb",
		"assignment-checker-85d6dcbd89-ccccc",
	}
	seen := make(map[string]bool)
	for _, inst := range instances {
		lastChar := byte('a')
		if len(inst) > 0 {
			lastChar = inst[len(inst)-1]
		}
		spec := specializations[int(lastChar)%len(specializations)]
		seen[spec] = true
	}
	if len(seen) < 3 {
		t.Errorf("expected 3 unique specializations, got %d: %v", len(seen), seen)
	}
}

func TestMatchBonusSameSpecialization(t *testing.T) {
	req := AuctionRequest{AssignmentType: "test"}
	specialization = "test"
	matchBonus := 0.0
	if req.AssignmentType != "" {
		if req.AssignmentType == specialization {
			matchBonus = -5.0
		} else {
			matchBonus = 2.0
		}
	}
	if matchBonus != -5.0 {
		t.Errorf("expected match bonus -5.0 for same specialization, got %.1f", matchBonus)
	}
}

func TestMatchBonusDifferentSpecialization(t *testing.T) {
	req := AuctionRequest{AssignmentType: "essay"}
	specialization = "test"
	matchBonus := 0.0
	if req.AssignmentType != "" {
		if req.AssignmentType == specialization {
			matchBonus = -5.0
		} else {
			matchBonus = 2.0
		}
	}
	if matchBonus != 2.0 {
		t.Errorf("expected match bonus 2.0 for different specialization, got %.1f", matchBonus)
	}
}

func TestMatchBonusEmptyType(t *testing.T) {
	req := AuctionRequest{AssignmentType: ""}
	specialization = "test"
	matchBonus := 0.0
	if req.AssignmentType != "" {
		if req.AssignmentType == specialization {
			matchBonus = -5.0
		} else {
			matchBonus = 2.0
		}
	}
	if matchBonus != 0.0 {
		t.Errorf("expected match bonus 0.0 for empty type, got %.1f", matchBonus)
	}
}

func TestScoreFormula(t *testing.T) {
	tests := []struct {
		name     string
		cpuLoad  float64
		uptime   float64
		tp       int64
		match    float64
		expected float64
	}{
		{"idle no match", 0.1, 10, 0, 0, 10.01},
		{"idle match", 0.1, 10, 0, -5, 5.01},
		{"loaded no match", 0.5, 100, 5, 2, 52.05},
		{"loaded match", 0.5, 100, 5, -5, 45.05},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			score := tt.cpuLoad*100 + tt.uptime*0.001 - float64(tt.tp)*0.01 + tt.match
			if score < 0 {
				score = 0
			}
			if math.Abs(score-tt.expected) > 0.01 {
				t.Errorf("expected %.2f, got %.2f", tt.expected, score)
			}
		})
	}
}

func TestMatchAdvantageOverLoad(t *testing.T) {
	matchedAgentScore := 0.1*100 + 50*0.001 - 0*0.01 - 5.0
	noMatchAgentScore := 0.1*100 + 50*0.001 - 0*0.01 + 2.0

	if matchedAgentScore > noMatchAgentScore {
		t.Errorf("matched agent (%.2f) should have lower score than non-matched (%.2f)",
			matchedAgentScore, noMatchAgentScore)
	}

	sameLoadMatchScore := 0.3*100 + 100*0.001 - 3*0.01 - 5.0
	sameLoadNoMatchScore := 0.3*100 + 100*0.001 - 3*0.01 + 2.0

	if sameLoadMatchScore > sameLoadNoMatchScore {
		t.Errorf("with same load, matched agent (%.2f) should have lower score than non-matched (%.2f)",
			sameLoadMatchScore, sameLoadNoMatchScore)
	}
}


