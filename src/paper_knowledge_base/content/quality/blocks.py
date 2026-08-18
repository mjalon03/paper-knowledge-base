"""Conservative block-level duplicate and repeated-page-noise handling."""

from __future__ import annotations

from paper_knowledge_base.content.models import (
    BoundingBox,
    ContentBlock,
    PaperContent,
    Paragraph,
)
from paper_knowledge_base.content.normalization import normalize_key
from paper_knowledge_base.content.quality.models import (
    ContentTransformation,
    ContentWarning,
    QualitySeverity,
    TransformationAction,
    WarningCode,
)


def clean_blocks(
    content: PaperContent,
) -> tuple[
    tuple[ContentBlock, ...],
    tuple[ContentWarning, ...],
    tuple[ContentTransformation, ...],
]:
    blocks = list(content.blocks)
    warnings: list[ContentWarning] = []
    transformations: list[ContentTransformation] = []
    suppressed: set[str] = set()

    repeated_groups: dict[str, list[Paragraph]] = {}
    for block in blocks:
        if isinstance(block, Paragraph) and block.text:
            repeated_groups.setdefault(normalize_key(block.text), []).append(block)
    for values in repeated_groups.values():
        pages = {
            block.source_location.page_number
            for block in values
            if block.source_location and block.source_location.page_number is not None
        }
        candidates = [block for block in values if _is_page_edge(block)]
        if len(pages) < 2 or len(candidates) < 2 or len(candidates) != len(values):
            continue
        for block in candidates:
            suppressed.add(block.id)
            code = (
                WarningCode.REPEATED_HEADER
                if _is_top_edge(block)
                else WarningCode.REPEATED_FOOTER
            )
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.SUPPRESS_REPEATED_PAGE_NOISE,
                    target_id=block.id,
                    reason="Identical text repeats at the same page edge on multiple pages.",
                    confidence=0.95,
                    evidence=(f"pages={sorted(pages)}", f"text={block.text[:80]!r}"),
                )
            )
            warnings.append(
                ContentWarning(
                    code=code,
                    severity=QualitySeverity.INFO,
                    message="Repeated page-edge text suppressed from mobile content.",
                    block_id=block.id,
                    provenance=block.provenance,
                )
            )

    retained: list[ContentBlock] = []
    duplicate_candidates: dict[tuple[str, int], list[Paragraph]] = {}
    for block in sorted(blocks, key=lambda item: (item.order, item.id)):
        if block.id in suppressed:
            continue
        if _is_empty(block):
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.SUPPRESS_EMPTY_BLOCK,
                    target_id=block.id,
                    reason="Empty paragraph/equation has no mobile-readable payload.",
                    confidence=0.99,
                )
            )
            continue
        if isinstance(block, Paragraph) and block.text and block.source_location:
            page = block.source_location.page_number
            key = (normalize_key(block.text), page or -1)
            prior = duplicate_candidates.setdefault(key, [])
            if not block.citation_ids and any(
                _same_geometry(block, item) for item in prior
            ):
                transformations.append(
                    ContentTransformation(
                        action=TransformationAction.SUPPRESS_DUPLICATE_BLOCK,
                        target_id=block.id,
                        reason="Adjacent parser-overlap paragraph duplicates text and same-page geometry.",
                        confidence=0.97,
                        evidence=(f"page={page}",),
                        source_ids=tuple(item.id for item in prior),
                    )
                )
                warnings.append(
                    ContentWarning(
                        code=WarningCode.POSSIBLE_DUPLICATE_BLOCK,
                        severity=QualitySeverity.INFO,
                        message="Same-page duplicate paragraph suppressed.",
                        block_id=block.id,
                        provenance=block.provenance,
                    )
                )
                continue
            prior.append(block)
        retained.append(block)
    return tuple(retained), tuple(warnings), tuple(transformations)


def _is_empty(block: ContentBlock) -> bool:
    if isinstance(block, Paragraph):
        return not block.text.strip()
    return block.block_type.value == "equation" and not (
        getattr(block, "text", None) or getattr(block, "latex", None)
    )


def _same_geometry(first: Paragraph, second: Paragraph) -> bool:
    left = first.source_location
    right = second.source_location
    if not left or not right or left.page_number != right.page_number:
        return False
    if left.coordinate_system != right.coordinate_system:
        return False
    if not left.bbox or not right.bbox:
        return False
    return _iou(left.bbox, right.bbox) >= 0.80


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    left = max(first.x0, second.x0)
    top = max(first.y0, second.y0)
    right = min(first.x1, second.x1)
    bottom = min(first.y1, second.y1)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first.x1 - first.x0) * max(0.0, first.y1 - first.y0)
    second_area = max(0.0, second.x1 - second.x0) * max(0.0, second.y1 - second.y0)
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _is_page_edge(block: ContentBlock) -> bool:
    location = block.source_location
    if not location or not location.bbox:
        return False
    bbox = location.bbox
    return min(bbox.y0, bbox.y1) <= 80 or max(bbox.y0, bbox.y1) >= 680


def _is_top_edge(block: ContentBlock) -> bool:
    location = block.source_location
    return bool(
        location and location.bbox and max(location.bbox.y0, location.bbox.y1) >= 680
    )
