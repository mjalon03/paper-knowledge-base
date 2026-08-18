"""Adapters for mature document parsers used by the processing pipeline."""

from paper_knowledge_base.parsers.docling import DoclingAdapter
from paper_knowledge_base.parsers.grobid import GrobidAdapter

__all__ = ["DoclingAdapter", "GrobidAdapter"]
