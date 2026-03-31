from __future__ import annotations

import io
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import fitz
import requests
from PIL import Image

from app.utils.document_ingest import (
    DATA_ROOT,
    download_to_path,
    ensure_dir,
    extract_pdf_pages,
    normalize_multiline_text,
    normalize_whitespace,
    render_page_png,
    run_tesseract_on_image,
    run_tesseract_tsv_on_image,
    save_extraction_docx,
    slugify,
    write_json,
)


CAP_SOURCE_MANIFEST = DATA_ROOT / "cap_review" / "cap_manifest.json"
CAP_SOURCE_ROOT = DATA_ROOT / "cap_practice_sources"
CAP_WORD_ROOT = DATA_ROOT / "cap_practice_word"
CAP_STRUCTURED_ROOT = DATA_ROOT / "cap_practice_structured"
CAP_LIBRARY_MANIFEST = DATA_ROOT / "cap_review" / "cap_practice_manifest.json"
CAP_ASSET_ROOT = DATA_ROOT / "cap_practice_assets"

OFFICIAL_QUESTION_COUNT_OVERRIDES = {
    "102": {"chinese": 48, "english": 40, "math": 25, "social": 63, "science": 54},
    "103": {"chinese": 48, "english": 40, "math": 27, "social": 63, "science": 54},
    "104": {"chinese": 48, "english": 40, "math": 25, "social": 63, "science": 54},
    "105": {"chinese": 48, "english": 41, "math": 25, "social": 63, "science": 54},
    "106": {"chinese": 48, "english": 41, "math": 26, "social": 63, "science": 54},
    "107": {"chinese": 48, "english": 41, "math": 26, "social": 63, "science": 54},
    "108": {"chinese": 48, "english": 41, "math": 26, "social": 63, "science": 54},
    "109": {"chinese": 48, "english": 41, "math": 26, "social": 63, "science": 54},
    "110": {"chinese": 48, "english": 41, "math": 26, "social": 63, "science": 54},
    "111": {"chinese": 42, "english": 43, "math": 25, "social": 54, "science": 50},
    "112": {"chinese": 42, "english": 43, "math": 25, "social": 54, "science": 50},
    "113": {"chinese": 42, "english": 43, "math": 25, "social": 54, "science": 50},
    "114": {"chinese": 42, "english": 43, "math": 25, "social": 54, "science": 50},
}

ENGLISH_LISTENING_YEARS = {"104", "105", "106", "107", "108", "110", "111", "112", "113", "114"}
ENGLISH_LISTENING_COUNT = 21

SUBJECT_LABELS = {
    "chinese": "國文",
    "english": "英語",
    "math": "數學",
    "social": "社會",
    "science": "自然",
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
SCANNED_FALLBACK_LANGUAGES = {
    "english": "eng",
    "math": "eng",
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


def extract_answer_page_candidates(answer_pdf_path: Path, page_number: int) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    with fitz.open(answer_pdf_path) as document:
        page = document[page_number - 1]
        direct_text = normalize_multiline_text(page.get_text("text"))
        if direct_text and direct_text not in seen:
            seen.add(direct_text)
            candidates.append(("direct", direct_text))
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
            if ocr_text and ocr_text not in seen:
                seen.add(ocr_text)
                candidates.append((f"ocr:{dpi}:{languages}:{psm}", ocr_text))
    return candidates


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


def get_official_subject_counts(year: str) -> dict[str, int]:
    return OFFICIAL_QUESTION_COUNT_OVERRIDES.get(str(year), {})


def get_answer_sheet_subject_counts(year: str) -> dict[str, int]:
    counts = dict(get_official_subject_counts(year))
    if str(year) in {"102", "103"}:
        counts["english"] = 60
    return counts


def has_english_listening_column(year: str) -> bool:
    return str(year) in ENGLISH_LISTENING_YEARS


def is_english_reading_only_mode(year: str, subject_slug: str) -> bool:
    return subject_slug == "english" and str(year) in {"102", "103"}


def should_skip_source_question(year: str, subject_slug: str, source_number: int) -> bool:
    return is_english_reading_only_mode(year, subject_slug) and source_number < 21


def normalize_subject_question_number(year: str, subject_slug: str, source_number: int) -> int:
    if is_english_reading_only_mode(year, subject_slug) and source_number >= 21:
        return source_number - 20
    return source_number


def build_answer_column_order(year: str, question_number: int) -> list[str]:
    counts = get_answer_sheet_subject_counts(year)
    columns: list[str] = []
    if question_number <= counts.get("chinese", 0):
        columns.append("chinese")
    if question_number <= counts.get("english", 0):
        columns.append("english")
    if has_english_listening_column(year) and question_number <= ENGLISH_LISTENING_COUNT:
        columns.append("english_listening")
    if question_number <= counts.get("math", 0):
        columns.append("math")
    if question_number <= counts.get("social", 0):
        columns.append("social")
    if question_number <= counts.get("science", 0):
        columns.append("science")
    return columns


def parse_answer_key(answer_pdf_path: Path, year: str) -> dict[str, dict[int, str]]:
    official_counts = get_official_subject_counts(year)
    answer_sheet_counts = get_answer_sheet_subject_counts(year)
    visible_subjects = ["chinese", "english", "math", "social", "science"]
    if not official_counts:
        raise RuntimeError(f"Missing official answer key counts for {year}.")

    answer_votes: dict[str, dict[int, Counter[str]]] = {
        subject_slug: defaultdict(Counter) for subject_slug in visible_subjects
    }

    with fitz.open(answer_pdf_path) as document:
        page_total = document.page_count

    max_question_number = max(answer_sheet_counts.values())
    for page_number in range(1, page_total + 1):
        for source_label, page_text in extract_answer_page_candidates(answer_pdf_path, page_number):
            previous_number = None
            source_weight = 5 if source_label == "direct" else 1
            for raw_number, answers in parse_answer_rows(page_text):
                if not answers:
                    continue
                question_number = normalize_answer_number(raw_number, previous_number)
                previous_number = question_number
                if question_number < 1 or question_number > max_question_number:
                    continue

                subject_order = build_answer_column_order(year, question_number)
                if len(answers) != len(subject_order):
                    continue

                for subject_slug, answer in zip(subject_order, answers):
                    if subject_slug == "english_listening":
                        continue
                    if question_number > answer_sheet_counts.get(subject_slug, 0):
                        continue
                    answer_votes[subject_slug][question_number][answer] += source_weight

    subject_answers: dict[str, dict[int, str]] = {}
    for subject_slug in visible_subjects:
        mapping: dict[int, str] = {}
        for question_number in range(1, answer_sheet_counts.get(subject_slug, 0) + 1):
            votes = answer_votes[subject_slug].get(question_number)
            if not votes:
                continue
            mapping[question_number] = votes.most_common(1)[0][0]
        subject_answers[subject_slug] = mapping

    visible_mappings = {subject: mapping for subject, mapping in subject_answers.items() if mapping}
    if not visible_mappings:
        raise RuntimeError("Unable to detect answer key columns.")

    return subject_answers


def clean_cap_text(text: str) -> str:
    cleaned = str(text or "")
    for source, target in OPTION_MARKERS.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("請翻頁繼續作答", "")
    cleaned = re.sub(r"^\s*\d+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[࠾ĴĲĳॗᗊ\*]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return normalize_multiline_text(cleaned)


QUESTION_START_RE = re.compile(r"^([0-9IlOo\|]{1,3})(?:\s*[\.\。、,，:：]\s*|\s+)(.*)$")
OPTION_LINE_RE = re.compile(r"^\(?\s*([ABCD])\s*[\)）\].、,，:：]?\s*(.*)$")
QUESTION_CONTINUATION_PREFIXES = (">", "》", "〉", "›", "»", "-", "—", "–", "•", "·")
FIGURE_LINE_RE = re.compile(r"^(?:圖|表|請翻頁|請翻頁繼續作答|請翻頁繼續作答。)")


def normalize_question_start_token(token: str) -> int | None:
    token = normalize_whitespace(token)
    if not token:
        return None

    translated = token.translate(
        str.maketrans(
            {
                "I": "1",
                "l": "1",
                "|": "1",
                "O": "0",
                "o": "0",
            }
        )
    )
    if translated.isdigit():
        return int(translated)
    return None


def normalize_question_number(number: int, previous_number: int | None) -> int:
    if previous_number is None:
        return number

    if number == previous_number + 1:
        return number

    if number <= previous_number:
        return previous_number + 1

    if number > previous_number + 1:
        for delta in (10, 20, 30):
            if number + delta == previous_number + 1:
                return previous_number + 1

    return number


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def looks_like_label_noise(opening: str) -> bool:
    opening = opening.strip()
    if not opening:
        return False
    if len(opening) <= 4 and not contains_cjk(opening) and not re.search(r"[?？=+\-×÷]", opening):
        return True
    if re.fullmatch(r"[A-Za-z0-9\s\|]+", opening) and len(opening) <= 12:
        return True
    return False


def question_start_match(line: str, previous_number: int | None = None):
    if re.match(r"^\d{1,2}\s*[:：]\s*\d", line):
        return None

    match = QUESTION_START_RE.match(line)
    if not match:
        return None

    raw_number = normalize_question_start_token(match.group(1))
    if raw_number is None:
        return None
    if raw_number <= 0 or raw_number > 70:
        return None

    opening = match.group(2).strip()
    if not opening and "." not in line and "。" not in line:
        return None
    if opening.startswith(("×", "x", "X", "+", "-", "−", "=", "°", "%", "÷", "/", "／", ")", "）")):
        return None
    if opening and re.fullmatch(r"\d+(?:\s+\d+)*", opening):
        return None
    if previous_number is not None and raw_number > previous_number + 3 and looks_like_label_noise(opening):
        raw_number = previous_number + 1
    if previous_number is not None and raw_number <= previous_number and looks_like_label_noise(opening):
        return None

    question_number = normalize_question_number(raw_number, previous_number)
    return {
        "number": question_number,
        "opening": opening,
        "raw_token": match.group(1),
    }


def is_option_line(line: str) -> bool:
    return bool(OPTION_LINE_RE.match(line))


def is_figure_or_footer_line(line: str) -> bool:
    return bool(FIGURE_LINE_RE.match(line))


def looks_like_implied_question_start(line: str) -> bool:
    candidate = line.lstrip("".join(QUESTION_CONTINUATION_PREFIXES)).strip()
    if len(candidate) < 8:
        return False
    if is_option_line(candidate) or is_figure_or_footer_line(candidate):
        return False
    if candidate.startswith(("資料", "附圖", "請翻頁")):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", candidate))


def get_scanned_fallback_languages(subject_slug: str) -> str:
    return SCANNED_FALLBACK_LANGUAGES.get(subject_slug, "chi_tra+eng")


def extract_margin_question_starts(
    page_image_bytes: bytes,
    previous_number: int | None,
    official_question_count: int | None,
    strict_sequence: bool = False,
) -> list[dict]:
    image = Image.open(io.BytesIO(page_image_bytes))
    width, height = image.size
    crop = image.crop((0, 0, max(1, int(width * 0.16)), height))
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG")
    rows = run_tesseract_tsv_on_image(
        buffer.getvalue(),
        languages="eng",
        psm=6,
        extra_configs=["tessedit_char_whitelist=0123456789IlOo.|"],
    )

    starts: list[dict] = []
    current_number = previous_number
    for row in sorted(rows, key=lambda item: (item["y0"], item["x0"])):
        text = normalize_whitespace(row["text"])
        if not text or row["y0"] >= height * 0.96:
            continue

        prefix_match = re.match(r"^([0-9IlOo|]{1,2})", text)
        raw_number = normalize_question_start_token(prefix_match.group(1)) if prefix_match else None
        expected_number = (current_number + 1) if current_number is not None else None
        if expected_number is None:
            candidate_number = raw_number
        elif raw_number is None or raw_number == 0:
            candidate_number = expected_number
        elif raw_number == expected_number:
            candidate_number = raw_number
        elif raw_number < expected_number:
            candidate_number = expected_number
        elif strict_sequence and raw_number > expected_number + 1:
            candidate_number = expected_number
        else:
            candidate_number = raw_number

        if candidate_number is None or candidate_number <= 0:
            continue
        if official_question_count and candidate_number > official_question_count:
            continue

        if starts and abs(row["y0"] - starts[-1]["y0"]) < 70:
            if row["confidence"] > starts[-1]["confidence"]:
                starts[-1] = {
                    "number": candidate_number,
                    "y0": int(row["y0"]),
                    "y1": int(row["y1"]),
                    "text": text,
                    "confidence": row["confidence"],
                }
            continue

        starts.append(
            {
                "number": candidate_number,
                "y0": int(row["y0"]),
                "y1": int(row["y1"]),
                "text": text,
                "confidence": row["confidence"],
            }
        )
        current_number = candidate_number
    return starts


def extract_question_band_texts(
    page_image_bytes: bytes,
    question_starts: list[dict],
    subject_slug: str,
) -> list[dict]:
    if not question_starts:
        return []

    image = Image.open(io.BytesIO(page_image_bytes))
    width, height = image.size
    band_left = int(width * 0.06)
    band_right = width
    languages = get_scanned_fallback_languages(subject_slug)
    extracted: list[dict] = []

    for index, start in enumerate(question_starts):
        top = max(0, start["y0"] - 20)
        next_top = question_starts[index + 1]["y0"] - 12 if index + 1 < len(question_starts) else height - 30
        bottom = max(top + 80, min(height, next_top))
        band = image.crop((band_left, top, band_right, bottom))
        buffer = io.BytesIO()
        band.save(buffer, format="PNG")
        text = normalize_multiline_text(
            run_tesseract_on_image(buffer.getvalue(), languages=languages, psm=4)
        )
        if not text:
            continue
        text = clean_cap_text(text)
        text = re.sub(rf"^\s*{start['number']}\s*[\.\、\)]?\s*", "", text, count=1)
        extracted.append(
            {
                "number": start["number"],
                "page_number": None,
                "carryover_context": "",
                "body": text,
            }
        )
    return extracted


def extract_scanned_fallback_question_chunks(
    pdf_path: Path,
    year: str,
    subject_slug: str,
    official_question_count: int | None,
) -> list[dict]:
    chunks: list[dict] = []
    previous_number = None
    strict_sequence = str(year) in {"102", "103"}
    with fitz.open(pdf_path) as document:
        for page_index in range(document.page_count):
            page_number = page_index + 1
            if page_number == 1:
                continue
            page_image_bytes = render_page_png(document[page_index], dpi=300)
            starts = extract_margin_question_starts(
                page_image_bytes,
                previous_number,
                official_question_count,
                strict_sequence=strict_sequence,
            )
            if not starts:
                continue
            page_chunks = extract_question_band_texts(page_image_bytes, starts, subject_slug)
            for chunk in page_chunks:
                chunk["page_number"] = page_number
                chunks.append(chunk)
                previous_number = chunk["number"]
    return chunks


def extract_page_local_question_chunks(
    pages: list[dict],
    subject_slug: str | None = None,
) -> list[dict]:
    chunks: list[dict] = []
    for page in pages:
        if page["page_number"] == 1:
            continue
        chunks.extend(
            parse_question_chunks(
                [page],
                subject_slug=subject_slug,
                reset_numbering_each_page=True,
            )
        )
    return chunks


def parse_question_chunks(
    pages: list[dict],
    subject_slug: str | None = None,
    reset_numbering_each_page: bool = False,
) -> list[dict]:
    questions = []
    current = None
    carryover = ""
    in_exam_section = True
    start_pattern = re.compile(
        r"^(?:第\s*一\s*部\s*分.*?(?:單\s*題|選\s*擇\s*題)|[一壹]\s*[、,，\.:：]?\s*(?:單\s*題|選\s*擇\s*題)).*?(?:1|１)\s*[~\-一至到]\s*\d+"
    )
    end_pattern = re.compile(r"^(?:第\s*二\s*部\s*分.*?非\s*選\s*擇\s*題|[二貳]\s*[、,，\.:：]?\s*非\s*選\s*擇\s*題)")

    def finalize_current():
        nonlocal current
        if not current:
            return
        current["body"] = normalize_multiline_text("\n".join(current.pop("lines")))
        current.pop("option_line_count", None)
        questions.append(current)
        current = None

    for page in pages:
        page_number = page["page_number"]
        if page_number == 1:
            continue
        page_previous_number = None
        for raw_line in clean_cap_text(page["text"]).splitlines():
            line = normalize_whitespace(raw_line)
            if not line:
                continue

            if not in_exam_section:
                continue

            previous_number = (
                current["number"]
                if current
                else (
                    page_previous_number
                    if reset_numbering_each_page
                    else (questions[-1]["number"] if questions else None)
                )
            )
            start_match = question_start_match(line, previous_number=previous_number)
            if start_match:
                finalize_current()
                question_number = start_match["number"]
                opening = start_match["opening"]
                current = {
                    "number": question_number,
                    "page_number": page_number,
                    "carryover_context": carryover,
                    "lines": [opening] if opening else [],
                    "option_line_count": 1 if opening and is_option_line(opening) else 0,
                }
                page_previous_number = question_number
                carryover = ""
                continue

            if current is None:
                carryover = normalize_multiline_text("\n".join(filter(None, [carryover, line])))
                continue

            if is_option_line(line):
                current["option_line_count"] += 1
                current["lines"].append(line)
                continue

            if (
                subject_slug in {"math", "chinese"}
                and current.get("option_line_count", 0) >= 2
                and looks_like_implied_question_start(line)
            ):
                finalize_current()
                previous_number = questions[-1]["number"] if questions else 0
                implied_line = line.lstrip("".join(QUESTION_CONTINUATION_PREFIXES)).strip()
                current = {
                    "number": previous_number + 1,
                    "page_number": page_number,
                    "carryover_context": "",
                    "lines": [implied_line] if implied_line else [],
                    "option_line_count": 0,
                }
                page_previous_number = previous_number + 1
                continue

            current["lines"].append(line)

    finalize_current()

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


VISUAL_REFERENCE_RE = re.compile(
    r"(圖\s*[（(]?[一二三四五六七八九十\d]+[)）]?|下圖|上圖|如圖|圖中|表\s*[（(]?[一二三四五六七八九十\d]+[)）]?|下表|如表|漫畫|照片|示意圖|Look at the picture|look at the picture|comic|chart|graph|table)",
    re.IGNORECASE,
)


def question_has_visual_reference(question: dict) -> bool:
    snippets = [question.get("context", ""), question.get("stem", "")]
    snippets.extend((question.get("options") or {}).values())
    text = "\n".join(str(item or "") for item in snippets)
    return bool(VISUAL_REFERENCE_RE.search(text))


def build_local_cap_explanation(subject_label: str, year: str, question: dict) -> str:
    answer = (question.get("correct_answer") or "A").strip().upper() or "A"
    option_text = normalize_whitespace((question.get("options") or {}).get(answer, ""))
    context = normalize_whitespace(question.get("context", ""))
    stem = normalize_whitespace(question.get("stem", ""))
    subject_slug = question.get("subject_slug", "")

    focus_line = "先把題幹的限制條件圈出來，再比對最符合條件的選項。"
    step_line = "先讀題幹，再回頭對照四個選項，最後檢查是否有單位、對象或關鍵詞被忽略。"

    if subject_slug == "english":
        if "____" in stem or "_____" in stem:
            focus_line = "先看空格前後的語意與詞性，再判斷哪個選項放進去最通順。"
            step_line = "先找空格周圍的關鍵字，再判斷語意、詞性與句型是否一致，最後回整句確認語感。"
        elif context:
            focus_line = "這題屬於題組閱讀，先抓出題組關鍵句，再回題目定位答案。"
            step_line = "先略讀題組重點，再看題目在問什麼，最後回到原文找到能直接支持答案的句子。"
        else:
            focus_line = "先抓句子的語意方向，再排除文法或語意不通的選項。"
    elif subject_slug == "math":
        focus_line = "先確認題目要比較的是哪個量，再列式、化簡或代入，最後再和選項比對。"
        step_line = "先整理已知條件，再用計算或圖形判斷縮小範圍，最後檢查答案是否符合題目要求。"
    elif subject_slug == "science":
        focus_line = "先分清題目考的是概念、實驗條件還是圖表資訊，再對照選項。"
        step_line = "先讀懂題幹與圖表的變因，再排除和科學概念不符的選項，最後回頭確認條件是否都滿足。"
    elif subject_slug == "social":
        focus_line = "先找出題幹的時代、地點、制度或議題關鍵詞，再對照選項。"
        step_line = "先圈出題目中的核心線索，再排除時序、地理位置或制度概念不合的選項。"
    elif subject_slug == "chinese":
        if context:
            focus_line = "先讀完整段材料，再判斷題目是在問文意、修辭還是觀點。"
            step_line = "先抓文本中的關鍵句，再比對四個選項與原文是否一致，最後排除過度推論。"
        else:
            focus_line = "先看題目考的是字詞、語意還是修辭，再找最符合的選項。"

    lines = [
        f"官方答案：{answer}" + (f"（{option_text}）" if option_text else ""),
        f"題目重點：{focus_line}",
        f"作答步驟：{step_line}",
    ]

    if context:
        lines.append("題組提醒：這題有前置材料，作答前要先把題組或題幹補充資訊看完。")
    if question_has_visual_reference(question):
        lines.append("圖表提醒：這題含有圖片、圖形或表格資訊，請先看清圖中的標記、座標、欄位或對話框內容。")

    lines.append(f"複習方向：這題來自 {year} 年會考{subject_label}科，可回頭複習同主題的核心觀念與常見判斷方式。")
    return "\n".join(lines)


def score_question_candidate(stem: str, options: dict[str, str], context: str, correct_answer: str) -> int:
    option_score = len(options) * 200
    stem_score = min(len(stem), 240)
    context_score = min(len(context), 120) // 3
    answer_score = 40 if correct_answer else 0
    completeness_bonus = 120 if stem and len(options) >= 2 else 0
    return option_score + stem_score + context_score + answer_score + completeness_bonus


def ensure_cap_page_assets(pdf_path: Path, year: str, subject_slug: str) -> dict[int, str]:
    asset_map: dict[int, str] = {}
    with fitz.open(pdf_path) as document:
        for page_index in range(document.page_count):
            asset_map[page_index + 1] = str(
                Path("cap_practice_assets") / year / subject_slug / f"page_{page_index + 1:02d}.png"
            )
    return asset_map


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

    raw_questions = parse_question_chunks(
        pages,
        subject_slug=subject_slug,
        reset_numbering_each_page=str(year) in {"102", "103"},
    )
    if str(year) in {"102", "103"}:
        raw_questions.extend(extract_page_local_question_chunks(pages, subject_slug=subject_slug))
    normalized_raw_numbers = [
        normalize_subject_question_number(year, subject_slug, item["number"])
        for item in raw_questions
        if (
            item.get("number") is not None
            and not should_skip_source_question(year, subject_slug, item["number"])
            and (
                official_question_count is None
                or normalize_subject_question_number(year, subject_slug, item["number"]) <= official_question_count
            )
        )
    ]
    raw_unique_count = len(set(normalized_raw_numbers))
    if official_question_count is None or raw_unique_count != official_question_count:
        raw_questions.extend(
            extract_scanned_fallback_question_chunks(
                pdf_path,
                year,
                subject_slug,
                official_question_count,
            )
        )
    page_assets = ensure_cap_page_assets(pdf_path, year, subject_slug)
    questions = []
    issues = []
    carryover = ""
    answered_count = 0
    candidate_buckets: dict[int, list[dict]] = defaultdict(list)

    for item in raw_questions:
        source_number = item["number"]
        if not source_number or source_number <= 0:
            issues.append({"question_number": source_number or 0, "reason": "invalid_question_number"})
            continue
        if should_skip_source_question(year, subject_slug, source_number):
            issues.append({"question_number": source_number, "reason": "reading_only_skip"})
            continue

        normalized_number = normalize_subject_question_number(year, subject_slug, source_number)
        if official_question_count and normalized_number > official_question_count:
            issues.append(
                {
                    "question_number": source_number,
                    "display_source_number": normalized_number,
                    "reason": "out_of_range_question_number",
                }
            )
            continue

        stem, options, trailing = split_question_body(item["body"])
        context = normalize_multiline_text("\n".join(filter(None, [carryover, item.get("carryover_context", "")])))
        if trailing:
            carryover = trailing
        else:
            carryover = ""

        correct_answer = answer_map.get(normalized_number, "") or answer_map.get(source_number, "")
        parse_status = "complete" if stem and len(options) >= 2 else "image_or_layout_fallback"
        if parse_status != "complete":
            issues.append(
                {
                    "question_number": source_number,
                    "display_source_number": normalized_number,
                    "reason": "parse_incomplete",
                    "stem_length": len(stem),
                    "option_count": len(options),
                }
            )

        candidate_buckets[normalized_number].append(
            {
                "number": normalized_number,
                "source_number": source_number,
                "page_number": item["page_number"],
                "page_image_path": page_assets.get(item["page_number"]),
                "context": context,
                "stem": stem,
                "options": options,
                "correct_answer": correct_answer,
                "parse_status": parse_status,
                "candidate_score": score_question_candidate(stem, options, context, correct_answer),
            }
        )

    for normalized_number in sorted(candidate_buckets):
        candidates = sorted(
            candidate_buckets[normalized_number],
            key=lambda item: (item["candidate_score"], len(item["options"]), len(item["stem"])),
            reverse=True,
        )
        best = candidates[0]
        question_payload = {
            "number": best["number"],
            "source_number": best["source_number"],
            "display_number": len(questions) + 1,
            "page_number": best["page_number"],
            "page_image_path": best["page_image_path"],
            "parse_status": best["parse_status"],
            "context": best["context"],
            "stem": best["stem"],
            "options": best["options"],
            "correct_answer": best["correct_answer"],
        }
        if best["correct_answer"]:
            answered_count += 1
            question_payload["explanation"] = build_local_cap_explanation(subject_label, year, question_payload)
        else:
            question_payload["explanation"] = "這題的官方答案目前還在補查中，先用預覽模式閱讀題目與選項。"
            issues.append(
                {
                    "question_number": best["source_number"],
                    "display_source_number": normalized_number,
                    "reason": "missing_answer",
                }
            )
        questions.append(question_payload)

    raw_question_numbers = [
        normalize_subject_question_number(year, subject_slug, item["number"])
        for item in raw_questions
        if (
            item.get("number") is not None
            and not should_skip_source_question(year, subject_slug, item["number"])
            and (
                official_question_count is None
                or normalize_subject_question_number(year, subject_slug, item["number"]) <= official_question_count
            )
        )
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
            answer_map = parse_answer_key(answer_pdf, year)
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
