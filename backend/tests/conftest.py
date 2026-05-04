from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

# TestClient runs the FastAPI lifespan before dependency overrides are active.
# Keep that startup path away from the developer's local SQLite database.
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+pysqlite:///{(Path(tempfile.gettempdir()) / f'roadshow_pytest_{os.getpid()}.db').as_posix()}",
)

from app.api.deps import session_dep
from app.db.session import Base
from app.main import app
from app.models.entities import Institution
from app.services.seed import seed_reference_data


SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        seed_reference_data(session)
        session.commit()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[session_dep] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_institution(db_session: Session) -> Institution:
    institution = db_session.query(Institution).filter(Institution.name == "University of Mannheim").one()
    return institution
