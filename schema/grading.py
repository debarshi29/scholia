"""Grading enums shared by the grader, DB and debrief UI."""

from enum import StrEnum


class OutcomeStatus(StrEnum):
    FOUND = "found"
    PARTIAL = "partial"
    MISSED = "missed"
    EXTRA = "extra"
    UNGRADED = "ungraded"
    """Matched a bug by location, but the judge produced no valid score. Never guessed."""


class ClaimVerdict(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    UNVERIFIABLE = "unverifiable"
