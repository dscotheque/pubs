#!/usr/bin/env python3
"""Add a new researcher to labpubs.yaml from a GitHub issue body.

Reads the issue body from the ISSUE_BODY environment variable, parses
the structured form fields, and appends the researcher to labpubs.yaml
using string insertion so that existing comments and formatting are
preserved.

Outputs RESEARCHER_NAME to GITHUB_OUTPUT so the calling workflow can
pass it to subsequent steps.
"""

import argparse
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

YAML_PATH = Path("labpubs.yaml")
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")
NO_RESPONSE = "_No response_"


def parse_issue_body(body: str) -> dict[str, str | None]:
    """Parse a GitHub issue form body into a dict of field values.

    GitHub issue forms render each field as:

        ### Field Label

        value

    Args:
        body: Raw issue body string from GitHub.

    Returns:
        Dict mapping label text to value string, or None when the
        field was left blank ("_No response_").
    """
    fields: dict[str, str | None] = {}
    pattern = re.compile(
        r"###\s+(.+?)\s*\n\n(.+?)(?=\n\n###|\Z)", re.DOTALL
    )
    for match in pattern.finditer(body):
        label = match.group(1).strip()
        value = match.group(2).strip()
        fields[label] = None if value in (NO_RESPONSE, "") else value
    return fields


def researcher_exists(yaml_text: str, name: str) -> bool:
    """Return True if a researcher with this name is already in the YAML.

    Args:
        yaml_text: Raw contents of labpubs.yaml.
        name: Researcher name to search for.

    Returns:
        True if the name appears as a researchers list entry.
    """
    return f'- name: "{name}"' in yaml_text or f"- name: '{name}'" in yaml_text


def build_researcher_block(
    name: str,
    orcid: str | None,
    openalex_id: str | None,
    role: str,
    start_date: str,
) -> str:
    """Build the YAML block for a new researcher entry.

    Args:
        name: Full researcher name.
        orcid: ORCID identifier or None.
        openalex_id: OpenAlex ID or None.
        role: Role string (faculty/postdoc/student/staff).
        start_date: ISO date string (YYYY-MM-DD) for tracking start.

    Returns:
        Indented YAML block ready to append to the researchers list.
    """
    lines = [f'  - name: "{name}"']
    if orcid:
        lines.append(f'    orcid: "{orcid}"')
    if openalex_id:
        lines.append(f'    openalex_id: "{openalex_id}"')
    lines.append(f'    groups: ["{role}"]')
    lines.append(f'    start_date: "{start_date}"')
    return "\n".join(lines) + "\n"


def build_scholar_map_block(
    name: str,
    scholar_profile_user: str | None,
    alert_subject_prefix: str | None,
) -> str:
    """Build the YAML block for a scholar_alerts.researcher_map entry.

    Args:
        name: Researcher name (must match the researchers list entry).
        scholar_profile_user: Google Scholar profile user ID or None.
        alert_subject_prefix: Alert subject fallback or None.

    Returns:
        Indented YAML block ready to append to researcher_map, or
        empty string if no scholar mapping was provided.
    """
    if not scholar_profile_user and not alert_subject_prefix:
        return ""
    lines = [f'    - researcher_name: "{name}"']
    if scholar_profile_user:
        lines.append(f'      scholar_profile_user: "{scholar_profile_user}"')
    elif alert_subject_prefix:
        lines.append(f'      alert_subject_prefix: "{alert_subject_prefix}"')
    return "\n".join(lines) + "\n"


def insert_researcher(yaml_text: str, researcher_block: str) -> str:
    """Append a researcher block at the end of the researchers list.

    Appends to the end of the file (researchers: is the last top-level
    key in labpubs.yaml).

    Args:
        yaml_text: Raw YAML file contents.
        researcher_block: Formatted YAML block to append.

    Returns:
        Updated YAML text.
    """
    return yaml_text.rstrip("\n") + "\n\n" + researcher_block


def insert_scholar_map(yaml_text: str, map_block: str) -> str:
    """Append a scholar_alerts.researcher_map entry before researchers:.

    Args:
        yaml_text: Raw YAML file contents.
        map_block: Formatted YAML block to append.

    Returns:
        Updated YAML text with map entry inserted.
    """
    marker = "\nresearchers:"
    idx = yaml_text.find(marker)
    if idx == -1:
        # researchers: not found — just append at end before researcher block
        return yaml_text.rstrip("\n") + "\n" + map_block
    return yaml_text[:idx] + "\n" + map_block + yaml_text[idx:]


def set_github_output(key: str, value: str) -> None:
    """Write a key=value pair to GITHUB_OUTPUT if running in Actions.

    Args:
        key: Output variable name.
        value: Output value.
    """
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as fh:
            fh.write(f"{key}={value}\n")
    else:
        # Local fallback: print so caller can capture
        print(f"{key}={value}")


def main() -> None:
    """Parse issue body and update labpubs.yaml."""
    parser = argparse.ArgumentParser(
        description="Add a researcher from a GitHub issue body"
    )
    parser.add_argument(
        "--yaml",
        default=str(YAML_PATH),
        help="Path to labpubs.yaml (default: labpubs.yaml)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    body = os.environ.get("ISSUE_BODY", "")
    if not body:
        logger.error("ISSUE_BODY environment variable is empty")
        sys.exit(1)

    fields = parse_issue_body(body)
    logger.debug("Parsed fields: %s", fields)

    name = fields.get("Full Name")
    if not name:
        logger.error("Full Name field is required but was not found in issue body")
        sys.exit(1)

    orcid = fields.get("ORCID")
    openalex_id = fields.get("OpenAlex ID")
    scholar_profile_user = fields.get("Google Scholar Profile ID")
    alert_subject_prefix = fields.get("Alert Subject Prefix")
    role = fields.get("Role") or "student"
    start_date = date.today().isoformat()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        logger.error("YAML file not found: %s", yaml_path)
        sys.exit(1)

    yaml_text = yaml_path.read_text()

    if researcher_exists(yaml_text, name):
        logger.warning("Researcher '%s' already exists in %s -- skipping", name, yaml_path)
        set_github_output("RESEARCHER_NAME", name)
        set_github_output("ALREADY_EXISTS", "true")
        sys.exit(0)

    researcher_block = build_researcher_block(
        name, orcid, openalex_id, role, start_date
    )
    yaml_text = insert_researcher(yaml_text, researcher_block)

    map_block = build_scholar_map_block(
        name, scholar_profile_user, alert_subject_prefix
    )
    if map_block:
        yaml_text = insert_scholar_map(yaml_text, map_block)

    yaml_path.write_text(yaml_text)
    logger.info(
        "Added '%s' (role=%s, start_date=%s) to %s", name, role, start_date, yaml_path
    )

    set_github_output("RESEARCHER_NAME", name)
    set_github_output("ALREADY_EXISTS", "false")


if __name__ == "__main__":
    main()
