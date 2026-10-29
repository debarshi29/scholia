"""Bug taxonomy. Changing members is a data migration: ask the owner first."""

from enum import StrEnum


class BugCategory(StrEnum):
    LOGIC = "logic"
    BOUNDARY = "boundary"
    NULL_EMPTY = "null_empty"
    SHARED_MUTABLE_STATE = "shared_mutable_state"
    CONCURRENCY = "concurrency"
    RESOURCE_LEAK = "resource_leak"
    ERROR_HANDLING = "error_handling"
    COMPLEXITY = "complexity"
