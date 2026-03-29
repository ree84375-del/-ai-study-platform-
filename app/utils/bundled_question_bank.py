from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import db
from app.utils.question_bank_metadata import build_normalized_metadata


DEFAULT_DIFFICULTY = 2
SYNC_TABLE = "bundled_question_bank_import"
REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_DIR = REPO_ROOT / "data" / "question_banks"


FIELD_ALIASES = {
    "volume": ["volume", "booklet", "冊別"],
    "category": ["category", "chapter", "類型"],
    "title": ["title", "topic", "篇名"],
    "source_unit": ["source_unit", "來源單元"],
    "content_text": ["content_text", "題目"],
    "option_a": ["option_a", "選項A"],
    "option_b": ["option_b", "選項B"],
    "option_c": ["option_c", "選項C"],
    "option_d": ["option_d", "選項D"],
    "correct_answer": ["correct_answer", "正確答案"],
    "explanation": ["explanation", "解析"],
    "difficulty": ["difficulty", "難度"],
}


@dataclass(frozen=True)
class BundledQuestionBank:
    subject: str
    csv_name: str
    expected_total: int

    @property
    def csv_path(self) -> Path:
        return BUNDLED_DIR / self.csv_name


BUNDLED_QUESTION_BANKS = (
    BundledQuestionBank(subject="國文", csv_name="chinese.csv", expected_total=6791),
    BundledQuestionBank(subject="英文", csv_name="english.csv", expected_total=2075),
    BundledQuestionBank(subject="數學", csv_name="math.csv", expected_total=3296),
    BundledQuestionBank(subject="地理", csv_name="geography.csv", expected_total=2119),
    BundledQuestionBank(subject="歷史", csv_name="history.csv", expected_total=2430),
    BundledQuestionBank(subject="公民", csv_name="civics.csv", expected_total=2304),
    BundledQuestionBank(subject="生物", csv_name="biology.csv", expected_total=1801),
    BundledQuestionBank(subject="理化", csv_name="integrated_science.csv", expected_total=3249),
    BundledQuestionBank(subject="地科", csv_name="earth_science.csv", expected_total=604),
)


def normalize_question_text(text: str) -> str:
    return " ".join((text or "").replace("\u3000", " ").replace("\xa0", " ").split())


def get_value(row: dict[str, str], field_name: str) -> str:
    for key in FIELD_ALIASES.get(field_name, [field_name]):
        value = row.get(key)
        if value:
            return value
    return ""


def build_category(row: dict[str, str]) -> str:
    metadata = build_normalized_metadata(
        subject_label="",
        volume=get_value(row, "volume").strip(),
        category=get_value(row, "category").strip(),
        title=get_value(row, "title").strip(),
        source_unit=get_value(row, "source_unit").strip(),
    )
    return metadata["category"]


def build_tags(row: dict[str, str]) -> str:
    metadata = build_normalized_metadata(
        subject_label="",
        volume=get_value(row, "volume").strip(),
        category=get_value(row, "category").strip(),
        title=get_value(row, "title").strip(),
        source_unit=get_value(row, "source_unit").strip(),
    )
    return metadata["tags"]


def get_difficulty(row: dict[str, str]) -> int:
    raw = get_value(row, "difficulty").strip()
    if raw.isdigit():
        difficulty = int(raw)
        if 1 <= difficulty <= 5:
            return difficulty
    return DEFAULT_DIFFICULTY


def validate_row(row: dict[str, str]) -> tuple[bool, str]:
    question_text = normalize_question_text(get_value(row, "content_text"))
    if not question_text:
        return False, "empty_question"

    correct_answer = get_value(row, "correct_answer").strip().upper()
    if correct_answer not in {"A", "B", "C", "D"}:
        return False, "invalid_answer"

    options = {
        "A": get_value(row, "option_a").strip(),
        "B": get_value(row, "option_b").strip(),
        "C": get_value(row, "option_c").strip(),
        "D": get_value(row, "option_d").strip(),
    }
    present_options = [key for key, value in options.items() if value]
    if len(present_options) < 2:
        return False, "too_few_options"
    if not options.get(correct_answer):
        return False, "missing_correct_option"

    return True, question_text


def ensure_sync_table() -> None:
    db.session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {SYNC_TABLE} (
                subject VARCHAR(50) PRIMARY KEY,
                csv_name VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'complete',
                row_count INTEGER NOT NULL DEFAULT 0,
                synced_at TIMESTAMP NULL
            )
            """
        )
    )
    db.session.commit()


def compute_checksum(csv_path: Path) -> str:
    digest = hashlib.sha256()
    with csv_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_sync_row(subject: str) -> dict[str, object] | None:
    row = db.session.execute(
        text(
            f"""
            SELECT subject, csv_name, checksum, status, row_count, synced_at
            FROM {SYNC_TABLE}
            WHERE subject = :subject
            """
        ),
        {"subject": subject},
    ).mappings().first()
    return dict(row) if row else None


def mark_sync_state(subject: str, csv_name: str, checksum: str, status: str, row_count: int = 0) -> None:
    payload = {
        "subject": subject,
        "csv_name": csv_name,
        "checksum": checksum,
        "status": status,
        "row_count": row_count,
        "synced_at": datetime.now(timezone.utc),
    }
    updated = db.session.execute(
        text(
            f"""
            UPDATE {SYNC_TABLE}
            SET csv_name = :csv_name,
                checksum = :checksum,
                status = :status,
                row_count = :row_count,
                synced_at = :synced_at
            WHERE subject = :subject
            """
        ),
        payload,
    )
    if updated.rowcount == 0:
        db.session.execute(
            text(
                f"""
                INSERT INTO {SYNC_TABLE} (subject, csv_name, checksum, status, row_count, synced_at)
                VALUES (:subject, :csv_name, :checksum, :status, :row_count, :synced_at)
                """
            ),
            payload,
        )
    db.session.commit()


def load_existing_questions(subject: str) -> set[str]:
    from app.models import Question

    rows = Question.query.filter_by(subject=subject).with_entities(Question.content_text).all()
    return {normalize_question_text(row[0]) for row in rows if row[0]}


def get_subject_count(subject: str) -> int:
    from app.models import Question

    return Question.query.filter_by(subject=subject).count()


def import_csv_to_current_db(csv_path: Path, subject: str) -> dict[str, int]:
    from app.models import Question

    summary = {
        "inserted": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "skipped_empty": 0,
    }
    existing_questions = load_existing_questions(subject)
    batch: list[dict[str, object]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            valid, result = validate_row(row)
            if not valid:
                if result == "empty_question":
                    summary["skipped_empty"] += 1
                else:
                    summary["skipped_invalid"] += 1
                continue

            normalized_question = result
            if normalized_question in existing_questions:
                summary["skipped_duplicate"] += 1
                continue

            batch.append(
                {
                    "subject": subject,
                    "category": build_category(row),
                    "content_text": get_value(row, "content_text").strip(),
                    "option_a": get_value(row, "option_a").strip(),
                    "option_b": get_value(row, "option_b").strip(),
                    "option_c": get_value(row, "option_c").strip(),
                    "option_d": get_value(row, "option_d").strip(),
                    "correct_answer": get_value(row, "correct_answer").strip().upper(),
                    "explanation": get_value(row, "explanation").strip(),
                    "tags": build_tags(row),
                    "difficulty": get_difficulty(row),
                }
            )
            existing_questions.add(normalized_question)
            summary["inserted"] += 1

            if len(batch) >= 500:
                db.session.bulk_insert_mappings(Question, batch)
                db.session.commit()
                batch.clear()

    if batch:
        db.session.bulk_insert_mappings(Question, batch)
        db.session.commit()

    return summary


def sync_bundled_question_bank(bank: BundledQuestionBank, logger=None, force: bool = False) -> dict[str, object]:
    ensure_sync_table()

    if not bank.csv_path.exists():
        raise FileNotFoundError(f"Bundled CSV not found: {bank.csv_path}")

    checksum = compute_checksum(bank.csv_path)
    current_count = get_subject_count(bank.subject)
    sync_row = fetch_sync_row(bank.subject)

    if (
        not force
        and sync_row
        and sync_row.get("checksum") == checksum
        and sync_row.get("status") == "complete"
        and current_count >= bank.expected_total
    ):
        return {
            "subject": bank.subject,
            "status": "skipped",
            "count": current_count,
            "inserted": 0,
        }

    mark_sync_state(bank.subject, bank.csv_name, checksum, status="syncing", row_count=current_count)
    if logger:
        logger.info("Syncing bundled question bank: %s", bank.subject)

    summary = import_csv_to_current_db(bank.csv_path, bank.subject)
    final_count = get_subject_count(bank.subject)
    mark_sync_state(bank.subject, bank.csv_name, checksum, status="complete", row_count=final_count)

    result = {
        "subject": bank.subject,
        "status": "synced",
        "count": final_count,
        **summary,
    }
    if logger:
        logger.info(
            "Bundled question bank synced: %s inserted=%s count=%s",
            bank.subject,
            summary["inserted"],
            final_count,
        )
    return result


def dedupe_questions_by_exact_text(logger=None, chunk_size: int = 500) -> dict[str, int]:
    from app.models import Question

    duplicates_by_key: dict[tuple[str, str], list[int]] = {}
    for question_id, subject, content_text in db.session.query(
        Question.id,
        Question.subject,
        Question.content_text,
    ).order_by(Question.id.asc()):
        normalized_text = normalize_question_text(content_text)
        if not normalized_text:
            continue
        key = ((subject or "").strip(), normalized_text)
        duplicates_by_key.setdefault(key, []).append(question_id)

    delete_ids: list[int] = []
    for ids in duplicates_by_key.values():
        if len(ids) > 1:
            delete_ids.extend(ids[1:])

    deleted = 0
    for start in range(0, len(delete_ids), chunk_size):
        batch_ids = delete_ids[start:start + chunk_size]
        if not batch_ids:
            continue
        deleted += db.session.query(Question).filter(Question.id.in_(batch_ids)).delete(synchronize_session=False)
        db.session.commit()

    summary = {
        "duplicate_groups": sum(1 for ids in duplicates_by_key.values() if len(ids) > 1),
        "deleted_rows": deleted,
    }
    if logger and deleted:
        logger.info(
            "Removed duplicate questions by exact text: groups=%s deleted=%s",
            summary["duplicate_groups"],
            summary["deleted_rows"],
        )
    return summary


def seed_bundled_question_banks(logger=None, force: bool = False) -> list[dict[str, object]]:
    results = []
    for bank in BUNDLED_QUESTION_BANKS:
        try:
            results.append(sync_bundled_question_bank(bank, logger=logger, force=force))
        except Exception:
            if logger:
                logger.exception("Bundled question bank sync failed: %s", bank.subject)
            else:
                raise
    return results
