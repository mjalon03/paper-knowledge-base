from paper_knowledge_base.identity import (
    DocumentIdentity,
    IdentityConfidence,
    IdentityMetadata,
    IdentityRelationship,
    IdentitySignal,
    IdentityThresholds,
    PublicationType,
    compare_identity,
    find_identity_matches,
)


def document(
    *,
    sha256: str = "a" * 64,
    title: str | None = "Astrocyte calcium signaling in the hippocampus",
    authors: tuple[str, ...] = ("Ada Author", "Bea Biologist"),
    doi: str | None = None,
    year: int | None = 2024,
    venue: str | None = "Example Journal",
    publication_type: PublicationType | str = PublicationType.UNKNOWN,
    identifiers: dict[str, str] | None = None,
) -> DocumentIdentity:
    return DocumentIdentity(
        sha256=sha256,
        filename="paper.pdf",
        metadata=IdentityMetadata(
            title=title,
            authors=authors,
            doi=doi,
            year=year,
            venue=venue,
            publication_type=publication_type,
            identifiers=identifiers or {},
            provenance=("grobid", "crossref"),
        ),
    )


def test_same_sha_is_exact_file_duplicate_without_metadata_comparison() -> None:
    result = compare_identity(
        document(doi="10.1234/original"),
        document(
            title="Completely unrelated",
            authors=("Different Person",),
            doi="10.1234/other",
        ),
    )

    assert result.relationship == IdentityRelationship.EXACT_FILE_DUPLICATE
    assert result.confidence == IdentityConfidence.HIGH
    assert result.evidence[0].signal == IdentitySignal.SHA256_MATCH


def test_different_sha_and_same_doi_is_same_paper() -> None:
    result = compare_identity(
        document(sha256="a" * 64, doi="10.1234/ABC.1"),
        document(sha256="b" * 64, doi="https://doi.org/10.1234/abc.1"),
    )

    assert result.relationship == IdentityRelationship.SAME_PAPER
    assert result.doi_match is True
    assert any(item.signal == IdentitySignal.DOI_MATCH for item in result.evidence)


def test_doi_match_dominates_title_formatting_differences() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64, doi="doi:10.1234/abc", title="Ca2+ β-astrocyte: STARDUST"
        ),
        document(
            sha256="b" * 64, doi="10.1234/ABC", title="Ca2+ β-astrocyte — STARDUST."
        ),
    )

    assert result.relationship == IdentityRelationship.SAME_PAPER
    assert result.title_similarity > 0.8


def test_doi_less_exact_title_and_authors_is_same_paper() -> None:
    result = compare_identity(
        document(sha256="a" * 64),
        document(sha256="b" * 64, authors=("Bea Biologist", "Ada Author")),
    )

    assert result.relationship == IdentityRelationship.SAME_PAPER
    assert result.confidence == IdentityConfidence.HIGH
    assert result.year_match is True


def test_doi_less_fuzzy_title_and_strong_authors_is_same_paper() -> None:
    result = compare_identity(
        document(sha256="a" * 64, title="Astrocytic calcium signalling in hippocampus"),
        document(
            sha256="b" * 64, title="Astrocyte calcium signaling in the hippocampus"
        ),
    )

    assert result.relationship == IdentityRelationship.SAME_PAPER
    assert result.title_similarity >= 0.75


def test_same_title_with_disjoint_authors_is_not_merged() -> None:
    result = compare_identity(
        document(sha256="a" * 64),
        document(sha256="b" * 64, authors=("Unauthorised Researcher",)),
    )

    assert result.relationship in {
        IdentityRelationship.DISTINCT,
        IdentityRelationship.AMBIGUOUS,
    }
    assert result.relationship != IdentityRelationship.SAME_PAPER


def test_generic_similar_titles_remain_ambiguous() -> None:
    result = compare_identity(
        document(sha256="a" * 64, title="A study", authors=("Ada Author",)),
        document(sha256="b" * 64, title="A study", authors=("Bea Author",)),
    )

    assert result.relationship == IdentityRelationship.AMBIGUOUS
    assert result.confidence == IdentityConfidence.LOW


def test_preprint_and_journal_article_are_related_versions() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            doi="10.9999/ssrn-paper",
            publication_type="posted-content",
            venue="SSRN",
            year=2023,
        ),
        document(
            sha256="b" * 64,
            doi="10.9999/journal-paper",
            publication_type="journal-article",
            year=2024,
        ),
    )

    assert result.relationship == IdentityRelationship.RELATED_VERSION
    assert result.relationship != IdentityRelationship.EXACT_FILE_DUPLICATE
    assert any(
        item.signal == IdentitySignal.PREPRINT_PUBLISHED_PAIR
        for item in result.evidence
    )


def test_version_year_difference_of_three_is_not_automatically_related() -> None:
    result = compare_identity(
        document(sha256="a" * 64, publication_type=PublicationType.PREPRINT, year=2020),
        document(
            sha256="b" * 64,
            publication_type=PublicationType.PUBLISHED_ARTICLE,
            year=2023,
        ),
    )

    assert result.relationship == IdentityRelationship.AMBIGUOUS


def test_correction_is_related_material_not_same_paper() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            title="Correction: Astrocyte calcium signaling in the hippocampus",
        ),
        document(sha256="b" * 64),
    )

    assert result.relationship == IdentityRelationship.RELATED_CORRECTION
    assert any(
        item.signal == IdentitySignal.CORRECTION_MARKER for item in result.evidence
    )


def test_erratum_and_corrigendum_markers_are_corrections() -> None:
    for marker in ("Erratum to", "Corrigendum:"):
        result = compare_identity(
            document(
                sha256="a" * 64,
                title=f"{marker} Astrocyte calcium signaling in the hippocampus",
            ),
            document(sha256="b" * 64),
        )
        assert result.relationship == IdentityRelationship.RELATED_CORRECTION


def test_retraction_notice_is_related_retraction() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            title="Retraction Note: Astrocyte calcium signaling in the hippocampus",
        ),
        document(sha256="b" * 64),
    )

    assert result.relationship == IdentityRelationship.RELATED_RETRACTION


def test_supplement_is_related_supplement() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            title="Supplementary Material: Astrocyte calcium signaling in the hippocampus",
        ),
        document(sha256="b" * 64),
    )

    assert result.relationship == IdentityRelationship.RELATED_SUPPLEMENT


def test_filename_alone_is_not_duplicate_evidence() -> None:
    left = document(sha256="a" * 64, title=None, authors=(), year=None)
    right = document(sha256="b" * 64, title=None, authors=(), year=None)
    result = compare_identity(left, right)

    assert result.relationship == IdentityRelationship.AMBIGUOUS
    assert all(item.signal != IdentitySignal.FILENAME_ONLY for item in result.evidence)


def test_conflicting_doi_and_unrelated_metadata_is_distinct() -> None:
    result = compare_identity(
        document(sha256="a" * 64, doi="10.1234/one"),
        document(
            sha256="b" * 64,
            title="Different research question",
            authors=("Other Author",),
            doi="10.1234/two",
            year=2020,
        ),
    )

    assert result.relationship == IdentityRelationship.DISTINCT
    assert result.conflicts


def test_conflicting_doi_with_version_types_is_related_version() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            doi="10.1234/preprint",
            publication_type=PublicationType.PREPRINT,
            year=2023,
        ),
        document(
            sha256="b" * 64,
            doi="10.1234/published",
            publication_type=PublicationType.PUBLISHED_ARTICLE,
            year=2024,
        ),
    )

    assert result.relationship == IdentityRelationship.RELATED_VERSION


def test_ambiguous_evidence_retains_explanation_and_scores() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64,
            title="Calcium dynamics in cells",
            authors=("Ada Author",),
            year=2020,
        ),
        document(
            sha256="b" * 64,
            title="Calcium dynamics across cells",
            authors=("Bea Author",),
            year=2024,
        ),
    )

    assert result.relationship == IdentityRelationship.AMBIGUOUS
    assert result.score is not None
    assert result.reasons
    assert result.title_similarity >= 0.0
    assert result.author_similarity == 0.0
    assert result.provenance == ("grobid", "crossref")


def test_custom_thresholds_make_boundaries_explicit() -> None:
    thresholds = IdentityThresholds(
        high_title_similarity=0.99,
        likely_title_similarity=0.99,
        minimum_same_paper_title_similarity=0.99,
    )
    result = compare_identity(
        document(sha256="a" * 64, title="Astrocyte calcium signaling in hippocampus"),
        document(
            sha256="b" * 64, title="Astrocyte calcium signaling in the hippocampus"
        ),
        thresholds=thresholds,
    )

    assert result.relationship != IdentityRelationship.SAME_PAPER


def test_matching_ignores_author_order_and_ranks_same_paper_first() -> None:
    incoming = document(sha256="incoming".ljust(64, "0"))
    same = document(
        sha256="same".ljust(64, "0"), authors=("Bea Biologist", "Ada Author")
    )
    distinct = document(
        sha256="distinct".ljust(64, "0"),
        title="Different article",
        authors=("Other Person",),
    )

    matches = find_identity_matches(incoming, (distinct, same))

    assert matches[0].candidate == same
    assert matches[0].decision.relationship == IdentityRelationship.SAME_PAPER


def test_same_title_ssrn_style_preprint_is_not_exact_duplicate() -> None:
    result = compare_identity(
        document(
            sha256="a" * 64, venue="SSRN", publication_type="posted-content", year=2023
        ),
        document(
            sha256="b" * 64,
            venue="Frontiers in Cellular Neuroscience",
            publication_type="journal-article",
            year=2024,
        ),
    )

    assert result.relationship == IdentityRelationship.RELATED_VERSION
    assert result.relationship != IdentityRelationship.SAME_PAPER
