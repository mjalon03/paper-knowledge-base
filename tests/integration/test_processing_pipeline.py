from __future__ import annotations

import os
from pathlib import Path

import pytest

from paper_knowledge_base.processing.pipeline import process_paper

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("PKB_RUN_INTEGRATION") != "1",
    reason="Set PKB_RUN_INTEGRATION=1 after configuring GROBID and Docling.",
)
@pytest.mark.parametrize("path", sorted(Path("data").glob("*.pdf")))
def test_real_paper_pipeline(path: Path) -> None:
    result = process_paper(path)

    assert result.inspection.has_usable_embedded_text
    assert result.parser_runs["grobid"].status.value == "success"
    assert result.parser_runs["docling"].status.value == "success"
