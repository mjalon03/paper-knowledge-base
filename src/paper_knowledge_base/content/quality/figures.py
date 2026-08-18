"""Figure/table assessment and conservative picture suppression."""

from __future__ import annotations

from dataclasses import replace

from paper_knowledge_base.content.models import (
    ContentBlock,
    Figure,
    PaperContent,
    Paragraph,
    Table,
)
from paper_knowledge_base.content.normalization import normalize_key
from paper_knowledge_base.content.quality.models import (
    CaptionAssociation,
    ContentTransformation,
    ContentWarning,
    FigureAssessment,
    FigureCategory,
    QualitySeverity,
    TransformationAction,
    WarningCode,
)


def clean_figures(
    content: PaperContent,
) -> tuple[
    tuple[ContentBlock, ...],
    tuple[ContentWarning, ...],
    tuple[ContentTransformation, ...],
    tuple[FigureAssessment, ...],
    tuple[CaptionAssociation, ...],
]:
    blocks = list(content.blocks)
    (
        blocks,
        nearby_warnings,
        nearby_transformations,
        nearby_associations,
    ) = _associate_nearby_captions(blocks)
    figures = [block for block in blocks if isinstance(block, Figure)]
    signatures = _small_signatures(figures)
    warnings: list[ContentWarning] = list(nearby_warnings)
    transformations: list[ContentTransformation] = list(nearby_transformations)
    assessments: list[FigureAssessment] = []
    associations: list[CaptionAssociation] = list(nearby_associations)
    suppressed: set[str] = set()

    for figure in figures:
        category, reason, evidence = _classify(figure, signatures)
        assessments.append(
            FigureAssessment(
                figure_id=figure.id,
                category=category,
                reason=reason,
                evidence=evidence,
            )
        )
        if figure.caption:
            associations.append(
                CaptionAssociation(
                    content_id=figure.id,
                    caption_source_id=None,
                    source="PARSER",
                    confidence=1.0,
                    evidence=("caption supplied by canonical parser mapping",),
                )
            )
        elif category == FigureCategory.DECORATIVE:
            suppressed.add(figure.id)
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.SUPPRESS_PICTURE,
                    target_id=figure.id,
                    reason="Uncaptioned repeated/edge picture is a likely decorative parser artifact.",
                    confidence=0.93,
                    evidence=evidence,
                )
            )
            warnings.append(
                ContentWarning(
                    code=WarningCode.PICTURE_NOISE,
                    severity=QualitySeverity.INFO,
                    message="Likely decorative or repeated picture suppressed.",
                    figure_id=figure.id,
                    provenance=figure.provenance,
                )
            )
        else:
            warnings.append(
                ContentWarning(
                    code=WarningCode.FIGURE_WITHOUT_CAPTION,
                    severity=QualitySeverity.WARNING,
                    message="Figure retained because its scientific role is uncertain, but no caption is associated.",
                    figure_id=figure.id,
                    provenance=figure.provenance,
                )
            )

    blocks = [block for block in blocks if block.id not in suppressed]
    for block in blocks:
        if isinstance(block, Table) and not block.caption:
            warnings.append(
                ContentWarning(
                    code=WarningCode.TABLE_WITHOUT_CAPTION,
                    severity=QualitySeverity.WARNING,
                    message="Table retained without a confidently associated caption.",
                    block_id=block.id,
                    provenance=block.provenance,
                )
            )
    return (
        tuple(blocks),
        tuple(warnings),
        tuple(transformations),
        tuple(assessments),
        tuple(associations),
    )


def _small_signatures(figures: list[Figure]) -> dict[tuple[int, int, str | None], int]:
    signatures: dict[tuple[int, int, str | None], int] = {}
    for figure in figures:
        dims = _dimensions(figure)
        if dims is None:
            continue
        width, height, origin = dims
        if width * height <= 15_000:
            key = (round(width / 5), round(height / 5), origin)
            signatures[key] = signatures.get(key, 0) + 1
    return signatures


def _classify(
    figure: Figure,
    signatures: dict[tuple[int, int, str | None], int],
) -> tuple[FigureCategory, str, tuple[str, ...]]:
    if figure.caption:
        return (
            FigureCategory.SCIENTIFIC_FIGURE,
            "Captioned picture retained.",
            ("caption_present",),
        )
    if figure.label and "table" in normalize_key(figure.label):
        return (
            FigureCategory.TABLE_IMAGE,
            "Picture label indicates a table image.",
            ("table_label",),
        )
    dims = _dimensions(figure)
    if dims is None:
        return (
            FigureCategory.UNKNOWN,
            "No geometry is available for a conservative classification.",
            (),
        )
    width, height, origin = dims
    signature = (round(width / 5), round(height / 5), origin)
    repeated = signatures.get(signature, 0) >= 2
    edge = _page_edge(figure)
    area = width * height
    evidence = (
        f"area={area:.0f}",
        f"repeated_geometry={repeated}",
        f"page_edge={edge}",
    )
    if area <= 15_000 and (repeated or edge):
        return (
            FigureCategory.DECORATIVE,
            "Small uncaptioned repeated or page-edge picture.",
            evidence,
        )
    return (
        FigureCategory.UNKNOWN,
        "Uncaptioned picture retained because it may be scientifically meaningful.",
        evidence,
    )


def _associate_nearby_captions(
    blocks: list[ContentBlock],
) -> tuple[
    list[ContentBlock],
    list[ContentWarning],
    list[ContentTransformation],
    list[CaptionAssociation],
]:
    warnings: list[ContentWarning] = []
    transformations: list[ContentTransformation] = []
    associations: list[CaptionAssociation] = []
    by_order = sorted(blocks, key=lambda block: (block.order, block.id))
    suppressed: set[str] = set()
    for index, block in enumerate(by_order):
        if not isinstance(block, Figure) or block.caption:
            continue
        candidates = []
        for candidate in by_order[max(0, index - 2) : index + 3]:
            if not isinstance(candidate, Paragraph) or not candidate.text:
                continue
            if not _same_page(block, candidate):
                continue
            if _looks_like_caption(candidate.text, block.label):
                candidates.append(candidate)
        if len(candidates) != 1:
            if len(candidates) > 1:
                warnings.append(
                    ContentWarning(
                        code=WarningCode.CAPTION_WITHOUT_FIGURE,
                        severity=QualitySeverity.WARNING,
                        message="Multiple nearby caption candidates found; none was forced.",
                        figure_id=block.id,
                        provenance=block.provenance,
                    )
                )
            continue
        caption = candidates[0]
        replacement = replace(block, caption=caption.text)
        by_order[by_order.index(block)] = replacement
        suppressed.add(caption.id)
        associations.append(
            CaptionAssociation(
                content_id=block.id,
                caption_source_id=caption.id,
                source="PROXIMITY",
                confidence=0.86,
                evidence=("same page", "nearby order", "figure label/text match"),
            )
        )
        transformations.append(
            ContentTransformation(
                action=TransformationAction.ASSOCIATE_CAPTION,
                target_id=block.id,
                source_ids=(caption.id,),
                reason="A unique same-page nearby caption matched the figure label.",
                confidence=0.86,
            )
        )
    return (
        [block for block in by_order if block.id not in suppressed],
        warnings,
        transformations,
        associations,
    )


def _looks_like_caption(text: str, label: str | None) -> bool:
    key = normalize_key(text)
    if not key.startswith(("figure ", "fig. ", "fig ", "table ")):
        return False
    return not label or normalize_key(label).replace(".", "") in key.replace(".", "")


def _same_page(first: ContentBlock, second: ContentBlock) -> bool:
    return bool(
        first.source_location
        and second.source_location
        and first.source_location.page_number is not None
        and first.source_location.page_number == second.source_location.page_number
    )


def _dimensions(figure: Figure) -> tuple[float, float, str | None] | None:
    bbox = figure.source_location.bbox if figure.source_location else None
    if bbox is None:
        return None
    return abs(bbox.x1 - bbox.x0), abs(bbox.y1 - bbox.y0), bbox.coordinate_origin


def _page_edge(figure: Figure) -> bool:
    bbox = figure.source_location.bbox if figure.source_location else None
    return bool(bbox and (min(bbox.y0, bbox.y1) <= 80 or max(bbox.y0, bbox.y1) >= 680))
