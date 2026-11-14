"""Category tracker: per-category attempts and misses, which weight the problem picker."""

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import ProfileStatRow, SessionRow, utcnow
from schema import BugCategory, OutcomeStatus


async def apply_session(
    db: AsyncSession, session: SessionRow, bugs: list[tuple[BugCategory, OutcomeStatus]]
) -> list[dict[str, Any]]:
    """Add this session's key bugs to its profile's ``profile_stats`` exactly once.

    Each key bug is one attempt in its category; a ``missed`` bug is also one miss.
    The before/after numbers are stored on the session, which doubles as the
    "already applied" marker, so regrading never counts a session twice.
    The caller commits.
    """
    if session.stats_delta is not None:
        return session.stats_delta
    attempts: dict[BugCategory, int] = {}
    misses: dict[BugCategory, int] = {}
    for category, status in bugs:
        attempts[category] = attempts.get(category, 0) + 1
        misses[category] = misses.get(category, 0) + (status is OutcomeStatus.MISSED)
    delta: list[dict[str, Any]] = []
    for category in sorted(attempts, key=lambda c: c.value):
        row = await db.get(ProfileStatRow, (session.profile_id, category))
        if row is None:
            row = ProfileStatRow(profile_id=session.profile_id, category=category)
        before = (row.attempts, row.misses)
        row.attempts += attempts[category]
        row.misses += misses[category]
        row.updated_at = utcnow()
        db.add(row)
        delta.append(
            {
                "category": category.value,
                "attempts_before": before[0],
                "misses_before": before[1],
                "attempts_after": row.attempts,
                "misses_after": row.misses,
            }
        )
    session.stats_delta = delta
    db.add(session)
    return delta
