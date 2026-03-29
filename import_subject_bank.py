from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from app import create_app, db
from app.models import Question


DEFAULT_DIFFICULTY = 2


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


def build_category(row: dict[str, str]) -> str:
    volume = (row.get("冊別") or "").strip()
    category = (row.get("類型") or row.get("單元/類別") or "").strip()
    if volume and category:
        return f"{volume}_{category}"[:100]
    return (category or volume)[:100]


def build_tags(row: dict[str, str]) -> str:
    parts = [
        (row.get("篇名") or "").strip(),
        (row.get("來源單元") or "").strip(),
    ]
    cleaned = [part for part in parts if part]
    return " | ".join(cleaned)[:100]


def get_difficulty(row: dict[str, str]) -> int:
    raw = (row.get("難度") or "").strip()
    if raw.isdigit():
        difficulty = int(raw)
        if 1 <= difficulty <= 5:
            return difficulty
    return DEFAULT_DIFFICULTY


def load_existing_questions(subject: str) -> set[str]:
    existing_rows = Question.query.filter_by(subject=subject).with_entities(Question.content_text).all()
    return {normalize_question_text(row[0]) for row in existing_rows if row[0]}


def validate_row(row: dict[str, str]) -> tuple[bool, str]:
    question_text = normalize_question_text(row.get("題目") or row.get("content_text") or "")
    if not question_text:
        return False, "empty_question"

    correct_answer = (row.get("正確答案") or row.get("correct_answer") or "").strip().upper()
    if correct_answer not in {"A", "B", "C", "D"}:
        return False, "invalid_answer"

    options = {
        "A": (row.get("選項A") or row.get("option_a") or "").strip(),
        "B": (row.get("選項B") or row.get("option_b") or "").strip(),
        "C": (row.get("選項C") or row.get("option_c") or "").strip(),
        "D": (row.get("選項D") or row.get("option_d") or "").strip(),
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
                content_text=(row.get("題目") or row.get("content_text") or "").strip(),
                option_a=(row.get("選項A") or row.get("option_a") or "").strip(),
                option_b=(row.get("選項B") or row.get("option_b") or "").strip(),
                option_c=(row.get("選項C") or row.get("option_c") or "").strip(),
                option_d=(row.get("選項D") or row.get("option_d") or "").strip(),
                correct_answer=(row.get("正確答案") or row.get("correct_answer") or "").strip().upper(),
                explanation=(row.get("解析") or row.get("explanation") or "").strip(),
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
