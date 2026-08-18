"""Conservative section-heading and hierarchy normalization."""

from __future__ import annotations

import re
from dataclasses import replace

from paper_knowledge_base.content.models import ContentBlock, PaperContent, Section
from paper_knowledge_base.content.normalization import normalize_key, normalize_text
from paper_knowledge_base.content.quality.models import (
    ContentTransformation,
    ContentWarning,
    QualitySeverity,
    TransformationAction,
    WarningCode,
)

_EMPTY_NOISE = frozenset(
    {
        "article",
        "copyright",
        "edited by",
        "open access",
        "reviewed by",
        "review",
    }
)


def clean_sections(
    content: PaperContent,
) -> tuple[
    tuple[Section, ...],
    tuple[ContentBlock, ...],
    tuple[ContentWarning, ...],
    tuple[ContentTransformation, ...],
]:
    sections: list[Section] = []
    blocks = list(content.blocks)
    warnings: list[ContentWarning] = []
    transformations: list[ContentTransformation] = []

    for section in content.sections:
        raw_title = normalize_text(section.title)
        title, level, normalized = _normalize_heading(raw_title, section.level)
        block_ids = set(section.block_ids)
        noise_kind = _noise_kind(raw_title, bool(block_ids))

        if sections and normalize_key(title) == normalize_key(sections[-1].title):
            previous = sections[-1]
            if section.order == previous.order + 1 or not block_ids:
                if block_ids:
                    blocks = [
                        replace(block, section_id=previous.id)
                        if block.id in block_ids
                        else block
                        for block in blocks
                    ]
                transformations.append(
                    ContentTransformation(
                        action=TransformationAction.MERGE_DUPLICATE_SECTION,
                        target_id=previous.id,
                        source_ids=(section.id,),
                        reason="Adjacent sections have the same normalized heading.",
                        confidence=0.96,
                        evidence=(f"normalized_title={normalize_key(title)}",),
                    )
                )
                warnings.append(
                    ContentWarning(
                        code=WarningCode.DUPLICATE_SECTION,
                        severity=QualitySeverity.INFO,
                        message="Adjacent duplicate section wrapper merged.",
                        section_id=section.id,
                        provenance=section.provenance,
                    )
                )
                continue

        if noise_kind == "empty":
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.REMOVE_EMPTY_SECTION,
                    target_id=section.id,
                    reason="The section is a parser-generated metadata/figure/table wrapper with no blocks.",
                    confidence=0.98,
                    evidence=(f"title={raw_title!r}",),
                )
            )
            continue

        if noise_kind in {"hide", "code"}:
            title = ""
            normalized = True
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.HIDE_SECTION_HEADING,
                    target_id=section.id,
                    reason="The heading is strongly parser-like; its blocks are retained in place.",
                    confidence=0.92 if noise_kind == "hide" else 0.90,
                    evidence=(f"title={raw_title!r}", f"kind={noise_kind}"),
                )
            )
            warnings.append(
                ContentWarning(
                    code=WarningCode.SUSPICIOUS_SECTION,
                    severity=QualitySeverity.WARNING,
                    message="Parser-like section heading hidden; associated blocks retained.",
                    section_id=section.id,
                    provenance=section.provenance,
                )
            )

        if normalized:
            transformations.append(
                ContentTransformation(
                    action=TransformationAction.NORMALIZE_SECTION_HEADING,
                    target_id=section.id,
                    reason="Leading hierarchy punctuation was normalized without changing block content.",
                    confidence=0.97,
                    evidence=(
                        f"before={raw_title!r}",
                        f"after={title!r}",
                        f"level={level}",
                    ),
                )
            )
        sections.append(
            replace(
                section,
                title=title,
                level=level,
                special=(
                    "quality_hidden_heading"
                    if noise_kind in {"hide", "code"}
                    else section.special
                ),
            )
        )

    sections = _rebuild_hierarchy(sections)
    block_ids_by_section: dict[str, list[str]] = {}
    for block in blocks:
        if block.section_id is not None:
            block_ids_by_section.setdefault(block.section_id, []).append(block.id)
    sections = [
        replace(
            section,
            order=index,
            block_ids=tuple(block_ids_by_section.get(section.id, ())),
        )
        for index, section in enumerate(sections)
    ]
    return tuple(sections), tuple(blocks), tuple(warnings), tuple(transformations)


def _normalize_heading(title: str, level: int) -> tuple[str, int, bool]:
    match = re.match(r"^(\s*(?:\.\s*)+)(.+)$", title)
    if not match:
        return title, level, False
    dots = len(re.findall(r"\.", match.group(1)))
    return match.group(2).strip(), max(level, dots + 1), True


def _noise_kind(title: str, has_blocks: bool) -> str | None:
    key = normalize_key(title)
    if not title:
        return "empty" if not has_blocks else "hide"
    if key in _EMPTY_NOISE or key in {"body", "figure", "table"}:
        return "hide" if has_blocks else "empty"
    if key.startswith(("table ", "figure ")) and not has_blocks:
        return "empty"
    if _looks_like_code(title):
        return "code"
    return None


def _looks_like_code(title: str) -> bool:
    key = normalize_key(title)
    return (
        title.lstrip().startswith("#")
        or key.startswith(("import ", "def ", "class "))
        or ("--" in title and len(title) > 50)
        or (" > " in title and len(title) > 50)
    )


def _rebuild_hierarchy(sections: list[Section]) -> list[Section]:
    stack: list[tuple[int, str]] = []
    rebuilt: list[Section] = []
    for section in sections:
        while stack and stack[-1][0] >= section.level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None
        rebuilt.append(replace(section, parent_id=parent_id))
        stack.append((section.level, section.id))
    return rebuilt
