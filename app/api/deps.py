"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import session_scope


def get_db() -> Session:
    generator = session_scope()
    session = next(generator)
    try:
        yield session
    except Exception:
        next(generator, None)
        raise
    else:
        next(generator, None)


SessionDep = Annotated[Session, Depends(get_db)]
