from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import fitz
import requests

from app.utils.document_ingest import (
    DATA_ROOT,
    download_to_path,
    ensure_dir,
    extract_pdf_pages,
    normalize_multiline_text,
    normalize_whitespace,
    render_page_png,
    run_tesseract_on_image,
    save_extraction_docx,
    slugify,
    write_json,
)


CAP_SOURCE_MANIFEST = DATA_ROOT / "cap_review" / "cap_manifest.json"
CAP_SOURCE_ROOT = DATA_ROOT / "cap_practice_sources"
CAP_WORD_ROOT = DATA_ROOT / "cap_practice_word"
CAP_STRUCTURED_ROOT = DATA_ROOT / "cap_practice_structured"
CAP_LIBRARY_MANIFEST = DATA_ROOT / "cap_review" / "cap_practice_manifest.json"

OFFICIAL_QUESTION_COUNT_OVERRIDES = {
    "102": {"chinese": 48, "english": 40, "math": 25, "social": 63, "science": 54},
    "103": {"chinese": 48, "english": 40, "math": 27, "social": 63, "science": 54},
}

SUBJECT_LABELS = {
    "chinese": "國文",
    "english": "英語",
    "math": "數學",
    "social": "社會",
    "science": "自然",
}
ANSWER_SEQUENCE_MAP = {
    6: {
        6: ["chinese", "english", "english_listening", "math", "social", "science"],
        5: ["chinese", "english", "math", "social", "science"],
        4: ["chinese", "english", "social", "science"],
        3: ["english", "social", "science"],
        2: ["social", "science"],
        1: ["social"],
    },
    5: {
        5: ["chinese", "english", "math", "social", "science"],
        4: ["chinese", "english", "social", "science"],
        3: ["english", "social", "science"],
        2: ["social", "science"],
        1: ["social"],
    },
}
OPTION_MARKERS = {
    "": "(A)",
    "": "(B)",
    "": "(C)",
    "": "(D)",
    "（A）": "(A)",
    "（B）": "(B)",
    "（C）": "(C)",
    "（D）": "(D)",
}


def load_cap_manifest() -> dict:
    import json

    return json.loads(CAP_SOURCE_MANIFEST.read_text(encoding="utf-8"))


def normalize_answer_token(text: str) -> str:
    token = normalize_whitespace(text).upper()
    token = token.replace("（", "(").replace("）", ")")
    token = token.strip(".、)")
    if token in {"A", "B", "C", "D"}:
        return token
    if token in {"(A)", "(B)", "(C)", "(D)"}:
        return token[1]
    if token and token[0] in {"A", "B", "C", "D"}:
        return token[0]
    return ""


def normalize_answer_number(number: int, previous_number: int | None) -> int:
    if previous_number is None:
        return number
    if number == previous_number + 1:
        return number
    if number <= previous_number:
        for delta in (10, 20, 30):
            if number + delta == previous_number + 1:
                return number + delta
    return number


def iterate_answer_tokens(text: str) -> list[str]:
    tokens = []
    for raw_line in str(text or "").splitlines():
        line = normalize_whitespace(raw_line)
        if not line:
            continue
        tokens.extend(chunk for chunk in re.split(r"\s+", line) if chunk)
    return tokens


def parse_answer_rows(text: str) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    current_number = None
    current_answers: list[str] = []

    for token in iterate_answer_tokens(text):
        number_match = re.fullmatch(r"\d{1,2}", token)
        if number_match:
            if current_number is not None and current_answers:
                rows.append((current_number, current_answers))
            current_number = int(number_match.group(0))
            current_answers = []
            continue

        answer = normalize_answer_token(token)
        if current_number is not None and answer:
            current_answers.append(answer)

    if current_number is not None and current_answers:
        rows.append((current_number, current_answers))
    return rows


def score_answer_text(text: str) -> tuple[int, list[tuple[int, int]]]:
    parseable_rows = []
    for number, answers in parse_answer_rows(text):
        if number is not None and answers:
            parseable_rows.append((number, len(answers)))
    score = len(parseable_rows) * 10 + sum(length for _, length in parseable_rows)
    return score, parseable_rows


def extract_answer_page_text(answer_pdf_path: Path, page_number: int) -> str:
    with fitz.open(answer_pdf_path) as document:
        page = document[page_number - 1]
        direct_text = normalize_multiline_text(page.get_text("text"))
        candidates = [direct_text] if direct_text else []
        for dpi, languages, psm in (
            (220, "eng", 4),
            (220, "chi_tra+eng", 4),
            (300, "eng", 4),
            (300, "chi_tra+eng", 4),
        ):
            try:
                ocr_text = normalize_multiline_text(
                    run_tesseract_on_image(render_page_png(page, dpi=dpi), languages=languages, psm=psm)
                )
            except Exception:
                ocr_text = ""
            if ocr_text:
                candidates.append(ocr_text)
    scored = sorted(
        ((score_answer_text(candidate)[0], candidate) for candidate in candidates if candidate),
        key=lambda item: item[0],
        reverse=True,
    )
    return scored[0][1] if scored else ""


def extract_cover_question_count(pdf_path: Path) -> int | None:
    patterns = [
        re.compile(r"有\s*(\d{1,3})\s*題"),
        re.compile(r"共\s*\d+\s*頁[^\n]{0,40}?(\d{1,3})\s*題"),
    ]
    with fitz.open(pdf_path) as document:
        cover_page = document[0]
        direct_text = normalize_multiline_text(cover_page.get_text("text"))
        candidates = [direct_text]

    for text in candidates:
        normalized = text.replace("\u2004", " ").replace("\u2005", " ").replace("\u2006", " ")
        for pattern in patterns:
            match = pattern.search(normalized)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

    with fitz.open(pdf_path) as document:
        cover_page = document[0]
        for dpi, languages, psm in (
            (220, "chi_tra+eng", 6),
            (300, "chi_tra+eng", 6),
            (300, "eng", 6),
        ):
            try:
                ocr_text = normalize_multiline_text(
                    run_tesseract_on_image(render_page_png(cover_page, dpi=dpi), languages=languages, psm=psm)
                )
            except Exception:
                ocr_text = ""
            if not ocr_text:
                continue
            normalized = ocr_text.replace("\u2004", " ").replace("\u2005", " ").replace("\u2006", " ")
            for pattern in patterns:
                match = pattern.search(normalized)
                if match:
                    try:
                        return int(match.group(1))
                    except ValueError:
                        continue
    return None


def resolve_official_question_count(year: str, subject_slug: str, pdf_path: Path) -> int | None:
    override = OFFICIAL_QUESTION_COUNT_OVERRIDES.get(str(year), {}).get(subject_slug)
    if override is not None:
        return override
    return extract_cover_question_count(pdf_path)


def is_english_reading_only_mode(year: str, subject_slug: str) -> bool:
    return subject_slug == "english" and str(year) in {"102", "103"}


def should_skip_source_question(year: str, subject_slug: str, source_number: int) -> bool:
    return is_english_reading_only_mode(year, subject_slug) and source_number < 21


def normalize_subject_question_number(year: str, subject_slug: str, source_number: int) -> int:
    if is_english_reading_only_mode(year, subject_slug) and source_number >= 21:
        return source_number - 20
    return source_number


def parse_answer_key(answer_pdf_path: Path) -> dict[str, dict[int, str]]:
    subject_answers = {
        "chinese": {},
        "english": {},
        "math": {},
        "social": {},
        "science": {},
        "english_listening": {},
    }

    with fitz.open(answer_pdf_path) as document:
        page_total = document.page_count

    previous_number = None
    max_row_width = 0
    for page_number in range(1, page_total + 1):
        page_text = extract_answer_page_text(answer_pdf_path, page_number)
        _, parseable_rows = score_answer_text(page_text)
        if parseable_rows:
            max_row_width = max(max_row_width, max(length for _, length in parseable_rows))

        for question_number, answers in parse_answer_rows(page_text):
            if not answers:
                continue
            question_number = normalize_answer_number(question_number, previous_number)
            previous_number = question_number

            sequence_size = 6 if max_row_width >= 6 else 5
            subject_order = ANSWER_SEQUENCE_MAP[sequence_size].get(len(answers), [])
            if not subject_order:
                continue
            for subject_slug, answer in zip(subject_order, answers):
                if subject_slug == "english_listening":
                    continue
                subject_answers[subject_slug][question_number] = answer

    visible_subjects = {subject for subject, mapping in subject_answers.items() if mapping and subject != "english_listening"}
    if not visible_subjects:
        raise RuntimeError("Unable to detect answer key columns.")

    return {subject: mapping for subject, mapping in subject_answers.items() if subject != "english_listening"}


def clean_cap_text(text: str) -> str:
    cleaned = str(text or "")
    for source, target in OPTION_MARKERS.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("請翻頁繼續作答", "")
    cleaned = re.sub(r"^\s*\d+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[࠾ĴĲĳॗᗊ\*]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return normalize_multiline_text(cleaned)


def question_start_match(line: str):
    return re.match(r"^(\d{1,2})\.\s*(.*)$", line)


def parse_question_chunks(pages: list[dict]) -> list[dict]:
    questions = []
    current = None
    carryover = ""

    for page in pages:
        page_number = page["page_number"]
        for raw_line in clean_cap_text(page["text"]).splitlines():
            line = normalize_whitespace(raw_line)
            if not line:
                continue

            start_match = question_start_match(line)
            if start_match:
                if current:
                    current["body"] = normalize_multiline_text("\n".join(current.pop("lines")))
                    questions.append(current)
                question_number = int(start_match.group(1))
                opening = start_match.group(2).strip()
                current = {
                    "number": question_number,
                    "page_number": page_number,
                    "carryover_context": carryover,
                    "lines": [opening] if opening else [],
                }
                carryover = ""
                continue

            if current is None:
                carryover = normalize_multiline_text("\n".join(filter(None, [carryover, line])))
                continue

            current["lines"].append(line)

    if current:
        current["body"] = normalize_multiline_text("\n".join(current.pop("lines")))
        questions.append(current)

    return questions


def split_question_body(body: str) -> tuple[str, dict[str, str], str]:
    body = normalize_multiline_text(body)
    if not body:
        return "", {}, ""

    normalized = re.sub(r"(?<!\S)\(([ABCD])\)", r"\n(\1)", body)
    matches = list(re.finditer(r"\(([ABCD])\)", normalized))
    if not matches:
        return body, {}, ""

    stem = normalize_whitespace(normalized[: matches[0].start()])
    options = {}
    trailing = ""
    for index, match in enumerate(matches):
        answer_key = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        chunk = normalize_multiline_text(normalized[start:end])
        options[answer_key] = chunk

    if len(matches) >= 4:
        last_option_text = options.get("D", "")
        split_candidate = re.search(r"(?<=[。！？!?])\s+(?=[^\(\)A-D])", last_option_text)
        if split_candidate and len(last_option_text[split_candidate.start() :]) > 40:
            trailing = normalize_multiline_text(last_option_text[split_candidate.start() :])
            options["D"] = normalize_multiline_text(last_option_text[: split_candidate.start()])

    return stem, options, trailing


def build_local_cap_explanation(subject_label: str, year: str, question: dict) -> str:
    answer = question.get("correct_answer") or "A"
    option_text = question.get("options", {}).get(answer, "")
    hints = [f"這題的正確答案是 {answer}。"]
    if option_text:
        hints.append(f"對應選項內容是「{option_text}」。")
    if question.get("context"):
        hints.append("先把題幹或前面的資料讀完，再圈出題目真正要比對的資訊。")
    else:
        hints.append("先抓題幹關鍵詞，再用刪去法排除不符合條件的選項。")
    hints.append(f"這題來自 {year} 年會考{subject_label}科，建議先回頭確認關鍵概念與題目限制。")
    return " ".join(hints)


def build_cap_structure_for_subject(
    year: str,
    subject_slug: str,
    subject_entry: dict,
    answer_map: dict[int, str],
    explanation_entry: dict,
    official_question_count: int | None = None,
) -> dict:
    subject_label = SUBJECT_LABELS[subject_slug]
    pdf_path = CAP_SOURCE_ROOT / year / subject_slug / f"{year}_{subject_slug}.pdf"
    docx_path = CAP_WORD_ROOT / year / f"{year}_{subject_slug}.docx"
    structured_path = CAP_STRUCTURED_ROOT / year / f"{subject_slug}.json"

    pages = extract_pdf_pages(pdf_path, ocr_threshold=55)
    save_extraction_docx(
        docx_path,
        title=f"{year} 年會考 {subject_label}",
        pages=pages,
        metadata={
            "年份": year,
            "科目": subject_label,
            "來源": subject_entry["question"]["url"],
        },
    )

    raw_questions = parse_question_chunks(pages)
    questions = []
    issues = []
    carryover = ""
    answered_count = 0

    for item in raw_questions:
        source_number = item["number"]
        if should_skip_source_question(year, subject_slug, source_number):
            issues.append({"question_number": source_number, "reason": "reading_only_skip"})
            continue

        stem, options, trailing = split_question_body(item["body"])
        context = normalize_multiline_text("\n".join(filter(None, [carryover, item.get("carryover_context", "")])))
        if trailing:
            carryover = trailing
        else:
            carryover = ""

        normalized_number = normalize_subject_question_number(year, subject_slug, source_number)
        correct_answer = answer_map.get(source_number, "")
        if not stem or len(options) < 2:
            issues.append(
                {
                    "question_number": source_number,
                    "display_source_number": normalized_number,
                    "reason": "parse_incomplete",
                    "stem_length": len(stem),
                    "option_count": len(options),
                }
            )
            continue

        question_payload = {
            "number": normalized_number,
            "source_number": source_number,
            "display_number": len(questions) + 1,
            "page_number": item["page_number"],
            "context": context,
            "stem": stem,
            "options": options,
            "correct_answer": correct_answer,
        }
        if correct_answer:
            answered_count += 1
            question_payload["explanation"] = build_local_cap_explanation(subject_label, year, question_payload)
        else:
            question_payload["explanation"] = "這題的官方答案目前還在補查中，先用預覽模式閱讀題目與選項。"
            issues.append(
                {
                    "question_number": source_number,
                    "display_source_number": normalized_number,
                    "reason": "missing_answer",
                }
            )
        questions.append(question_payload)

    raw_question_numbers = [
        normalize_subject_question_number(year, subject_slug, item["number"])
        for item in raw_questions
        if item.get("number") is not None and not should_skip_source_question(year, subject_slug, item["number"])
    ]
    kept_question_numbers = [item["number"] for item in questions if item.get("number") is not None]
    missing_question_numbers = []
    if official_question_count:
        missing_question_numbers = [
            question_number
            for question_number in range(1, official_question_count + 1)
            if question_number not in kept_question_numbers
        ]
    duplicate_question_numbers = sorted(
        {
            question_number
            for question_number in kept_question_numbers
            if kept_question_numbers.count(question_number) > 1
        }
    )
    answer_completion_ratio = answered_count / len(questions) if questions else 0.0
    payload = {
        "year": year,
        "subject_slug": subject_slug,
        "subject_label": subject_label,
        "official_question_count": official_question_count,
        "question_count": len(questions),
        "answered_count": answered_count,
        "page_count": len(pages),
        "ocr_pages": [page["page_number"] for page in pages if page["source"] != "direct"],
        "files": {
            "pdf": str(pdf_path.relative_to(DATA_ROOT)),
            "docx": str(docx_path.relative_to(DATA_ROOT)),
        },
        "official": {
            "question_url": subject_entry["question"]["url"],
            "answer_url": explanation_entry["answer"]["url"],
            "explanation_url": explanation_entry["explanation"]["url"],
        },
        "checks": {
            "question_chunks_found": len(raw_questions),
            "answers_found": len(answer_map),
            "questions_kept": len(questions),
            "issues_found": len(issues),
            "answer_completion_ratio": round(answer_completion_ratio, 3),
            "raw_question_numbers": raw_question_numbers,
            "kept_question_numbers": kept_question_numbers,
            "missing_question_numbers": missing_question_numbers,
            "duplicate_question_numbers": duplicate_question_numbers,
        },
        "practice_ready": (
            answer_completion_ratio >= 0.95
            and len(questions) > 0
            and (official_question_count is None or len(questions) == official_question_count)
            and not missing_question_numbers
            and not duplicate_question_numbers
        ),
        "questions": questions,
        "issues": issues,
    }
    write_json(structured_path, payload)
    return payload


def build_library() -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Codex CAP builder"})
    manifest = load_cap_manifest()
    year_entries = []

    for year_entry in sorted(manifest.get("years", []), key=lambda item: str(item.get("year")), reverse=True):
        year = str(year_entry["year"])
        ensure_dir(CAP_SOURCE_ROOT / year)
        shared_dir = CAP_SOURCE_ROOT / year / "shared"
        ensure_dir(shared_dir)

        answer_pdf = download_to_path(year_entry["answer"]["download_url"], shared_dir / f"{year}_answers.pdf", session=session)
        explanation_pdf = download_to_path(year_entry["explanation"]["download_url"], shared_dir / f"{year}_explanation.pdf", session=session)
        try:
            answer_map = parse_answer_key(answer_pdf)
        except Exception as exc:
            answer_map = {}
            year_entry.setdefault("issues", []).append(f"answer_parse_failed:{exc}")

        subjects = []
        issues = list(year_entry.get("issues", []))
        for subject_entry in year_entry.get("subjects", []):
            subject_slug = subject_entry["slug"]
            subject_dir = CAP_SOURCE_ROOT / year / subject_slug
            ensure_dir(subject_dir)
            question_pdf = download_to_path(
                subject_entry["question"]["download_url"],
                subject_dir / f"{year}_{subject_slug}.pdf",
                session=session,
            )
            if not question_pdf.exists():
                issues.append(f"missing_pdf:{year}:{subject_slug}")
                continue

            official_question_count = resolve_official_question_count(year, subject_slug, question_pdf)
            structured = build_cap_structure_for_subject(
                year,
                subject_slug,
                subject_entry,
                answer_map.get(subject_slug, {}),
                year_entry,
                official_question_count=official_question_count,
            )
            if official_question_count is None:
                issues.append(f"cover_count_missing:{year}:{subject_slug}")
            elif structured["question_count"] != official_question_count:
                issues.append(
                    f"question_count_mismatch:{year}:{subject_slug}:{structured['question_count']}!= {official_question_count}"
                )
            subjects.append(
                {
                    "slug": subject_slug,
                    "label": SUBJECT_LABELS[subject_slug],
                    "official_question_count": official_question_count,
                    "question_count": structured["question_count"],
                    "answered_count": structured["answered_count"],
                    "practice_ready": structured["practice_ready"],
                    "structured_path": str((CAP_STRUCTURED_ROOT / year / f"{subject_slug}.json").relative_to(DATA_ROOT)),
                    "page_count": structured["page_count"],
                    "ocr_pages": structured["ocr_pages"],
                }
            )

        year_entries.append(
            {
                "year": year,
                "answer_file": str(answer_pdf.relative_to(DATA_ROOT)),
                "explanation_file": str(explanation_pdf.relative_to(DATA_ROOT)),
                "subjects": subjects,
                "issues": issues,
            }
        )

    payload = {
        "title": "會考歷屆練習",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "years": year_entries,
    }
    write_json(CAP_LIBRARY_MANIFEST, payload)
    return payload


if __name__ == "__main__":
    result = build_library()
    print(f"years: {len(result['years'])}")
    print(f"subjects: {sum(len(year['subjects']) for year in result['years'])}")
