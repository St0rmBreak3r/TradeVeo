from __future__ import annotations

from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session


def db_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session
