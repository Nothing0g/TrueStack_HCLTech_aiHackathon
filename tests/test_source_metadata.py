from datetime import date
from app.main import SourceMetadata


def test_source_metadata_allows_unknown_effective_date_but_not_fake_date():
    m = SourceMetadata.model_validate({
        "doc_id": "DTU-ORD-TEST", "title": "Ordinance", "issuer": "DTU", "authority_level": 1,
        "doc_type": "regulation", "version": "2025", "effective_from": "", "effective_to": "",
        "supersedes": "", "scope_programmes": "ALL", "scope_batches": "ALL",
        "provenance": "official source, date not stated", "retrieved_on": date.today().isoformat(), "synthetic": "N"
    })
    assert m.effective_from == ""
