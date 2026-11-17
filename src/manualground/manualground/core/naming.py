"""Slug normalization, resource bound helpers, and CSV roster loader."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manualground.core.models import StudentSpec

_EMAIL_RE = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$"
)
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

EMAIL_COLUMNS = ("email", "student_email", "user_email", "mail")
SLUG_COLUMNS = ("slug", "student_slug")
DISPLAY_NAME_COLUMNS = ("display_name", "name", "full_name", "student_name")


class RosterValidationError(ValueError):
    """Raised when a student email, slug, or roster CSV is invalid or collides."""


def validate_email(email: str) -> str:
    """Validate and normalize an email address to lowercase."""
    cleaned = email.strip().lower()
    if not cleaned or not _EMAIL_RE.match(cleaned):
        raise RosterValidationError(f"Invalid student email address: {email!r}")
    return cleaned


def normalize_slug(raw: str, max_length: int = 80) -> str:
    """Normalize an arbitrary identifier into a lowercase hyphenated GCP-safe slug."""
    cleaned = _NON_SLUG_RE.sub("-", raw.strip().lower()).strip("-")
    if max_length > 0:
        cleaned = cleaned[:max_length].rstrip("-")
    if not cleaned:
        raise RosterValidationError(f"Cannot derive a non-empty student slug from {raw!r}")
    return cleaned


def email_to_slug(email: str) -> str:
    """Derive a canonical student slug from a validated student email local-part."""
    normalized_email = validate_email(email)
    local_part, _ = normalized_email.split("@", 1)
    return normalize_slug(local_part)


def sa_email_to_slug(sa_email: str) -> str:
    """Extract student slug from sa-<slug>@<project>.iam.gserviceaccount.com if matching."""
    local_part = sa_email.strip().lower().split("@", 1)[0]
    if local_part.startswith("sa-") and len(local_part) > 3:
        return local_part[3:]
    return normalize_slug(local_part)


def validate_roster(students: Sequence[StudentSpec]) -> list[StudentSpec]:
    """Verify non-empty roster with zero duplicate emails, slugs, or 30-char SA IDs."""
    if not students:
        raise RosterValidationError("Student roster is empty.")

    seen_emails: dict[str, int] = {}
    seen_slugs: dict[str, str] = {}
    seen_sa_ids: dict[str, str] = {}
    validated: list[StudentSpec] = []

    for idx, student in enumerate(students, start=1):
        if student.email in seen_emails:
            raise RosterValidationError(
                f"Duplicate student email {student.email!r} at roster entry {idx} "
                f"(already seen at entry {seen_emails[student.email]})."
            )
        seen_emails[student.email] = idx

        if student.slug in seen_slugs:
            raise RosterValidationError(
                f"Duplicate student slug {student.slug!r} for {student.email!r} "
                f"(collides with {seen_slugs[student.slug]!r})."
            )
        seen_slugs[student.slug] = student.email

        sa_id = student.sa_id()
        if len(sa_id) < 6:
            raise RosterValidationError(
                f"Derived service account ID {sa_id!r} for {student.email!r} is shorter "
                "than GCP's 6-character minimum."
            )
        if sa_id in seen_sa_ids:
            raise RosterValidationError(
                f"Truncated 30-char service account ID {sa_id!r} for {student.email!r} "
                f"collides with {seen_sa_ids[sa_id]!r}."
            )
        seen_sa_ids[sa_id] = student.email
        validated.append(student)

    return validated


def parse_roster_csv(content: str) -> list[StudentSpec]:
    """Parse CSV text into a validated list of StudentSpec models."""
    from manualground.core.models import StudentSpec

    lines = [
        line
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise RosterValidationError("Roster CSV contains no student rows.")

    reader = csv.reader(io.StringIO("\n".join(lines)))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise RosterValidationError("Roster CSV contains no student rows.")

    first_row = [cell.strip() for cell in rows[0]]
    lower_header = [cell.lower() for cell in first_row]

    email_col_idx: int | None = None
    slug_col_idx: int | None = None
    name_col_idx: int | None = None

    for candidate in EMAIL_COLUMNS:
        if candidate in lower_header:
            email_col_idx = lower_header.index(candidate)
            break

    has_header = email_col_idx is not None
    if has_header:
        for candidate in SLUG_COLUMNS:
            if candidate in lower_header:
                slug_col_idx = lower_header.index(candidate)
                break
        for candidate in DISPLAY_NAME_COLUMNS:
            if candidate in lower_header:
                name_col_idx = lower_header.index(candidate)
                break
        data_rows = rows[1:]
    else:
        if "@" not in first_row[0]:
            raise RosterValidationError(
                "Roster CSV header is missing an 'email' (or 'student_email') column."
            )
        email_col_idx = 0
        name_col_idx = 1 if len(first_row) > 1 else None
        data_rows = rows

    students: list[StudentSpec] = []
    for row_num, row in enumerate(data_rows, start=2 if has_header else 1):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if email_col_idx is None or email_col_idx >= len(cells) or not cells[email_col_idx]:
            raise RosterValidationError(f"Missing student email on CSV row {row_num}.")
        email = cells[email_col_idx]
        slug = (
            cells[slug_col_idx]
            if slug_col_idx is not None and slug_col_idx < len(cells)
            else ""
        )
        display_name = (
            cells[name_col_idx]
            if name_col_idx is not None and name_col_idx < len(cells)
            else ""
        )
        students.append(
            StudentSpec(
                email=email,
                slug=slug,
                display_name=display_name,
            )
        )

    return validate_roster(students)


def load_roster_csv(path: Path | str) -> list[StudentSpec]:
    """Load and validate a student roster CSV from disk."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise RosterValidationError(f"Roster CSV file not found: {csv_path}")
    return parse_roster_csv(csv_path.read_text(encoding="utf-8"))
