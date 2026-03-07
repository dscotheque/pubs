"""Send Slack notifications for recently discovered DSCO publications.

Queries pubs.db directly and posts a formatted digest to Slack.
Replaces `labpubs notify` to give full control over message formatting.
"""

import argparse
import html
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DB_PATH = "pubs.db"


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode HTML entities.

    Handles double-encoded entities like ``&amp;amp;`` by unescaping
    repeatedly until the text stabilizes.

    Args:
        text: Raw text potentially containing HTML markup.

    Returns:
        Clean plain text.
    """
    text = _HTML_TAG_RE.sub("", text)
    prev = None
    while text != prev:
        prev = text
        text = html.unescape(text)
    return text


def _get_new_works(db_path: str, days: int) -> list[dict]:
    """Query publications first seen within the last N days.

    Args:
        db_path: Path to the SQLite database.
        days: Look-back window in days.

    Returns:
        List of dicts with title, year, venue, doi, oa_url, researchers.
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Get works with researcher names from researcher_works (API sync)
        # and fall back to scholar_alert_emails subjects (Scholar ingestion)
        rows = conn.execute(
            """SELECT w.id, w.doi, w.title, w.year, w.venue,
                      w.open_access_url
               FROM works w
               WHERE w.first_seen >= ?
               ORDER BY w.first_seen DESC""",
            (since,),
        ).fetchall()

        works: list[dict] = []
        for row in rows:
            work = dict(row)
            work_id = work.pop("id")

            # Try researcher_works first (OpenAlex/Crossref sync)
            researcher_rows = conn.execute(
                """SELECT DISTINCT r.name
                   FROM researchers r
                   JOIN researcher_works rw ON rw.researcher_id = r.id
                   WHERE rw.work_id = ?""",
                (work_id,),
            ).fetchall()

            if researcher_rows:
                work["researchers"] = ", ".join(
                    r["name"] for r in researcher_rows
                )
            else:
                # Fall back to Scholar alert email subjects
                alert_rows = conn.execute(
                    """SELECT DISTINCT sae.subject
                       FROM scholar_alert_items sai
                       JOIN scholar_alert_emails sae
                         ON sae.message_id = sai.message_id
                       WHERE sai.work_id = ?""",
                    (work_id,),
                ).fetchall()
                names = []
                for ar in alert_rows:
                    subject = ar["subject"] or ""
                    # Subject format: "Researcher Name - new articles"
                    if " - " in subject:
                        names.append(subject.split(" - ")[0].strip())
                work["researchers"] = ", ".join(names)

            works.append(work)
        return works
    finally:
        conn.close()


def _format_message(works: list[dict]) -> str:
    """Format works into a Slack mrkdwn message.

    Args:
        works: List of work dicts from _get_new_works.

    Returns:
        Formatted Slack message string.
    """
    lines = [f"*New DSCO publications ({len(works)}):*"]

    for work in works:
        title = _strip_html(work["title"])

        # Title as a clickable bold link
        if work["doi"]:
            link = f"https://doi.org/{work['doi']}"
            title_line = f"*<{link}|{title}>*"
        elif work["open_access_url"]:
            title_line = f"*<{work['open_access_url']}|{title}>*"
        else:
            title_line = f"*{title}*"

        # Metadata line: Researcher(s)  |  Venue  |  Year
        year = str(work["year"]) if work["year"] else "forthcoming"
        venue = work["venue"] or ""
        researchers = work["researchers"] or ""

        meta_parts: list[str] = []
        if researchers:
            meta_parts.append(researchers)
        if venue:
            meta_parts.append(venue)
        meta_parts.append(year)

        lines.append(f"{title_line}\n{'  |  '.join(meta_parts)}")

    return "\n\n".join(lines)


def _send_slack(webhook_url: str, message: str) -> bool:
    """POST a message to a Slack incoming webhook.

    Args:
        webhook_url: Slack webhook URL.
        message: Formatted message text.

    Returns:
        True if the message was sent successfully.
    """
    try:
        response = httpx.post(
            webhook_url, json={"text": message}, timeout=10.0
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send Slack notification")
        return False


def main() -> None:
    """Entry point for the notification script."""
    parser = argparse.ArgumentParser(
        description="Send Slack digest of new DSCO publications."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Look-back window in days (default: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the message without sending to Slack.",
    )
    args = parser.parse_args()

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url and not args.dry_run:
        logger.error("SLACK_WEBHOOK_URL is not set")
        sys.exit(1)

    works = _get_new_works(_DB_PATH, args.days)
    if not works:
        print("No new publications to notify about.")
        return

    message = _format_message(works)

    if args.dry_run:
        print(message)
        return

    if _send_slack(webhook_url, message):
        print(f"Notified Slack about {len(works)} new publications.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
