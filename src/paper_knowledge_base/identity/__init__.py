"""Public paper/document identity comparison API."""

from paper_knowledge_base.identity.matcher import (
    compare_identity,
    document_from_canonical_metadata,
    document_from_processing_result,
    find_identity_matches,
)
from paper_knowledge_base.identity.models import (
    DocumentIdentity,
    IdentityConfidence,
    IdentityDecision,
    IdentityEvidence,
    IdentityMatch,
    IdentityMetadata,
    IdentityRelationship,
    IdentitySignal,
    IdentityThresholds,
    PublicationType,
)

__all__ = [
    "DocumentIdentity",
    "IdentityConfidence",
    "IdentityDecision",
    "IdentityEvidence",
    "IdentityMatch",
    "IdentityMetadata",
    "IdentityRelationship",
    "IdentitySignal",
    "IdentityThresholds",
    "PublicationType",
    "compare_identity",
    "document_from_canonical_metadata",
    "document_from_processing_result",
    "find_identity_matches",
]
