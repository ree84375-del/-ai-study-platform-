from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from app import create_app, db
from app.models import Question
from app.utils.question_bank_metadata import build_normalized_metadata


DEFAULT_DIFFICULTY = 2

FIELD_ALIASES = {
    "volume": ["volume", "booklet", "?"],
    "category": ["category", "chapter", "憿?", "?桀?/憿"],
    "title": ["title", "topic", "蝭?"],
    "source_unit": ["source_unit", "靘??桀?"],
    "content_text": ["content_text", "憿"],
    "option_a": ["option_a", "?賊?A"],
    "option_b": ["option_b", "?賊?B"],
    "option_c": ["option_c", "?賊?C"],
    "option_d": ["option_d", "?賊?D"],
    "correct_answer": ["correct_answer", "甇?Ⅱ蝑?"],
    "explanation": ["explanation", "閫??"],
    "difficulty": ["difficulty", "??漲"],
}


@dataclass
class ImportSummary:
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    skipped_empty: int = 0


def normalize_question_text(text: str) -> str:
    return " ".join((text or "").replace("\u3000", " ").replace("\xa0", " ").split())


def resolve_csv_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    raise ValueError("CSV path is required.")


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


def load_existing_questions(subject: str) -> set[str]:
    existing_rows = Question.query.filter_by(subject=subject).with_entities(Question.content_text).all()
    return {normalize_question_text(row[0]) for row in existing_rows if row[0]}


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


def import_csv(csv_path: Path, subject: str) -> ImportSummary:
    summary = ImportSummary()
    existing_questions = load_existing_questions(subject)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            valid, result = validate_row(row)
            if not valid:
                if result == "empty_question":
                    summary.skipped_empty += 1
                else:
                    summary.skipped_invalid += 1
                continue

            normalized_question = result
            if normalized_question in existing_questions:
                summary.skipped_duplicate += 1
                continue

            question = Question(
                subject=subject,
                category=build_category(row),
                content_text=get_value(row, "content_text").strip(),
                option_a=get_value(row, "option_a").strip(),
                option_b=get_value(row, "option_b").strip(),
                option_c=get_value(row, "option_c").strip(),
                option_d=get_value(row, "option_d").strip(),
                correct_answer=get_value(row, "correct_answer").strip().upper(),
                explanation=get_value(row, "explanation").strip(),
                tags=build_tags(row),
                difficulty=get_difficulty(row),
            )
            db.session.add(question)
            existing_questions.add(normalized_question)
            summary.inserted += 1

            if summary.inserted % 500 == 0:
                db.session.flush()

    db.session.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a cleaned subject CSV into the website question bank.")
    parser.add_argument("--csv", required=True, help="Absolute or relative path to the cleaned CSV file.")
    parser.add_argument("--subject", required=True, help="Question.subject label to store, e.g. 國文 or 英文.")
    args = parser.parse_args()

    app = create_app()
    csv_path = resolve_csv_path(args.csv)

    with app.app_context():
        summary = import_csv(csv_path=csv_path, subject=args.subject.strip())
        total_for_subject = Question.query.filter_by(subject=args.subject.strip()).count()

    print(f"csv={csv_path}")
    print(f"subject={args.subject.strip()}")
    print(f"inserted={summary.inserted}")
    print(f"skipped_duplicate={summary.skipped_duplicate}")
    print(f"skipped_invalid={summary.skipped_invalid}")
    print(f"skipped_empty={summary.skipped_empty}")
    print(f"subject_total={total_for_subject}")


if __name__ == "__main__":
    main()
