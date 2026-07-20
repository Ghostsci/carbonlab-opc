import os
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test modules still contain legacy module-level create_all/drop_all hooks. Force
# every pytest process onto its own disposable SQLite database before importing
# backend.database, regardless of the caller's cwd or local .env file. Without
# this boundary, running pytest from backend/ can point those hooks at the local
# PostgreSQL demo database.
_worker = os.getenv("PYTEST_XDIST_WORKER", "main")
_test_database_path = (
    Path(tempfile.gettempdir())
    / f"zero_carbon_pytest_{os.getpid()}_{_worker}.db"
)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_database_path}"
os.environ["APP_ENV"] = "test"

from backend.database import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def pytest_sessionfinish(session, exitstatus):
    del session, exitstatus
    from backend.database import get_engine

    get_engine().dispose()
    _test_database_path.unlink(missing_ok=True)
