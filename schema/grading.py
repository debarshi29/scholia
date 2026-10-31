"""Grading enums shared by the grader, DB and debrief UI."""

from enum import StrEnum


class OutcomeStatus(StrEnum):
    FOUND = "found"
    PARTIAL = "partial"
    MISSED = "missed"
    EXTRA = "extra"


class ClaimVerdict(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    UNVERIFIABLE = "unverifiable"
