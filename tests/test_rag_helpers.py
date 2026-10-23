from __future__ import annotations

from app.rag import chunk_text, read_document


def test_chunk_text_preserves_heading_and_respects_chunks():
    text = "# Attendance Rules\n\nMinimum attendance is 75%.\n\nStudents can request approved condonation."
    chunks = chunk_text(text, max_chars=100, overlap=10)
    assert len(chunks) >= 2
    assert all("Attendance Rules" in c for c in chunks)


def test_text_document_reading(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("[PAGE 3]\nClause 7.2 says this is a test source.", encoding="utf-8")
    text, pages = read_document(p)
    assert "[PAGE 3]" in text
    assert pages == []
