from __future__ import annotations

import argparse
from pathlib import Path

from app import create_app
from app.models import Question
from app.utils.bundled_question_bank import import_csv_to_current_db


def resolve_csv_path(path_arg: str) -> Path:
    csv_path = Path(path_arg).expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a cleaned subject CSV into the website question bank.")
    parser.add_argument("--csv", required=True, help="Absolute or relative path to the cleaned CSV file.")
    parser.add_argument("--subject", required=True, help="Question.subject label to store, e.g. 國文 or 英文.")
    args = parser.parse_args()

    app = create_app()
    csv_path = resolve_csv_path(args.csv)
    subject = args.subject.strip()

    with app.app_context():
        summary = import_csv_to_current_db(csv_path=csv_path, subject=subject)
        total_for_subject = Question.query.filter_by(subject=subject).count()

    print(f"csv={csv_path}")
    print(f"subject={subject}")
    print(f"inserted={summary['inserted']}")
    print(f"skipped_duplicate={summary['skipped_duplicate']}")
    print(f"skipped_invalid={summary['skipped_invalid']}")
    print(f"skipped_empty={summary['skipped_empty']}")
    print(f"subject_total={total_for_subject}")


if __name__ == "__main__":
    main()
