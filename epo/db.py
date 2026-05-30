"""
EPO Local Database -- SQLite for CLI usage.

Provides a synchronous SQLAlchemy session for local operation
without a server. Stores data in ~/.claude/epo.db.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from epo.models import EPOBase

DEFAULT_DB_PATH = Path.home() / ".claude" / "epo.db"


def get_engine(db_path: Path | None = None):
    """Create a SQLite engine."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)


def init_db(db_path: Path | None = None):
    """Create all EPO tables in the local SQLite database."""
    engine = get_engine(db_path)
    EPOBase.metadata.create_all(engine)
    return engine


def get_session(db_path: Path | None = None) -> Session:
    """Get a synchronous SQLAlchemy session."""
    engine = init_db(db_path)
    return sessionmaker(bind=engine)()
