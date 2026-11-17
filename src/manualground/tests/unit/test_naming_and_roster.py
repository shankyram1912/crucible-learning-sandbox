"""Unit tests for slug normalization, GCP resource length bounds, duplicate detection, and CSV roster loading."""

from __future__ import annotations

from pathlib import Path

import pytest


MG_ROOT = Path(__file__).resolve().parents[2]


def _load_roster(csv_path: Path):
    """Invoke the canonical CSV roster loader exposed by ``manualground.core.naming`` (or ``models``)."""
    from manualground.core import naming

    for fn_name in ("load_roster_csv", "load_roster", "parse_roster_csv", "read_roster_csv"):
        fn = getattr(naming, fn_name, None)
        if callable(fn):
            return fn(csv_path)
    raise AssertionError(
        "manualground.core.naming must expose a CSV roster loader (e.g. load_roster_csv(path))"
    )


def test_email_to_slug_normalization() -> None:
    from manualground.core.naming import email_to_slug

    assert email_to_slug("lsb-student1@shankyram.altostrat.com") == "lsb-student1"
    assert email_to_slug("  Alice.Tan_2026@E.NTU.EDU.SG ") == "alice-tan-2026"

    # Consecutive punctuation collapses to a single hyphen with no leading/trailing hyphens
    slug_punct = email_to_slug("..Bob__Lee--Lab01..@ntu.edu.sg")
    assert "--" not in slug_punct
    assert not slug_punct.startswith("-")
    assert not slug_punct.endswith("-")
    assert slug_punct.replace("-", "").isalnum()
    assert slug_punct == slug_punct.lower()

    # Numeric-leading local parts remain valid lowercase slugs usable across GCP identifiers
    slug_num = email_to_slug("99student@ntu.edu.sg")
    assert slug_num
    assert slug_num == slug_num.lower()
    assert not slug_num.startswith("-")


def test_student_spec_30_char_sa_truncation_and_sql_iam_format() -> None:
    from manualground.core.models import StudentSpec

    short = StudentSpec(email="lsb-student1@shankyram.altostrat.com", slug="lsb-student1")
    assert short.sa_id() == "sa-lsb-student1"
    assert 6 <= len(short.sa_id()) <= 30
    assert short.sa_email("mg-ntu-01") == "sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com"
    # Cloud SQL IAM service account login MUST strip the .gserviceaccount.com suffix!
    assert short.sql_iam_sa_user("mg-ntu-01") == "sa-lsb-student1@mg-ntu-01.iam"
    assert not short.sql_iam_sa_user("mg-ntu-01").endswith(".gserviceaccount.com")

    # Craft a slug where index 29 of f"sa-{slug}" falls directly on a hyphen ("sa-" = 3 + 26 'a's + '-')
    hyphen_boundary_slug = ("a" * 26) + "-trailing-part-exceeding-thirty-chars"
    long_student = StudentSpec(
        email="verylongstudent@shankyram.altostrat.com",
        slug=hyphen_boundary_slug,
    )
    sa_id = long_student.sa_id()
    assert len(sa_id) <= 30
    assert not sa_id.endswith("-"), f"sa_id() left trailing hyphen after 30-char slice: {sa_id!r}"
    assert sa_id.startswith("sa-")


def test_student_spec_63_char_bucket_and_db_bounds() -> None:
    from manualground.core.models import StudentSpec

    # Long project ID (30 chars) + long slug (45 chars) would exceed 63-char GCS bucket & Firestore DB caps
    long_project = "ntu-ai-playground-shard-prod01"
    # Choose slug length so 63rd character of f"bkt-{long_project}-{slug}" lands on a '-'
    prefix_len = len(f"bkt-{long_project}-")  # 35 chars -> 27 chars + '-' hits index 62 (63rd char!)
    long_slug = ("x" * (62 - prefix_len)) + "-" + ("y" * 35) + "-" + ("z" * 20)

    st = StudentSpec(email="longslug@ntu.edu.sg", slug=long_slug)

    bkt = st.bucket_name(long_project)
    assert len(bkt) <= 63
    assert not bkt.endswith("-"), f"bucket_name left trailing hyphen: {bkt!r}"
    assert bkt.startswith(f"bkt-{long_project}-")

    fs_db = st.firestore_db_id()
    assert len(fs_db) <= 63
    assert not fs_db.endswith("-"), f"firestore_db_id left trailing hyphen: {fs_db!r}"
    assert fs_db.startswith("fs-")

    # SQL identifiers replace hyphens with underscores and stay <= 63 bytes for PostgreSQL NAMEDATALEN
    sql_st = StudentSpec(email="lsb-student1@shankyram.altostrat.com", slug="lsb-student1")
    assert sql_st.sql_db_name() == "db_lsb_student1"
    assert sql_st.sql_role_name() == "role_lsb_student1"
    assert "-" not in sql_st.sql_db_name()
    assert "-" not in sql_st.sql_role_name()
    assert sql_st.ar_repo_id() == "ar-lsb-student1"
    assert sql_st.search_datastore_id() == "ds-lsb-student1"
    assert sql_st.search_engine_id() == "eng-lsb-student1"


def test_sample_roster_csv_loads_cleanly() -> None:
    sample_csv = MG_ROOT / "rosters" / "sample-2students.csv"
    assert sample_csv.is_file(), f"Missing sample roster CSV: {sample_csv}"

    students = _load_roster(sample_csv)
    assert len(students) == 2
    emails = [s.email for s in students]
    assert "lsb-student1@shankyram.altostrat.com" in emails
    assert "lsb-student2@shankyram.altostrat.com" in emails
    slugs = [s.slug for s in students]
    assert "lsb-student1" in slugs
    assert "lsb-student2" in slugs


def test_csv_loader_detects_duplicate_emails_and_slug_or_sa_collisions(tmp_path: Path) -> None:
    # 1. Case-insensitive duplicate email
    dup_email_csv = tmp_path / "dup_email.csv"
    dup_email_csv.write_text(
        "email,display_name\n"
        "Alice.Tan@ntu.edu.sg,Alice One\n"
        "alice.tan@NTU.EDU.SG,Alice Two\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _load_roster(dup_email_csv)

    # 2. Distinct emails whose normalized slugs collide (alice.tan vs alice_tan)
    dup_slug_csv = tmp_path / "dup_slug.csv"
    dup_slug_csv.write_text(
        "email,display_name\n"
        "alice.tan@ntu.edu.sg,Alice Dot\n"
        "alice_tan@ntu.edu.sg,Alice Underscore\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _load_roster(dup_slug_csv)

    # 3. Distinct slugs that collide after 30-char sa_id() truncation!
    shared_27 = "christopher-alexander-tan01"  # "sa-" + 27 chars = 30 chars!
    dup_sa_csv = tmp_path / "dup_sa.csv"
    dup_sa_csv.write_text(
        "email,display_name\n"
        f"{shared_27}-alpha@ntu.edu.sg,Chris Alpha\n"
        f"{shared_27}-bravo@ntu.edu.sg,Chris Bravo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _load_roster(dup_sa_csv)

    # 4. Malformed email rejected
    bad_email_csv = tmp_path / "bad_email.csv"
    bad_email_csv.write_text(
        "email,display_name\nnot-an-email,Bad User\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _load_roster(bad_email_csv)
