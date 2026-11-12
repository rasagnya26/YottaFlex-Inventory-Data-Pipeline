import pytest
from pathlib import Path
from src.database import init_db

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_inventory.db"
    init_db(path)
    return path
