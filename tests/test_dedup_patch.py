"""Tests for patches/dedup.py merge helpers.

Verifies that the patched merge_works prefers richer metadata over
sparse data from early sources like Google Scholar alerts.
"""

from labpubs.models import Author, Source, Work

from patches.dedup import (
    _pick_richer_authors,
    _pick_richer_str,
    merge_works,
)


def _author(name: str) -> Author:
    """Create a minimal Author instance for testing."""
    return Author(name=name)


def _work(
    title: str = "Test Paper",
    authors: list[Author] | None = None,
    venue: str | None = None,
    doi: str | None = None,
    abstract: str | None = None,
    sources: list[Source] | None = None,
    year: int | None = 2025,
) -> Work:
    """Create a minimal Work instance for testing."""
    return Work(
        title=title,
        authors=authors or [],
        venue=venue,
        doi=doi,
        abstract=abstract,
        sources=sources or [Source.OPENALEX],
        year=year,
    )


# -- _pick_richer_str --------------------------------------------------------


class TestPickRicherStr:
    """Tests for the richer-string selector."""

    def test_both_none(self) -> None:
        assert _pick_richer_str(None, None) is None

    def test_a_none(self) -> None:
        assert _pick_richer_str(None, "hello") == "hello"

    def test_b_none(self) -> None:
        assert _pick_richer_str("hello", None) == "hello"

    def test_a_empty(self) -> None:
        assert _pick_richer_str("", "hello") == "hello"

    def test_prefers_longer(self) -> None:
        short = "arXiv preprint"
        long = "arXiv (Cornell University)"
        assert _pick_richer_str(short, long) == long

    def test_penalises_unicode_ellipsis(self) -> None:
        truncated = "Proceedings of the\u2026"
        full = "Proceedings of the AAAI Conference"
        assert _pick_richer_str(truncated, full) == full

    def test_penalises_ascii_ellipsis(self) -> None:
        truncated = "arXiv preprint arXiv..."
        full = "arXiv (Cornell University)"
        assert _pick_richer_str(truncated, full) == full

    def test_b_truncated_returns_a(self) -> None:
        full = "arXiv (Cornell University)"
        truncated = "arXiv preprint..."
        assert _pick_richer_str(full, truncated) == full

    def test_equal_length_prefers_existing(self) -> None:
        assert _pick_richer_str("AAAA", "BBBB") == "AAAA"

    def test_truncated_both_prefers_longer(self) -> None:
        a = "short..."
        b = "a much longer truncated value..."
        assert _pick_richer_str(a, b) == b


# -- _pick_richer_authors ----------------------------------------------------


class TestPickRicherAuthors:
    """Tests for the richer-author-list selector."""

    def test_a_empty(self) -> None:
        b = [_author("Chirag Shah")]
        assert _pick_richer_authors([], b) == b

    def test_b_empty(self) -> None:
        a = [_author("Chirag Shah")]
        assert _pick_richer_authors(a, []) == a

    def test_prefers_more_entries(self) -> None:
        sparse = [_author("C Shah")]
        rich = [_author("Chirag Shah"), _author("Jing Liu")]
        assert _pick_richer_authors(sparse, rich) == rich

    def test_same_count_prefers_longer_names(self) -> None:
        abbreviated = [_author("C Shah"), _author("J Liu")]
        full = [_author("Chirag Shah"), _author("Jing Liu")]
        assert _pick_richer_authors(abbreviated, full) == full

    def test_same_count_same_length_prefers_first(self) -> None:
        a = [_author("AAAA")]
        b = [_author("BBBB")]
        assert _pick_richer_authors(a, b) == a


# -- merge_works end-to-end -------------------------------------------------


class TestMergeWorks:
    """End-to-end tests for the patched merge_works."""

    def test_richer_venue_wins(self) -> None:
        """OpenAlex venue replaces truncated scholar-alert venue."""
        existing = _work(
            venue="arXiv preprint arXiv...",
            sources=[Source.CROSSREF],
        )
        new = _work(
            venue="arXiv (Cornell University)",
            sources=[Source.OPENALEX],
        )
        merged = merge_works(existing, new)
        assert merged.venue == "arXiv (Cornell University)"

    def test_richer_title_wins(self) -> None:
        """Longer title from OpenAlex replaces shorter scholar-alert title."""
        existing = _work(
            title="Short Title",
            sources=[Source.CROSSREF],
        )
        new = _work(
            title="A Much Longer and More Descriptive Title",
            sources=[Source.OPENALEX],
        )
        merged = merge_works(existing, new)
        assert merged.title == "A Much Longer and More Descriptive Title"

    def test_richer_authors_wins(self) -> None:
        """Full author names from OpenAlex replace abbreviated ones."""
        existing = _work(
            authors=[_author("C Shah"), _author("J Liu")],
            sources=[Source.CROSSREF],
        )
        new = _work(
            authors=[
                _author("Chirag Shah"),
                _author("Jing Liu"),
                _author("Alice Smith"),
            ],
            sources=[Source.OPENALEX],
        )
        merged = merge_works(existing, new)
        assert len(merged.authors) == 3
        assert merged.authors[0].name == "Chirag Shah"

    def test_fills_missing_abstract(self) -> None:
        """New source fills abstract when existing has none."""
        existing = _work(abstract=None, sources=[Source.CROSSREF])
        new = _work(abstract="This paper explores...", sources=[Source.OPENALEX])
        merged = merge_works(existing, new)
        assert merged.abstract == "This paper explores..."

    def test_fills_missing_doi(self) -> None:
        """New source fills DOI when existing has none."""
        existing = _work(doi=None, sources=[Source.CROSSREF])
        new = _work(doi="10.1234/test", sources=[Source.OPENALEX])
        merged = merge_works(existing, new)
        assert merged.doi == "10.1234/test"

    def test_sources_merged(self) -> None:
        """Both sources appear in the merged record."""
        existing = _work(sources=[Source.CROSSREF])
        new = _work(sources=[Source.OPENALEX])
        merged = merge_works(existing, new)
        source_values = [s.value for s in merged.sources]
        assert "crossref" in source_values
        assert "openalex" in source_values

    def test_citation_count_takes_max(self) -> None:
        """Higher citation count wins."""
        existing = _work(sources=[Source.OPENALEX])
        existing.citation_count = 5
        new = _work(sources=[Source.OPENALEX])
        new.citation_count = 20
        merged = merge_works(existing, new)
        assert merged.citation_count == 20

    def test_existing_doi_preserved(self) -> None:
        """Existing DOI is not overwritten by new source."""
        existing = _work(doi="10.1234/original", sources=[Source.OPENALEX])
        new = _work(doi="10.5678/other", sources=[Source.CROSSREF])
        merged = merge_works(existing, new)
        assert merged.doi == "10.1234/original"

    def test_equal_titles_prefers_existing(self) -> None:
        """When titles are equal length, existing wins."""
        existing = _work(title="Title A", sources=[Source.OPENALEX])
        new = _work(title="Title B", sources=[Source.CROSSREF])
        merged = merge_works(existing, new)
        assert merged.title == "Title A"
