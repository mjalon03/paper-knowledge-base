"""Paper-processing orchestration and parser-independent result models."""

from typing import Any

__all__ = ["process_paper"]


def __getattr__(name: str) -> Any:
    """Expose the high-level API without pre-importing the CLI module."""

    if name == "process_paper":
        from paper_knowledge_base.processing.pipeline import process_paper

        return process_paper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
