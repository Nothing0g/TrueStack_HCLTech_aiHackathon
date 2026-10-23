from __future__ import annotations

import pytest

import app.db as db


@pytest.fixture

def isolated_db(tmp_path, monkeypatch):
    """Use a fresh SQLite DB; no ChromaDB/model downloads required for unit tests."""
    db_path = tmp_path / "test_university.db"
    monkeypatch.setattr(db, "DATABASE_PATH", db_path)
    db.init_db()
    db.seed_source_metadata_and_rules()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO students VALUES (?,?,?,?,?,?,?)",
            ("S1001", "Aarav Mehta", "B.Tech CSE", 2023, 4, 7.2, 0),
        )
        conn.execute(
            "INSERT INTO students VALUES (?,?,?,?,?,?,?)",
            ("S1002", "Ananya Rao", "B.Tech CSE", 2024, 3, 6.5, 1),
        )
        conn.execute(
            "INSERT INTO courses VALUES (?,?,?,?,?)",
            ("CS201", "Data Structures", "B.Tech CSE", 4, 4),
        )
        conn.execute(
            "INSERT INTO attendance VALUES (?,?,?,?)",
            ("S1001", "CS201", 100, 75),
        )
        conn.execute(
            "INSERT INTO attendance VALUES (?,?,?,?)",
            ("S1002", "CS201", 100, 74),
        )
        conn.execute(
            "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?)",
            ("S1001", "CS201", "2026-MAY", "REGULAR", 20, 55, 75, 100, "PASS"),
        )
    return db_path


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Fresh SQLite database seeded with the full Annex C synthetic fixture."""
    db_path = tmp_path / "test_university_full.db"
    monkeypatch.setattr(db, "DATABASE_PATH", db_path)
    db.init_db()
    from scripts.load_students import load
    load(db.ROOT / "data" / "test_students")
    return db_path
