from __future__ import annotations

from app import create_app, db
from app.models import Question
from app.utils.question_bank_metadata import build_category_label, build_tags_label, extract_question_hierarchy


GENERAL_PRACTICE_SUBJECTS = {
    "國文",
    "英文",
    "數學",
    "地理",
    "歷史",
    "公民",
    "生物",
    "理化",
    "地科",
}


def normalize_questions() -> tuple[int, int]:
    updated = 0
    skipped = 0

    questions = Question.query.filter(Question.subject.in_(GENERAL_PRACTICE_SUBJECTS)).all()
    for question in questions:
        hierarchy = extract_question_hierarchy(
            category_value=question.category or "",
            tags_value=question.tags or "",
            subject_label=question.subject or "",
        )
        new_category = build_category_label(hierarchy["booklet"], hierarchy["chapter"])
        new_tags = build_tags_label(hierarchy["topic"], hierarchy["booklet"], hierarchy["chapter"])

        if new_category == (question.category or "") and new_tags == (question.tags or ""):
            skipped += 1
            continue

        question.category = new_category
        question.tags = new_tags
        updated += 1

        if updated % 500 == 0:
            db.session.flush()

    db.session.commit()
    return updated, skipped


def main() -> None:
    app = create_app()
    with app.app_context():
        updated, skipped = normalize_questions()
        print(f"updated={updated}")
        print(f"skipped={skipped}")


if __name__ == "__main__":
    main()
