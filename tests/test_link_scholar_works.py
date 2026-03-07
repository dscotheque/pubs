"""Tests for scripts/link_scholar_works.py."""

import sqlite3
from pathlib import Path

import pytest

from scripts.link_scholar_works import (
    link_scholar_works,
    match_alert_name_to_researcher,
    matches_author_initials,
)

RESEARCHERS = [
    "Chirag Shah",
    "Emma Spiro",
    "Tanu Mitra",
    "Anna Gueorguieva",
    "Eva Maxfield Brown",
    "Benjamin Charles Germain Lee",
    "Shahan Ali Memon",
    "Katelyn Mei",
    "Nic Weber",
]


# -- match_alert_name_to_researcher -----------------------------------------


class TestMatchAlertName:
    """Tests for alert-name-to-researcher matching."""

    def test_exact_match(self) -> None:
        assert (
            match_alert_name_to_researcher("Chirag Shah", RESEARCHERS) == "Chirag Shah"
        )

    def test_middle_initial(self) -> None:
        assert (
            match_alert_name_to_researcher("Emma S. Spiro", RESEARCHERS) == "Emma Spiro"
        )

    def test_middle_name(self) -> None:
        assert (
            match_alert_name_to_researcher("Katelyn X. Mei", RESEARCHERS)
            == "Katelyn Mei"
        )

    def test_nickname(self) -> None:
        assert (
            match_alert_name_to_researcher("Tanushree Mitra", RESEARCHERS)
            == "Tanu Mitra"
        )

    def test_hyphenated_first_name(self) -> None:
        assert (
            match_alert_name_to_researcher("Anna-Maria Gueorguieva", RESEARCHERS)
            == "Anna Gueorguieva"
        )

    def test_no_match(self) -> None:
        assert match_alert_name_to_researcher("Unknown Person", RESEARCHERS) is None

    def test_single_token_returns_none(self) -> None:
        assert match_alert_name_to_researcher("Chirag", RESEARCHERS) is None


# -- matches_author_initials ------------------------------------------------


class TestMatchesAuthorInitials:
    """Tests for abbreviated-author-to-researcher matching."""

    def test_single_initial(self) -> None:
        assert matches_author_initials("C Shah", "Chirag Shah") is True

    def test_multi_initial(self) -> None:
        assert matches_author_initials("EM Brown", "Eva Maxfield Brown") is True

    def test_triple_initial(self) -> None:
        assert (
            matches_author_initials("BCG Lee", "Benjamin Charles Germain Lee") is True
        )

    def test_trailing_ellipsis_unicode(self) -> None:
        assert matches_author_initials("B Wen\u2026", "Bingbing Wen") is True

    def test_trailing_dots(self) -> None:
        assert matches_author_initials("A Caliskan...", "Aylin Caliskan") is True

    def test_full_name_match(self) -> None:
        assert matches_author_initials("Shahan Ali Memon", "Shahan Ali Memon") is True

    def test_middle_initial_not_in_db(self) -> None:
        assert matches_author_initials("JD West", "Jevin West") is True

    def test_extra_middle_initials(self) -> None:
        assert matches_author_initials("KX Mei", "Katelyn Mei") is True

    def test_last_name_mismatch(self) -> None:
        assert matches_author_initials("C Weber", "Chirag Shah") is False

    def test_initial_mismatch(self) -> None:
        assert matches_author_initials("X Shah", "Chirag Shah") is False

    def test_single_token(self) -> None:
        assert matches_author_initials("Shah", "Chirag Shah") is False


# -- link_scholar_works (end-to-end with in-memory DB) -----------------------

SCHEMA = """
CREATE TABLE researchers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    config_key TEXT UNIQUE NOT NULL
);

CREATE TABLE works (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE work_authors (
    work_id INTEGER REFERENCES works(id),
    author_name TEXT NOT NULL,
    author_position INTEGER NOT NULL,
    PRIMARY KEY (work_id, author_position)
);

CREATE TABLE researcher_works (
    researcher_id INTEGER REFERENCES researchers(id),
    work_id INTEGER REFERENCES works(id),
    PRIMARY KEY (researcher_id, work_id)
);
CREATE INDEX idx_researcher_works_work ON researcher_works(work_id);

CREATE TABLE scholar_alert_emails (
    message_id TEXT PRIMARY KEY,
    subject TEXT,
    processed_at TEXT NOT NULL
);

CREATE TABLE scholar_alert_items (
    id INTEGER PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES scholar_alert_emails(message_id),
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    work_id INTEGER REFERENCES works(id),
    created_at TEXT NOT NULL,
    UNIQUE(message_id, position)
);
CREATE INDEX idx_scholar_alert_items_work ON scholar_alert_items(work_id);
"""


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Create an in-memory-like temp DB with the minimal schema."""
    path = str(tmp_path / "test.db")
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA foreign_keys = ON")

        # Researchers
        conn.executemany(
            "INSERT INTO researchers (id, name, config_key) VALUES (?, ?, ?)",
            [
                (1, "Chirag Shah", "chirag-shah"),
                (2, "Mouly Dewan", "mouly-dewan"),
                (3, "Eva Maxfield Brown", "eva-maxfield-brown"),
            ],
        )

        # Works (orphaned -- no researcher_works rows)
        conn.executemany(
            "INSERT INTO works (id, title) VALUES (?, ?)",
            [
                (100, "Paper about search"),
                (101, "Paper about fairness"),
                (102, "Paper about archives"),
            ],
        )

        # Work authors
        conn.executemany(
            "INSERT INTO work_authors "
            "(work_id, author_name, author_position) VALUES (?, ?, ?)",
            [
                (100, "C Shah", 0),
                (100, "J Liu", 1),
                (101, "M Dewan", 0),
                (101, "C Shah", 1),
                (102, "EM Brown", 0),
            ],
        )

        # Alert emails
        conn.executemany(
            "INSERT INTO scholar_alert_emails "
            "(message_id, subject, processed_at) VALUES (?, ?, ?)",
            [
                ("msg1", "Chirag Shah - new articles", "2025-01-01"),
                ("msg2", "Mouly Dewan - new articles", "2025-01-01"),
                ("msg3", "Eva Maxfield Brown - new articles", "2025-01-01"),
            ],
        )

        # Alert items (linking emails to works)
        conn.executemany(
            "INSERT INTO scholar_alert_items "
            "(message_id, position, title, work_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("msg1", 0, "Paper about search", 100, "2025-01-01"),
                ("msg2", 0, "Paper about fairness", 101, "2025-01-01"),
                ("msg1", 1, "Paper about fairness", 101, "2025-01-01"),
                ("msg3", 0, "Paper about archives", 102, "2025-01-01"),
            ],
        )
        conn.commit()
    return path


class TestLinkScholarWorks:
    """End-to-end tests for link_scholar_works."""

    def test_links_orphaned_works(self, db_path: str) -> None:
        count = link_scholar_works(db_path)
        assert count > 0

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT researcher_id, work_id FROM researcher_works "
                "ORDER BY researcher_id, work_id"
            ).fetchall()

        # Work 100: Chirag Shah (alert msg1, author "C Shah")
        assert (1, 100) in rows
        # Work 101: Chirag Shah (alert msg1) AND Mouly Dewan (alert msg2)
        assert (1, 101) in rows
        assert (2, 101) in rows
        # Work 102: Eva Maxfield Brown (alert msg3, author "EM Brown")
        assert (3, 102) in rows

    def test_idempotent(self, db_path: str) -> None:
        first = link_scholar_works(db_path)
        second = link_scholar_works(db_path)
        assert first > 0
        assert second == 0

    def test_no_orphans(self, db_path: str) -> None:
        # Pre-link everything, then run again
        link_scholar_works(db_path)
        count = link_scholar_works(db_path)
        assert count == 0

    def test_author_validation_prevents_bad_link(self, tmp_path: Path) -> None:
        """If the researcher is not among the work's authors, skip."""
        path = str(tmp_path / "test_val.db")
        with sqlite3.connect(path) as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO researchers (id, name, config_key) "
                "VALUES (1, 'Chirag Shah', 'chirag-shah')"
            )
            conn.execute("INSERT INTO works (id, title) VALUES (200, 'Other paper')")
            # Author is NOT Chirag Shah
            conn.execute(
                "INSERT INTO work_authors "
                "(work_id, author_name, author_position) "
                "VALUES (200, 'J Smith', 0)"
            )
            conn.execute(
                "INSERT INTO scholar_alert_emails "
                "(message_id, subject, processed_at) "
                "VALUES ('m1', 'Chirag Shah - new articles', '2025-01-01')"
            )
            conn.execute(
                "INSERT INTO scholar_alert_items "
                "(message_id, position, title, work_id, created_at) "
                "VALUES ('m1', 0, 'Other paper', 200, '2025-01-01')"
            )
            conn.commit()

        count = link_scholar_works(path)
        assert count == 0

    def test_no_authors_still_links(self, tmp_path: Path) -> None:
        """If work has no authors, link based on alert name alone."""
        path = str(tmp_path / "test_noauth.db")
        with sqlite3.connect(path) as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO researchers (id, name, config_key) "
                "VALUES (1, 'Chirag Shah', 'chirag-shah')"
            )
            conn.execute(
                "INSERT INTO works (id, title) VALUES (300, 'Paper with no authors')"
            )
            conn.execute(
                "INSERT INTO scholar_alert_emails "
                "(message_id, subject, processed_at) "
                "VALUES ('m1', 'Chirag Shah - new articles', '2025-01-01')"
            )
            conn.execute(
                "INSERT INTO scholar_alert_items "
                "(message_id, position, title, work_id, created_at) "
                "VALUES ('m1', 0, 'Paper with no authors', 300, "
                "'2025-01-01')"
            )
            conn.commit()

        count = link_scholar_works(path)
        assert count == 1

        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT researcher_id, work_id FROM researcher_works"
            ).fetchall()
        assert (1, 300) in rows

    def test_unmatched_alert_name_skipped(self, tmp_path: Path) -> None:
        """Alert from unknown researcher creates no linkage."""
        path = str(tmp_path / "test_unknown.db")
        with sqlite3.connect(path) as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO researchers (id, name, config_key) "
                "VALUES (1, 'Chirag Shah', 'chirag-shah')"
            )
            conn.execute("INSERT INTO works (id, title) VALUES (400, 'Some paper')")
            conn.execute(
                "INSERT INTO work_authors "
                "(work_id, author_name, author_position) "
                "VALUES (400, 'X Unknown', 0)"
            )
            conn.execute(
                "INSERT INTO scholar_alert_emails "
                "(message_id, subject, processed_at) "
                "VALUES ('m1', 'Nobody Real - new articles', '2025-01-01')"
            )
            conn.execute(
                "INSERT INTO scholar_alert_items "
                "(message_id, position, title, work_id, created_at) "
                "VALUES ('m1', 0, 'Some paper', 400, '2025-01-01')"
            )
            conn.commit()

        count = link_scholar_works(path)
        assert count == 0

    def test_multi_alert_creates_multiple_linkages(self, db_path: str) -> None:
        """Work appearing in two researcher alerts gets two linkages."""
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT researcher_id, work_id FROM researcher_works"
            ).fetchall()
        # Before linking, nothing linked
        assert len(rows) == 0

        link_scholar_works(db_path)

        with sqlite3.connect(db_path) as conn:
            rows_101 = conn.execute(
                "SELECT researcher_id FROM researcher_works "
                "WHERE work_id = 101 ORDER BY researcher_id"
            ).fetchall()
        # Work 101 linked from msg1 (Chirag Shah) AND msg2 (Mouly Dewan)
        assert (1,) in rows_101
        assert (2,) in rows_101
