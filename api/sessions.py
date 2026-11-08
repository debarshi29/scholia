"""Session API. M3 adds the assistant route; the rest of the session API lands in M2."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import SessionRow, get_db
from api.deps import get_proxy
from api.proxy import AskRequest, AskResult, Proxy

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/{session_id}/ask", response_model=AskResult)
async def ask(
    session_id: str,
    req: AskRequest,
    db: Db,
    proxy: Annotated[Proxy, Depends(get_proxy)],
) -> AskResult:
    """Ask the assistant. Refusals are 200 responses with ``refused: true``."""
    session = await db.get(SessionRow, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.submitted_at is not None:
        raise HTTPException(409, "Session already submitted")
    return await proxy.ask(db, session, req)
