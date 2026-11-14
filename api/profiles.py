"""Local profiles: separate progress and defaults on one machine. There is no login.

The browser names its profile in the ``X-Profile`` header; a request without one is the
default profile, so everything that predates profiles keeps working. A profile owns its
sessions (``sessions.profile_id``), its category stats and its session defaults. Problems
and the answer key are shared. Anyone at the keyboard can switch profiles: this separates
progress, it does not protect it.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import (
    DEFAULT_PROFILE,
    ClaimAuditRow,
    FindingRow,
    FixResultRow,
    OutcomeRow,
    PatchRow,
    ProfileRow,
    ProfileStatRow,
    QueryRow,
    SessionRow,
    as_utc,
    get_db,
)
from api.errors import ApiError
from schema import AssistantMode

router = APIRouter(prefix="/api", tags=["profiles"])

Db = Annotated[AsyncSession, Depends(get_db)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
MAX_PROFILES = 20


async def current_profile(db: Db, x_profile: Annotated[str | None, Header()] = None) -> ProfileRow:
    """The profile named by the ``X-Profile`` header (the default one without it)."""
    profile = await db.get(ProfileRow, x_profile or DEFAULT_PROFILE)
    if profile is None:
        raise ApiError(404, "profile_not_found", f"No profile {x_profile!r}")
    return profile


Profile = Annotated[ProfileRow, Depends(current_profile)]


class ProfileView(BaseModel):
    id: str
    name: str
    created_at: datetime
    is_default: bool
    default_mode: AssistantMode | None
    default_ctx_cap: int | None
    default_q_budget: int | None
    sessions: int
    graded: int
    attempts: int
    """Key bugs attempted across graded sessions."""
    misses: int


class ProfileCreate(BaseModel):
    name: Name
    default_mode: AssistantMode | None = None
    default_ctx_cap: int | None = Field(default=None, ge=256, le=32768)
    default_q_budget: int | None = Field(default=None, ge=0, le=200)


class ProfileUpdate(BaseModel):
    """Only the fields that are sent change; send ``null`` to go back to the server default."""

    name: Name | None = None
    default_mode: AssistantMode | None = None
    default_ctx_cap: int | None = Field(default=None, ge=256, le=32768)
    default_q_budget: int | None = Field(default=None, ge=0, le=200)


async def _view(db: AsyncSession, p: ProfileRow) -> ProfileView:
    sessions, graded = (
        await db.exec(
            select(func.count(), func.count(col(SessionRow.graded_at))).where(
                SessionRow.profile_id == p.id
            )
        )
    ).one()
    attempts, misses = (
        await db.exec(
            select(
                func.coalesce(func.sum(ProfileStatRow.attempts), 0),
                func.coalesce(func.sum(ProfileStatRow.misses), 0),
            ).where(ProfileStatRow.profile_id == p.id)
        )
    ).one()
    return ProfileView(
        id=p.id,
        name=p.name,
        created_at=as_utc(p.created_at),
        is_default=p.id == DEFAULT_PROFILE,
        default_mode=p.default_mode,
        default_ctx_cap=p.default_ctx_cap,
        default_q_budget=p.default_q_budget,
        sessions=sessions,
        graded=graded,
        attempts=int(attempts),
        misses=int(misses),
    )


async def _get(db: AsyncSession, profile_id: str) -> ProfileRow:
    profile = await db.get(ProfileRow, profile_id)
    if profile is None:
        raise ApiError(404, "profile_not_found", f"No profile {profile_id!r}")
    return profile


@router.get("/profiles", response_model=list[ProfileView])
async def list_profiles(db: Db) -> list[ProfileView]:
    rows = (await db.exec(select(ProfileRow).order_by(col(ProfileRow.created_at)))).all()
    return [await _view(db, p) for p in rows]


@router.post("/profiles", response_model=ProfileView, status_code=201)
async def create_profile(req: ProfileCreate, db: Db) -> ProfileView:
    rows = (await db.exec(select(ProfileRow))).all()
    if len(rows) >= MAX_PROFILES:
        raise ApiError(409, "too_many_profiles", f"At most {MAX_PROFILES} profiles")
    if any(r.name.casefold() == req.name.casefold() for r in rows):
        raise ApiError(409, "profile_name_taken", f"A profile named {req.name!r} exists")
    profile = ProfileRow(id=uuid.uuid4().hex[:8], **req.model_dump())
    db.add(profile)
    await db.commit()
    return await _view(db, profile)


@router.get("/profiles/{profile_id}", response_model=ProfileView)
async def get_profile(profile_id: str, db: Db) -> ProfileView:
    return await _view(db, await _get(db, profile_id))


@router.patch("/profiles/{profile_id}", response_model=ProfileView)
async def update_profile(profile_id: str, req: ProfileUpdate, db: Db) -> ProfileView:
    profile = await _get(db, profile_id)
    changes = req.model_dump(exclude_unset=True)
    name = changes.get("name")
    if name is not None:
        others = (await db.exec(select(ProfileRow).where(ProfileRow.id != profile.id))).all()
        if any(o.name.casefold() == name.casefold() for o in others):
            raise ApiError(409, "profile_name_taken", f"A profile named {name!r} exists")
    for key, value in changes.items():
        if key == "name" and value is None:
            continue  # a profile always has a name
        setattr(profile, key, value)
    db.add(profile)
    await db.commit()
    return await _view(db, profile)


@router.post("/profiles/{profile_id}/reset-stats", response_model=ProfileView)
async def reset_stats(profile_id: str, db: Db) -> ProfileView:
    """Forget the weak-spot counts, so the picker starts fresh. Sessions are kept."""
    profile = await _get(db, profile_id)
    await db.exec(delete(ProfileStatRow).where(col(ProfileStatRow.profile_id) == profile.id))
    await db.commit()
    return await _view(db, profile)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: Db) -> None:
    """Delete a profile with its sessions, assistant logs, reports and stats."""
    profile = await _get(db, profile_id)
    if profile.id == DEFAULT_PROFILE:
        raise ApiError(409, "default_profile", "The default profile cannot be deleted")
    ids = list(
        (await db.exec(select(SessionRow.id).where(SessionRow.profile_id == profile.id))).all()
    )
    if ids:
        queries = select(QueryRow.id).where(col(QueryRow.session_id).in_(ids))
        await db.exec(delete(ClaimAuditRow).where(col(ClaimAuditRow.query_id).in_(queries)))
        # Children before parents: outcomes point at findings, which point at sessions.
        for table in (OutcomeRow, FixResultRow, PatchRow, FindingRow, QueryRow):
            await db.exec(delete(table).where(col(table.session_id).in_(ids)))
        await db.exec(delete(SessionRow).where(col(SessionRow.id).in_(ids)))
    await db.exec(delete(ProfileStatRow).where(col(ProfileStatRow.profile_id) == profile.id))
    await db.delete(profile)
    await db.commit()
