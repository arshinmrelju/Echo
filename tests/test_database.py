from echo.core.database import Database


def test_database_initialization(temp_db: Database):
    with temp_db.get_connection() as conn:
        # Check that tables exist
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cur.fetchall()}
        assert "conversations" in tables
        assert "messages" in tables
        assert "app_settings" in tables
        assert "tasks" in tables
        assert "memories" in tables
        assert "action_logs" in tables
        assert "schema_version" in tables

        # Verify PRAGMAs
        wal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert wal.lower() == "wal"


def test_transaction_rollback(temp_db: Database):
    try:
        with temp_db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('1', 'T', 'now', 'now');"
            )
            raise ValueError("Forced error")
    except ValueError:
        pass

    with temp_db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM conversations;")
        assert cur.fetchone()[0] == 0

