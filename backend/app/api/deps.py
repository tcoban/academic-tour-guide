from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_session


def session_dep() -> Generator[Session, None, None]:
    yield from get_session()

