import duckdb
import pytest

from db.init_db import SCHEMA_PATH


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    connection.execute(SCHEMA_PATH.read_text())
    yield connection
    connection.close()
