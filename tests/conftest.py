import pytest

import db


@pytest.fixture
def connection(tmp_path):
    database_path = tmp_path / "test_spaceshare.sqlite3"
    connection = db.connect(database_path)
    yield connection
    connection.close()
