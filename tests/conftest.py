import os
from pathlib import Path
import shutil
import tempfile
import pytest
from echo.core.config import Settings
from echo.core.database import Database
from echo.memory.store import MemoryStore


@pytest.fixture
def temp_dir():
    td = tempfile.mkdtemp(prefix="echo_test_")
    yield Path(td)
    try:
        shutil.rmtree(td, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def temp_db(temp_dir):
    db_path = temp_dir / "test_echo.db"
    db = Database(db_path=db_path)
    return db


@pytest.fixture
def memory_store(temp_db):
    return MemoryStore(db=temp_db)
