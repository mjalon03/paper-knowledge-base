from __future__ import annotations

import os

import pytest

from paper_knowledge_base.metadata.normalization import normalize_doi
from paper_knowledge_base.metadata.sources.crossref import CrossrefClient
from paper_knowledge_base.metadata.sources.openalex import OpenAlexClient

pytestmark = pytest.mark.metadata_integration


@pytest.mark.skipif(
    os.environ.get("PKB_RUN_METADATA_INTEGRATION") != "1",
    reason="Set PKB_RUN_METADATA_INTEGRATION=1 to call public Crossref/OpenAlex APIs.",
)
def test_public_doi_lookup() -> None:
    doi = "10.1117/1.NPh.9.2.021907"

    crossref = CrossrefClient().lookup_doi(doi)
    openalex = OpenAlexClient().lookup_doi(doi)

    assert crossref is not None and crossref.doi == normalize_doi(doi)
    assert openalex is not None and openalex.doi == normalize_doi(doi)
