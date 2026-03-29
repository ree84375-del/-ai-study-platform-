from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

from app.utils.document_ingest import (
    DATA_ROOT,
    download_to_path,
    ensure_dir,
    extract_pdf_pages,
    normalize_multiline_text,
    normalize_whitespace,
    read_words,
    save_extraction_docx,
    slugify,
    write_json,
)


CAP_SOURCE_MANIFEST = DATA_ROOT / "cap_review" / "cap_manifest.json"
CAP_SOURCE_ROOT = DATA_ROOT / "cap_practice_sources"
CAP_WORD_ROOT = DATA_ROOT / "cap_practice_word"
CAP_STRUCTURED_ROOT = DATA_ROOT / "cap_practice_structured"
CAP_LIBRARY_MANIFEST = DATA_ROOT / "cap_review" / "cap_practice_manifest.json"

SUBJECT_LABELS = {
    "chinese": "國文",
    "english": "英語",
    "math": "數學",
    "social": "社會",
    "science": "自然",
}
ANSWER_SUBJECT_ORDER_6 = ["chinese", "english", "english_listening", "math", "social", "science"]
ANSWER_SUBJECT_ORDER_5 = ["chinese", "english", "math", "social", "science"]
ANSWER_HEADER_MAP = {
    "國文": "chinese",
    "數學": "math",
    "社會": "social",
    "自然": "science",
    "閱讀": "english",
    "(閱讀)": "english",
    "聽力": "english_listening",
    "(聽力)": "english_listening",
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


def group_words_by_row(words: list[dict], tolerance: float = 3.0) -> list[list[dict]]:
    rows = []
    for word in sorted(words, key=lambda item: (item["y0"], item["x0"])):
        if not rows or abs(rows[-1][0]["y0"] - word["y0"]) > tolerance:
            rows.append([word])
        else:
            rows[-1].append(word)
    return rows


def cluster_positions(values: list[float], tolerance: float = 26.0) -> list[float]:
    clusters = []
    for value in sorted(values):
        if not clusters or abs(clusters[-1][-1] - value) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def parse_answer_key(answer_pdf_path: Path) -> dict[str, dict[int, str]]:
    subject_answers = {
        "chinese": {},
        "english": {},
        "math": {},
        "social": {},
        "science": {},
        "english_listening": {},
    }

    for page_number in range(1, 4):
        try:
            words = read_words(answer_pdf_path, page_number)
        except Exception:
            continue

        header_columns = {}
        for word in words:
            token = normalize_whitespace(word["text"])
            mapped = ANSWER_HEADER_MAP.get(token)
            if not mapped:
                continue
            existing = header_columns.get(mapped)
            if existing is None or word["x0"] < existing:
                header_columns[mapped] = word["x0"]

        page_subject_order = [subject for subject, _ in sorted(header_columns.items(), key=lambda item: item[1])]
        page_centers = [header_columns[subject] for subject in page_subject_order]

        if len(page_centers) < 2:
            continue

        for row in group_words_by_row(words):
            row = sorted(row, key=lambda item: item["x0"])
            texts = [normalize_whitespace(item["text"]) for item in row if normalize_whitespace(item["text"])]
            if not texts:
                continue
            if not re.fullmatch(r"\d{1,2}", texts[0]):
                continue
            question_number = int(texts[0])
            for item in row[1:]:
                token = normalize_whitespace(item["text"])
                if re.fullmatch(r"[A-D]", token):
                    nearest_index = min(range(len(page_centers)), key=lambda idx: abs(page_centers[idx] - item["x0"]))
                    if nearest_index < len(page_subject_order):
                        subject_answers[page_subject_order[nearest_index]][question_number] = token

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


def build_cap_structure_for_subject(year: str, subject_slug: str, subject_entry: dict, answer_map: dict[int, str], explanation_entry: dict) -> dict:
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
        stem, options, trailing = split_question_body(item["body"])
        context = normalize_multiline_text("\n".join(filter(None, [carryover, item.get("carryover_context", "")])))
        if trailing:
            carryover = trailing
        else:
            carryover = ""

        correct_answer = answer_map.get(item["number"], "")
        if not stem or len(options) < 2:
            issues.append(
                {
                    "question_number": item["number"],
                    "reason": "parse_incomplete",
                    "stem_length": len(stem),
                    "option_count": len(options),
                }
            )
            continue

        question_payload = {
            "number": item["number"],
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
            question_payload["explanation"] = f"這題的官方答案目前還在補查中，先用預覽模式閱讀題目與選項。"
            issues.append({"question_number": item["number"], "reason": "missing_answer"})
        questions.append(question_payload)

    answer_completion_ratio = answered_count / len(questions) if questions else 0.0
    payload = {
        "year": year,
        "subject_slug": subject_slug,
        "subject_label": subject_label,
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
        },
        "practice_ready": answer_completion_ratio >= 0.95 and len(questions) > 0,
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

            structured = build_cap_structure_for_subject(year, subject_slug, subject_entry, answer_map.get(subject_slug, {}), year_entry)
            subjects.append(
                {
                    "slug": subject_slug,
                    "label": SUBJECT_LABELS[subject_slug],
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
