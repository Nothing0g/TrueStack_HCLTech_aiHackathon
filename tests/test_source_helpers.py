from __future__ import annotations

from scripts.activate_rule import clause_is_indexed
from app.main import AskRequest, SourceMetadata
from pydantic import ValidationError
import pytest


def test_clause_verification_accepts_clause_with_human_readable_page_note():
    chunks = [{"text": "R.1(B).22 Attendance. Students must have minimum 75 percent.", "metadata": {"section": "R.1(B).22 Attendance", "page": 25}}]
    assert clause_is_indexed("R.1(B).22; PDF page 25 (printed page 19)", chunks)


def test_ask_request_rejects_invalid_as_of_date():
    with pytest.raises(ValidationError):
        AskRequest(question="Test", as_of_date="23-10-2026")


def test_synthetic_metadata_requires_visible_label():
    with pytest.raises(ValidationError):
        SourceMetadata(doc_id="SYN-TEST", title="Test only", issuer="Test", authority_level=4,
                       doc_type="faq", version="1", effective_from="2026-01-01", effective_to="",
                       supersedes="", scope_programmes="ALL", scope_batches="ALL", provenance="synthetic fixture",
                       retrieved_on="2026-10-23", synthetic="Y")
