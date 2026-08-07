#!/usr/bin/env python3
"""Link orphaned scholar-alert works to researchers.

Google Scholar alert ingestion adds works to the database but does not
create researcher_works linkages. This script resolves that by matching
alert email subjects (which name the researcher) to DB researcher
records, validating against work_authors, and inserting the linkages.
"""

import argparse
import logging
import re
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Alert subject names that differ from the canonical DB name.
NICKNAME_MAP: dict[str, str] = {
    "tanushree": "tanu",
}


def _normalize(name: str) -> str:
    """Lowercase, strip periods, collapse whitespace."""
    return re.sub(r"\s+", " ", name.replace(".", "").strip().lower())


def match_alert_name_to_researcher(
    alert_name: str,
    researcher_names: list[str],
) -> str | None:
    """Match a scholar alert subject name to a researcher name.

    Handles middle initials ("Emma S. Spiro" -> "Emma Spiro"),
    nicknames ("Tanushree Mitra" -> "Tanu Mitra"), and
    hyphenated names ("Anna-Maria Gueorguieva" -> "Anna Gueorguieva").

    Args:
        alert_name: Name extracted from the alert email subject.
        researcher_names: Canonical researcher names from the DB.

    Returns:
        Matching researcher name, or None if no match found.
    """
    norm_alert = _normalize(alert_name)

    # Pass 1: exact normalized match
    for name in researcher_names:
        if _normalize(name) == norm_alert:
            return name

    # Pass 2: compare first + last tokens with prefix/nickname handling
    alert_parts = norm_alert.split()
    if len(alert_parts) < 2:
        return None

    alert_first = alert_parts[0].split("-")[0]
    alert_last = alert_parts[-1]
    alert_first_resolved = NICKNAME_MAP.get(alert_first, alert_first)

    for name in researcher_names:
        res_parts = _normalize(name).split()
        if len(res_parts) < 2:
            continue
        res_first = res_parts[0].split("-")[0]
        res_last = res_parts[-1]

        if res_last != alert_last:
            continue
        if (
            res_first == alert_first_resolved
            or alert_first_resolved.startswith(res_first)
            or res_first.startswith(alert_first_resolved)
        ):
            return name

    return None


def matches_author_initials(
    author_name: str,
    researcher_name: str,
) -> bool:
    """Check if a work author name matches a researcher.

    Handles abbreviated forms ("C Shah" -> "Chirag Shah"),
    multi-initial blocks ("BCG Lee" -> "Benjamin Charles Germain Lee"),
    full names ("Shahan Ali Memon" -> "Shahan Ali Memon"),
    and trailing ellipsis ("B Wen...").

    Args:
        author_name: Name from work_authors table.
        researcher_name: Full researcher name from researchers table.

    Returns:
        True if the names match.
    """
    cleaned = author_name.replace("\u2026", "").rstrip(".").strip()
    parts = cleaned.split()
    if len(parts) < 2:
        return False

    res_parts = researcher_name.split()
    if len(res_parts) < 2:
        return False

    if parts[-1].lower() != res_parts[-1].lower():
        return False

    given = parts[:-1]
    res_given = res_parts[:-1]

    # Abbreviated initials: single token, all alpha, up to 4 chars.
    # Author initials may include middle names absent from the DB
    # (e.g. "JD West" for "Jevin West", "KX Mei" for "Katelyn Mei"),
    # so check that author initials START with expected initials.
    if len(given) == 1 and given[0].isalpha() and len(given[0]) <= 4:
        expected = "".join(n[0].lower() for n in res_given)
        if given[0].lower().startswith(expected):
            return True

    # Full or partial name: compare first given-name tokens
    return given[0].lower() == res_given[0].lower()


def link_scholar_works(db_path: str) -> int:
    """Link orphaned scholar-alert works to researchers.

    Finds works ingested from scholar alerts that have no
    researcher_works linkage, resolves the researcher from the
    alert email subject, validates against work_authors, and
    inserts the linkages.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Number of new researcher_works linkages created.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        researchers: dict[str, int] = {
            row[1]: row[0] for row in conn.execute("SELECT id, name FROM researchers")
        }
        researcher_names = list(researchers.keys())

        rows = conn.execute(
            """
            SELECT DISTINCT
                   sai.work_id,
                   REPLACE(sae.subject, ' - new articles', '')
            FROM scholar_alert_items sai
            JOIN scholar_alert_emails sae
                ON sai.message_id = sae.message_id
            LEFT JOIN researcher_works rw
                ON sai.work_id = rw.work_id
            WHERE rw.work_id IS NULL
              AND sai.work_id IS NOT NULL
            """
        ).fetchall()

        if not rows:
            logger.info("No orphaned scholar-alert works found")
            return 0

        # Group alert names by work_id
        alerts_by_work: dict[int, list[str]] = {}
        for work_id, alert_name in rows:
            alerts_by_work.setdefault(work_id, []).append(alert_name)

        logger.info(
            "Found %d orphaned scholar-alert works", len(alerts_by_work)
        )

        orphan_ids = list(alerts_by_work.keys())
        placeholders = ",".join("?" * len(orphan_ids))
        author_rows = conn.execute(
            f"SELECT work_id, author_name FROM work_authors "
            f"WHERE work_id IN ({placeholders})",
            orphan_ids,
        ).fetchall()

        authors_by_work: dict[int, list[str]] = {}
        for work_id, author_name in author_rows:
            authors_by_work.setdefault(work_id, []).append(author_name)

        linkages: list[tuple[int, int]] = []
        for work_id, alert_names in alerts_by_work.items():
            work_authors = authors_by_work.get(work_id, [])

            for alert_name in alert_names:
                matched = match_alert_name_to_researcher(alert_name, researcher_names)
                if matched is None:
                    logger.warning(
                        "No researcher match for alert '%s' (work %d)",
                        alert_name,
                        work_id,
                    )
                    continue

                if work_authors and not any(
                    matches_author_initials(a, matched) for a in work_authors
                ):
                    logger.debug(
                        "Author validation failed for '%s' on work %d (authors: %s)",
                        matched,
                        work_id,
                        work_authors,
                    )
                    continue

                linkages.append((researchers[matched], work_id))

        if not linkages:
            logger.info("No new linkages to create")
            return 0

        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO researcher_works "
            "(researcher_id, work_id) VALUES (?, ?)",
            linkages,
        )
        conn.commit()
        count = conn.total_changes - before
        logger.info("Created %d researcher_works linkages", count)
        return count


def link_coauthors(db_path: str, since_days: int = 7) -> int:
    """Link newly added works to DSCO co-authors who were not flagged.

    A scholar alert links a work only to the researcher named in the alert
    subject, and an API sync links it only to the researcher whose ID was
    queried. When a paper is co-authored by several DSCO members, a co-author
    who did not independently surface it (e.g. it is not yet on their Google
    Scholar profile) is never linked and so is omitted from the Slack digest.

    For each recently added work that is already linked to at least one
    researcher, this matches the work's ``work_authors`` against all
    researchers with :func:`matches_author_initials` and inserts any missing
    linkage. It only considers works first seen within ``since_days``, so it
    acts on new papers rather than backfilling the whole database.

    Args:
        db_path: Path to the SQLite database.
        since_days: Only consider works first seen within this many days.

    Returns:
        Number of new researcher_works linkages created.
    """
    since = (datetime.utcnow() - timedelta(days=since_days)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        researchers: list[tuple[int, str]] = list(
            conn.execute("SELECT id, name FROM researchers")
        )

        # Recently added works that already have at least one researcher linked.
        recent_work_ids = [
            row[0]
            for row in conn.execute(
                """
                SELECT DISTINCT rw.work_id
                FROM researcher_works rw
                JOIN works w ON w.id = rw.work_id
                WHERE w.first_seen >= ?
                """,
                (since,),
            )
        ]

        if not recent_work_ids:
            logger.info("No recent linked works to scan for co-authors")
            return 0

        existing: set[tuple[int, int]] = {
            (researcher_id, work_id)
            for researcher_id, work_id in conn.execute(
                "SELECT researcher_id, work_id FROM researcher_works"
            )
        }

        placeholders = ",".join("?" * len(recent_work_ids))
        author_rows = conn.execute(
            f"SELECT work_id, author_name FROM work_authors "
            f"WHERE work_id IN ({placeholders})",
            recent_work_ids,
        ).fetchall()

        authors_by_work: dict[int, list[str]] = {}
        for work_id, author_name in author_rows:
            authors_by_work.setdefault(work_id, []).append(author_name)

        linkages: list[tuple[int, int]] = []
        for work_id, authors in authors_by_work.items():
            for researcher_id, name in researchers:
                if (researcher_id, work_id) in existing:
                    continue
                if any(matches_author_initials(a, name) for a in authors):
                    linkages.append((researcher_id, work_id))
                    existing.add((researcher_id, work_id))
                    logger.info(
                        "Linking co-author '%s' to work %d", name, work_id
                    )

        if not linkages:
            logger.info("No new co-author linkages to create")
            return 0

        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO researcher_works "
            "(researcher_id, work_id) VALUES (?, ?)",
            linkages,
        )
        conn.commit()
        count = conn.total_changes - before
        logger.info("Created %d co-author linkages", count)
        return count


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Link scholar-alert works to researchers"
    )
    parser.add_argument(
        "--db",
        default="pubs.db",
        help="Path to the SQLite database (default: pubs.db)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help=(
            "Co-author linking only considers works first seen within this "
            "many days (default: 7)"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    subject_count = link_scholar_works(args.db)
    coauthor_count = link_coauthors(args.db, since_days=args.days)
    logger.info(
        "Done. %d linkages created (%d from alert subjects, "
        "%d from DSCO co-authors).",
        subject_count + coauthor_count,
        subject_count,
        coauthor_count,
    )


if __name__ == "__main__":
    main()
