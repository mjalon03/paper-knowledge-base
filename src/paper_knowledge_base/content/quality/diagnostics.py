"""Non-destructive structural, source-location, and citation diagnostics."""

from __future__ import annotations

from itertools import pairwise

from paper_knowledge_base.content.models import PaperContent
from paper_knowledge_base.content.quality.models import (
    ContentWarning,
    QualitySeverity,
    WarningCode,
    citation_is_valid,
)


def diagnose_content(content: PaperContent) -> tuple[ContentWarning, ...]:
    warnings: list[ContentWarning] = []
    reference_ids = [reference.id for reference in content.references]
    for reference_id in set(reference_ids):
        if reference_ids.count(reference_id) > 1:
            warnings.append(
                ContentWarning(
                    code=WarningCode.CITATION_LINK_MISSING,
                    severity=QualitySeverity.ERROR,
                    message="Reference IDs are not unique.",
                )
            )
    block_ids = {block.id for block in content.blocks}
    page_numbers: list[int] = []
    for block in content.ordered_blocks:
        if block.source_location and block.source_location.page_number is not None:
            page_numbers.append(block.source_location.page_number)
        elif block.block_type.value in {"paragraph", "figure", "table", "equation"}:
            warnings.append(
                ContentWarning(
                    code=WarningCode.SOURCE_LOCATION_MISSING,
                    severity=QualitySeverity.INFO,
                    message="Content block has no source page/location.",
                    block_id=block.id,
                    provenance=block.provenance,
                )
            )
    for previous, current in pairwise(page_numbers):
        if current + 1 < previous:
            warnings.append(
                ContentWarning(
                    code=WarningCode.ORDER_ANOMALY,
                    severity=QualitySeverity.WARNING,
                    message="Source page order decreases unexpectedly in the canonical stream.",
                )
            )
            break
    for citation in content.citations:
        if (
            citation.block_id not in block_ids
            or not citation.reference_ids
            or not citation_is_valid(citation, content)
        ):
            warnings.append(
                ContentWarning(
                    code=WarningCode.CITATION_LINK_MISSING,
                    severity=QualitySeverity.WARNING,
                    message="Citation does not resolve to an existing content block and reference set.",
                    block_id=citation.block_id,
                    provenance=citation.provenance,
                )
            )
        block = next(
            (item for item in content.blocks if item.id == citation.block_id), None
        )
        text = getattr(block, "text", None) if block else None
        invalid_offsets = (
            text is None
            or citation.start is None
            or citation.end is None
            or citation.start < 0
            or citation.end > len(text)
            or citation.start >= citation.end
            or text[citation.start : citation.end] != citation.display
        )
        if (citation.start is not None or citation.end is not None) and invalid_offsets:
            warnings.append(
                ContentWarning(
                    code=WarningCode.CITATION_OFFSET_INVALID,
                    severity=QualitySeverity.WARNING,
                    message="Citation character offsets do not match paragraph text.",
                    block_id=citation.block_id,
                    provenance=citation.provenance,
                )
            )
    previous_level = 0
    for section in content.sections:
        if section.level > previous_level + 1 and previous_level:
            warnings.append(
                ContentWarning(
                    code=WarningCode.HIERARCHY_ANOMALY,
                    severity=QualitySeverity.WARNING,
                    message="Section hierarchy jumps by more than one level.",
                    section_id=section.id,
                    provenance=section.provenance,
                )
            )
        previous_level = section.level
    return tuple(warnings)
