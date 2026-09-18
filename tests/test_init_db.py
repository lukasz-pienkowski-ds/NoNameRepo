from db.init_db import init_db


def test_init_db_creates_empty_documents_table(tmp_path):
    con = init_db(tmp_path / "context.duckdb")
    try:
        (count,) = con.execute("SELECT count(*) FROM documents").fetchone()
        assert count == 0
    finally:
        con.close()


def test_init_db_creates_parent_directories(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "context.duckdb"
    con = init_db(db_path)
    try:
        assert db_path.exists()
    finally:
        con.close()


def test_init_db_is_idempotent_on_existing_file(tmp_path):
    db_path = tmp_path / "context.duckdb"
    con = init_db(db_path)
    con.close()

    con2 = init_db(db_path)
    try:
        (count,) = con2.execute("SELECT count(*) FROM documents").fetchone()
        assert count == 0
    finally:
        con2.close()
