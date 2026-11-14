"""Single source of truth for types shared by corpus, api and web."""

from schema.answer import AnswerKey, Bug, CategorySource, DesignNote, Severity
from schema.grading import ClaimVerdict, OutcomeStatus
from schema.problem import ProblemMeta, Source
from schema.report import FilePatch, Finding, Report
from schema.session import AssistantMode
from schema.taxonomy import BugCategory

__all__ = [
    "AnswerKey",
    "AssistantMode",
    "Bug",
    "BugCategory",
    "CategorySource",
    "ClaimVerdict",
    "DesignNote",
    "FilePatch",
    "Finding",
    "OutcomeStatus",
    "ProblemMeta",
    "Report",
    "Severity",
    "Source",
]
