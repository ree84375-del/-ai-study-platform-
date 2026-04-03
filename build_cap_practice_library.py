from __future__ import annotations

import io
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import fitz
import numpy as np
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
CAP_RENDER_SCALE = 1.75

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
OPTION_KEYS = ("A", "B", "C", "D")
OPTION_MARKER_RE = re.compile(r"^[\(\[\{（]?\s*([ABCD])\s*[\)\]\}）\.．:]?$", re.IGNORECASE)
QUESTION_NUMBER_RE = re.compile(r"^(\d{1,2})(?:[\.．、\)]?)$")


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
                "crop_box": {
                    "x0": round(band_left / width, 6),
                    "y0": round(top / height, 6),
                    "x1": round(band_right / width, 6),
                    "y1": round(bottom / height, 6),
                },
            }
        )
    return extracted


def normalize_option_marker_token(text: str) -> str:
    token = normalize_whitespace(text).upper()
    token = (
        token.replace("（", "(")
        .replace("）", ")")
        .replace("【", "(")
        .replace("】", ")")
        .replace("．", ".")
    )
    match = OPTION_MARKER_RE.match(token)
    if match:
        return match.group(1)
    if token in OPTION_KEYS:
        return token
    return ""


def pdf_words_to_rows(page: fitz.Page) -> list[dict]:
    rows: list[dict] = []
    for word in page.get_text("words"):
        text = normalize_whitespace(word[4])
        if not text:
            continue
        rows.append(
            {
                "x0": float(word[0]),
                "y0": float(word[1]),
                "x1": float(word[2]),
                "y1": float(word[3]),
                "text": text,
                "confidence": 100.0,
                "source": "pdf",
            }
        )
    return rows


def normalize_crop_box_absolute(crop_box: dict | None, page_rect: fitz.Rect) -> tuple[float, float, float, float] | None:
    if not crop_box:
        return None
    try:
        return (
            float(crop_box["x0"]) * float(page_rect.width),
            float(crop_box["y0"]) * float(page_rect.height),
            float(crop_box["x1"]) * float(page_rect.width),
            float(crop_box["y1"]) * float(page_rect.height),
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_normalized_crop_box(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_rect: fitz.Rect,
) -> dict | None:
    width = float(page_rect.width or 0)
    height = float(page_rect.height or 0)
    if width <= 0 or height <= 0:
        return None

    x0 = max(0.0, min(width, x0))
    x1 = max(0.0, min(width, x1))
    y0 = max(0.0, min(height, y0))
    y1 = max(0.0, min(height, y1))
    if x1 - x0 < width * 0.015 or y1 - y0 < height * 0.015:
        return None

    return {
        "x0": round(x0 / width, 6),
        "y0": round(y0 / height, 6),
        "x1": round(x1 / width, 6),
        "y1": round(y1 / height, 6),
    }


def get_cap_page_analysis(
    document: fitz.Document,
    page_cache: dict[int, dict],
    page_number: int,
    subject_slug: str,
) -> dict:
    analysis = page_cache.get(page_number)
    if analysis:
        return analysis

    page = document[page_number - 1]
    analysis = {
        "page": page,
        "page_rect": page.rect,
        "pdf_rows": pdf_words_to_rows(page),
        "ocr_rows": None,
        "ocr_subject": subject_slug,
    }
    page_cache[page_number] = analysis
    return analysis


def get_cap_page_render_data(analysis: dict, dpi: int = 300) -> dict:
    cache_key = f"render_{dpi}"
    cached = analysis.get(cache_key)
    if cached:
        return cached

    image = Image.open(io.BytesIO(render_page_png(analysis["page"], dpi=dpi))).convert("RGB")
    width, height = image.size
    page_rect = analysis["page_rect"]
    render_data = {
        "image": image,
        "width": width,
        "height": height,
        "scale_x": width / float(page_rect.width or 1.0),
        "scale_y": height / float(page_rect.height or 1.0),
    }
    analysis[cache_key] = render_data
    return render_data


def collect_rows_in_crop(
    analysis: dict,
    absolute_crop: tuple[float, float, float, float],
    subject_slug: str,
    margin: float = 6.0,
) -> list[dict]:
    x0, y0, x1, y1 = absolute_crop

    def within(rows: list[dict]) -> list[dict]:
        return [
            row
            for row in rows
            if float(row["x1"]) >= x0 - margin
            and float(row["x0"]) <= x1 + margin
            and float(row["y1"]) >= y0 - margin
            and float(row["y0"]) <= y1 + margin
        ]

    rows = within(analysis["pdf_rows"])
    if rows:
        return rows
    return within(ensure_cap_page_ocr_rows(analysis, subject_slug))


def infer_question_visual_crop_box(
    analysis: dict,
    crop_box: dict | None,
    subject_slug: str,
) -> dict | None:
    page_rect = analysis["page_rect"]
    absolute = normalize_crop_box_absolute(crop_box, page_rect)
    if not absolute:
        return None

    x0, y0, x1, y1 = absolute
    render = get_cap_page_render_data(analysis, dpi=300)
    scale_x = render["scale_x"]
    scale_y = render["scale_y"]
    image = np.array(render["image"])

    px0 = max(0, int(math.floor(x0 * scale_x)))
    py0 = max(0, int(math.floor(y0 * scale_y)))
    px1 = min(render["width"], int(math.ceil(x1 * scale_x)))
    py1 = min(render["height"], int(math.ceil(y1 * scale_y)))
    if px1 - px0 < 32 or py1 - py0 < 32:
        return None

    crop = image[py0:py1, px0:px1]
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    mask = (gray < 245).astype(np.uint8) * 255

    text_rows = collect_rows_in_crop(analysis, absolute, subject_slug)
    for row in text_rows:
        rx0 = max(0, int(math.floor((float(row["x0"]) - x0) * scale_x)) - 3)
        ry0 = max(0, int(math.floor((float(row["y0"]) - y0) * scale_y)) - 3)
        rx1 = min(mask.shape[1], int(math.ceil((float(row["x1"]) - x0) * scale_x)) + 3)
        ry1 = min(mask.shape[0], int(math.ceil((float(row["y1"]) - y0) * scale_y)) + 3)
        if rx1 <= rx0 or ry1 <= ry0:
            continue
        cv2.rectangle(mask, (rx0, ry0), (rx1, ry1), 0, thickness=-1)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    crop_area = float((px1 - px0) * (py1 - py0))
    min_component_area = max(500.0, crop_area * 0.015)
    boxes = []
    for index in range(1, component_count):
        area = float(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if area < min_component_area:
            continue
        if width < 20 or height < 20:
            continue
        left = int(stats[index, cv2.CC_STAT_LEFT])
        top = int(stats[index, cv2.CC_STAT_TOP])
        boxes.append((left, top, left + width, top + height))

    if not boxes:
        return None

    vx0 = min(box[0] for box in boxes)
    vy0 = min(box[1] for box in boxes)
    vx1 = max(box[2] for box in boxes)
    vy1 = max(box[3] for box in boxes)

    visual_area = float((vx1 - vx0) * (vy1 - vy0))
    if visual_area < crop_area * 0.02:
        return None

    if (vx1 - vx0) > (px1 - px0) * 0.96 and (vy1 - vy0) > (py1 - py0) * 0.9:
        return None

    return build_normalized_crop_box(
        x0 + (vx0 / scale_x),
        y0 + (vy0 / scale_y),
        x0 + (vx1 / scale_x),
        y0 + (vy1 / scale_y),
        page_rect,
    )


def ensure_cap_page_ocr_rows(analysis: dict, subject_slug: str) -> list[dict]:
    if analysis.get("ocr_rows") is not None and analysis.get("ocr_subject") == subject_slug:
        return analysis["ocr_rows"]

    page = analysis["page"]
    page_rect = analysis["page_rect"]
    page_image = Image.open(io.BytesIO(render_page_png(page, dpi=300)))
    image_width, image_height = page_image.size
    rows = run_tesseract_tsv_on_image(
        render_page_png(page, dpi=300),
        languages=get_scanned_fallback_languages(subject_slug),
        psm=6,
    )
    scaled_rows = []
    for row in rows:
        scaled_rows.append(
            {
                **row,
                "x0": float(row["x0"]) * page_rect.width / image_width,
                "y0": float(row["y0"]) * page_rect.height / image_height,
                "x1": float(row["x1"]) * page_rect.width / image_width,
                "y1": float(row["y1"]) * page_rect.height / image_height,
            }
        )
    analysis["ocr_rows"] = scaled_rows
    analysis["ocr_subject"] = subject_slug
    return scaled_rows


def find_question_number_rows(rows: list[dict], question_number: int, page_rect: fitz.Rect) -> list[dict]:
    matches = []
    number_text = str(question_number)
    left_limit = float(page_rect.width) * 0.22
    for row in rows:
        text = normalize_whitespace(row.get("text", ""))
        if not text or float(row.get("x0", 0)) > left_limit:
            continue
        match = QUESTION_NUMBER_RE.match(text)
        if match and match.group(1) == number_text:
            matches.append(row)
            continue
        if text == number_text:
            matches.append(row)
    return sorted(matches, key=lambda item: (item["y0"], item["x0"]))


def infer_question_band_crop_box(
    analysis: dict,
    question_number: int,
    fallback_crop_box: dict | None = None,
) -> dict | None:
    page_rect = analysis["page_rect"]
    fallback_absolute = normalize_crop_box_absolute(fallback_crop_box, page_rect)
    if fallback_absolute:
        return build_normalized_crop_box(*fallback_absolute, page_rect)

    question_rows = find_question_number_rows(analysis["pdf_rows"], question_number, page_rect)
    if not question_rows:
        question_rows = find_question_number_rows(
            ensure_cap_page_ocr_rows(analysis, analysis.get("ocr_subject") or "chi_tra+eng"),
            question_number,
            page_rect,
        )
    if not question_rows:
        return None

    current_row = question_rows[0]
    next_rows = find_question_number_rows(analysis["pdf_rows"], question_number + 1, page_rect)
    if not next_rows:
        next_rows = find_question_number_rows(
            ensure_cap_page_ocr_rows(analysis, analysis.get("ocr_subject") or "chi_tra+eng"),
            question_number + 1,
            page_rect,
        )
    next_row = next_rows[0] if next_rows else None

    top = max(0.0, float(current_row["y0"]) - 8.0)
    bottom = float(next_row["y0"]) - 8.0 if next_row else float(page_rect.height) - 12.0
    left = float(page_rect.width) * 0.06
    right = float(page_rect.width) * 0.98
    return build_normalized_crop_box(left, top, right, bottom, page_rect)


def find_option_markers_in_band(
    analysis: dict,
    crop_box: dict | None,
    subject_slug: str,
) -> list[dict]:
    if not crop_box:
        return []

    page_rect = analysis["page_rect"]
    absolute = normalize_crop_box_absolute(crop_box, page_rect)
    if not absolute:
        return []
    x0, y0, x1, y1 = absolute
    marker_candidates: list[dict] = []

    def collect(rows: list[dict]):
        for row in rows:
            if row["x0"] < x0 - 8 or row["x1"] > x1 + 8:
                continue
            if row["y0"] < y0 - 8 or row["y1"] > y1 + 8:
                continue
            raw_text = normalize_whitespace(row.get("text", ""))
            marker_key = normalize_option_marker_token(raw_text)
            if not marker_key:
                continue
            marker_candidates.append(
                {
                    "key": marker_key,
                    "x0": float(row["x0"]),
                    "y0": float(row["y0"]),
                    "x1": float(row["x1"]),
                    "y1": float(row["y1"]),
                    "source": row.get("source", "pdf"),
                    "raw_text": raw_text,
                    "has_affix": normalize_whitespace(raw_text).upper() not in OPTION_KEYS,
                }
            )

    collect(analysis["pdf_rows"])
    if len({item["key"] for item in marker_candidates}) < 4:
        collect(ensure_cap_page_ocr_rows(analysis, subject_slug))

    # Prefer canonical markers like "(A)" over bare letters because diagram labels
    # often contain A/B/C/D and would otherwise steal the option crop anchor.
    best_by_key: dict[str, dict] = {}
    for candidate in marker_candidates:
        existing = best_by_key.get(candidate["key"])
        if existing is None:
            best_by_key[candidate["key"]] = candidate
            continue

        candidate_rank = (
            0 if candidate.get("has_affix") else 1,
            float(candidate["y0"]),
            float(candidate["x0"]),
        )
        existing_rank = (
            0 if existing.get("has_affix") else 1,
            float(existing["y0"]),
            float(existing["x0"]),
        )
        if candidate_rank < existing_rank:
            best_by_key[candidate["key"]] = candidate

    return sorted(best_by_key.values(), key=lambda item: (item["y0"], item["x0"]))


def classify_option_marker_layout(markers: list[dict]) -> str:
    if len(markers) < 2:
        return "single"

    sorted_markers = sorted(markers, key=lambda item: (item["y0"], item["x0"]))
    row_groups: list[list[dict]] = []
    tolerance = 14.0
    for marker in sorted_markers:
        if not row_groups or abs(row_groups[-1][0]["y0"] - marker["y0"]) > tolerance:
            row_groups.append([marker])
        else:
            row_groups[-1].append(marker)

    if len(row_groups) == 1:
        return "horizontal"
    if len(row_groups) == 2 and all(len(group) <= 2 for group in row_groups):
        return "grid"
    return "vertical"


def build_question_and_option_crop_boxes(
    analysis: dict,
    crop_box: dict | None,
    markers: list[dict],
) -> tuple[dict | None, dict[str, dict], str]:
    if not crop_box:
        return None, {}, "none"

    page_rect = analysis["page_rect"]
    absolute = normalize_crop_box_absolute(crop_box, page_rect)
    if not absolute:
        return crop_box, {}, "none"
    band_x0, band_y0, band_x1, band_y1 = absolute

    if not markers:
        return crop_box, {}, "single"

    layout = classify_option_marker_layout(markers)
    question_crop_box = crop_box
    option_crop_boxes: dict[str, dict] = {}
    top_marker = min(markers, key=lambda item: item["y0"])
    question_bottom = max(band_y0 + 24.0, top_marker["y0"] - 4.0)
    inferred_question_crop = build_normalized_crop_box(band_x0, band_y0, band_x1, question_bottom, page_rect)
    if inferred_question_crop:
        question_crop_box = inferred_question_crop

    if layout == "vertical":
        ordered = sorted(markers, key=lambda item: item["y0"])
        for index, marker in enumerate(ordered):
            next_y = ordered[index + 1]["y0"] - 8.0 if index + 1 < len(ordered) else band_y1
            option_box = build_normalized_crop_box(
                band_x0,
                marker["y0"] - 2.0,
                band_x1,
                next_y,
                page_rect,
            )
            if option_box:
                option_crop_boxes[marker["key"]] = option_box
        return question_crop_box, option_crop_boxes, layout

    if layout in {"horizontal", "grid"}:
        row_groups: list[list[dict]] = []
        tolerance = 14.0
        for marker in sorted(markers, key=lambda item: (item["y0"], item["x0"])):
            if not row_groups or abs(row_groups[-1][0]["y0"] - marker["y0"]) > tolerance:
                row_groups.append([marker])
            else:
                row_groups[-1].append(marker)

        for row_index, row_group in enumerate(row_groups):
            row_group = sorted(row_group, key=lambda item: item["x0"])
            row_top = row_group[0]["y0"] - 2.0
            row_bottom = row_groups[row_index + 1][0]["y0"] - 8.0 if row_index + 1 < len(row_groups) else band_y1
            boundaries = [band_x0]
            centers = [((marker["x0"] + marker["x1"]) / 2.0) for marker in row_group]
            for index in range(len(centers) - 1):
                boundaries.append((centers[index] + centers[index + 1]) / 2.0)
            boundaries.append(band_x1)

            for index, marker in enumerate(row_group):
                option_box = build_normalized_crop_box(
                    boundaries[index],
                    row_top,
                    boundaries[index + 1],
                    row_bottom,
                    page_rect,
                )
                if option_box:
                    option_crop_boxes[marker["key"]] = option_box
        return question_crop_box, option_crop_boxes, layout

    return question_crop_box, option_crop_boxes, layout


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
            if page_number == 1 and str(year) not in {"102", "103"}:
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


def should_prioritize_visual(year: str, subject_slug: str, stem: str, options: dict[str, str], parse_status: str) -> bool:
    if str(year) in {"102", "103"}:
        return True
    if parse_status != "complete":
        return True
    if len(options) < 4:
        return True

    combined = normalize_whitespace(
        " ".join([stem, *(str(value or "") for value in (options or {}).values())])
    )
    if not combined:
        return True

    readable_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", combined))
    suspicious_chars = len(re.findall(r"[�\ufffd]|[?]{2,}|[A-Za-z]{5,}\s+[A-Za-z]{5,}", combined))
    return readable_chars < 24 or suspicious_chars > 0


def should_extract_option_visuals(question_payload: dict) -> bool:
    options = question_payload.get("options") or {}
    if question_payload.get("visual_primary"):
        return True
    return any(not normalize_whitespace(options.get(key, "")) for key in OPTION_KEYS)


def infer_missing_question_page(
    candidate_buckets: dict[int, list[dict]],
    missing_number: int,
    default_page: int = 1,
) -> int:
    previous_candidates = [number for number in candidate_buckets if number < missing_number]
    next_candidates = [number for number in candidate_buckets if number > missing_number]

    previous_page = None
    next_page = None
    if previous_candidates:
        previous_page = candidate_buckets[max(previous_candidates)][0].get("page_number")
    if next_candidates:
        next_page = candidate_buckets[min(next_candidates)][0].get("page_number")

    if previous_page and next_page and previous_page == next_page:
        return int(previous_page)
    if next_page:
        return int(next_page)
    if previous_page:
        return int(previous_page)
    return int(default_page)


def ensure_cap_page_assets(pdf_path: Path, year: str, subject_slug: str) -> dict[int, str]:
    asset_map: dict[int, str] = {}
    with fitz.open(pdf_path) as document:
        for page_index in range(document.page_count):
            asset_map[page_index + 1] = str(
                Path("cap_practice_assets") / year / subject_slug / f"page_{page_index + 1:02d}.png"
            )
    return asset_map


def _fitz_clip_from_normalized_crop(page_rect, crop_box):
    if not crop_box:
        return None
    try:
        x0 = float(crop_box["x0"])
        y0 = float(crop_box["y0"])
        x1 = float(crop_box["x1"])
        y1 = float(crop_box["y1"])
    except (TypeError, ValueError, KeyError):
        return None

    clip = fitz.Rect(
        max(0.0, min(page_rect.width, page_rect.width * x0)),
        max(0.0, min(page_rect.height, page_rect.height * y0)),
        max(0.0, min(page_rect.width, page_rect.width * x1)),
        max(0.0, min(page_rect.height, page_rect.height * y1)),
    )
    if clip.is_empty or clip.width < 8 or clip.height < 8:
        return None
    return clip


def trim_cap_rendered_crop(image: Image.Image, asset_kind: str) -> Image.Image | None:
    rgb_image = image.convert("RGB")
    image_array = np.array(rgb_image)
    if image_array.size == 0:
        return None

    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    mask = (gray < 246).astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    image_area = float(image_array.shape[0] * image_array.shape[1])
    min_area = max(18.0, image_area * 0.00015)
    boxes = []
    for index in range(1, component_count):
        area = float(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if area < min_area or width < 2 or height < 2:
            continue
        left = int(stats[index, cv2.CC_STAT_LEFT])
        top = int(stats[index, cv2.CC_STAT_TOP])
        boxes.append((left, top, left + width, top + height))

    if not boxes:
        return None

    if asset_kind == "option" and len(boxes) >= 2:
        ordered_boxes = sorted(boxes, key=lambda box: box[0])
        large_gap_threshold = max(96, int(rgb_image.width * 0.15))
        first_large_gap_index = None
        for index in range(len(ordered_boxes) - 1):
            gap = ordered_boxes[index + 1][0] - ordered_boxes[index][2]
            if gap >= large_gap_threshold:
                first_large_gap_index = index
                break

        if first_large_gap_index is not None:
            left_cluster = ordered_boxes[: first_large_gap_index + 1]
            left_cluster_right = max(box[2] for box in left_cluster)
            if left_cluster_right <= max(120, int(rgb_image.width * 0.2)):
                boxes = left_cluster

    pad_x = 10 if asset_kind == "option" else 14
    pad_y = 8 if asset_kind == "option" else 12
    left = max(0, min(box[0] for box in boxes) - pad_x)
    top = max(0, min(box[1] for box in boxes) - pad_y)
    right = min(rgb_image.width, max(box[2] for box in boxes) + pad_x)
    bottom = min(rgb_image.height, max(box[3] for box in boxes) + pad_y)

    if right - left < 12 or bottom - top < 12:
        return None

    trimmed_image = rgb_image.crop((left, top, right, bottom))
    trimmed_gray = cv2.cvtColor(np.array(trimmed_image), cv2.COLOR_RGB2GRAY)
    height, width = trimmed_gray.shape[:2]
    dark_ratio = float(np.mean(trimmed_gray < 150))
    mid_gray_ratio = float(np.mean((trimmed_gray >= 150) & (trimmed_gray < 245)))
    gray_std = float(np.std(trimmed_gray))

    # Scan artifacts often appear as a very wide, nearly-flat gray stripe.
    if asset_kind in {"question", "group"} and width >= height * 8 and height <= 120:
        if (mid_gray_ratio > 0.75 and dark_ratio < 0.08) or gray_std < 6.0:
            return None

    return trimmed_image


def render_cap_crop_asset(
    source_document,
    page_number: int,
    crop_box: dict | None,
    target_path: Path,
    asset_kind: str = "question",
) -> str | None:
    try:
        page = source_document.load_page(max(0, int(page_number) - 1))
    except (TypeError, ValueError, IndexError, RuntimeError):
        return None

    clip = _fitz_clip_from_normalized_crop(page.rect, crop_box)
    if clip is None:
        return None

    ensure_dir(target_path.parent)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(CAP_RENDER_SCALE, CAP_RENDER_SCALE), clip=clip, alpha=False)
    output_image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    trimmed_image = trim_cap_rendered_crop(output_image, asset_kind)
    if trimmed_image is None:
        if target_path.exists():
            target_path.unlink()
        return None
    trimmed_image.save(target_path, optimize=True)
    return str(target_path.relative_to(DATA_ROOT)).replace("\\", "/")


def build_cap_question_asset_paths(question_payload: dict) -> dict:
    asset_paths = {
        "question_image_path": None,
        "group_image_path": None,
        "option_image_paths": {},
    }

    year = str(question_payload.get("year") or "").strip()
    subject_slug = str(question_payload.get("subject_slug") or "").strip()
    page_number = question_payload.get("page_number")
    display_number = int(question_payload.get("display_number") or question_payload.get("number") or 0)

    if not year or not subject_slug or not page_number or display_number <= 0:
        return asset_paths

    asset_dir = CAP_ASSET_ROOT / year / subject_slug
    if question_payload.get("question_visual_crop_box") or question_payload.get("question_crop_box"):
        asset_paths["question_image_path"] = str(
            (asset_dir / f"q{display_number:03d}_question.png").relative_to(DATA_ROOT)
        ).replace("\\", "/")
    if question_payload.get("group_crop_box"):
        asset_paths["group_image_path"] = str(
            (asset_dir / f"q{display_number:03d}_group.png").relative_to(DATA_ROOT)
        ).replace("\\", "/")

    option_paths = {}
    for key, crop_box in (question_payload.get("option_crop_boxes") or {}).items():
        if not crop_box:
            continue
        option_paths[key] = str(
            (asset_dir / f"q{display_number:03d}_option_{key}.png").relative_to(DATA_ROOT)
        ).replace("\\", "/")
    asset_paths["option_image_paths"] = option_paths
    return asset_paths


def materialize_cap_question_assets(source_document, year: str, subject_slug: str, question_payload: dict) -> None:
    page_number = question_payload.get("page_number")
    display_number = int(question_payload.get("display_number") or question_payload.get("number") or 0)
    if not page_number or display_number <= 0:
        return

    asset_dir = CAP_ASSET_ROOT / year / subject_slug
    stale_prefix = f"q{display_number:03d}_"
    stale_question_path = asset_dir / f"{stale_prefix}question.png"
    stale_group_path = asset_dir / f"{stale_prefix}group.png"
    if stale_question_path.exists():
        stale_question_path.unlink()
    if stale_group_path.exists():
        stale_group_path.unlink()
    for stale_option_path in asset_dir.glob(f"{stale_prefix}option_*.png"):
        stale_option_path.unlink()

    question_payload["question_image_path"] = None
    question_payload["group_image_path"] = None
    question_payload["option_image_paths"] = {}

    has_explicit_visual_reference = question_has_visual_reference(question_payload)
    stem_text = normalize_whitespace(question_payload.get("stem") or "")
    question_crop = question_payload.get("question_visual_crop_box")
    if not question_crop and (has_explicit_visual_reference or not stem_text):
        question_crop = question_payload.get("question_crop_box")

    question_image_path = None
    if question_crop:
        question_image_path = render_cap_crop_asset(
            source_document,
            int(page_number),
            question_crop,
            asset_dir / f"q{display_number:03d}_question.png",
            asset_kind="question",
        )
    if (
        not question_image_path
        and question_payload.get("question_visual_crop_box")
        and question_payload.get("question_crop_box")
        and (has_explicit_visual_reference or not stem_text)
    ):
        question_image_path = render_cap_crop_asset(
            source_document,
            int(page_number),
            question_payload.get("question_crop_box"),
            asset_dir / f"q{display_number:03d}_question.png",
            asset_kind="question",
        )
    if question_image_path:
        question_payload["question_image_path"] = question_image_path

    if question_payload.get("group_crop_box"):
        group_image_path = render_cap_crop_asset(
            source_document,
            int(page_number),
            question_payload.get("group_crop_box"),
            asset_dir / f"q{display_number:03d}_group.png",
            asset_kind="group",
        )
        if group_image_path:
            question_payload["group_image_path"] = group_image_path

    option_image_paths = {}
    option_texts = question_payload.get("options") or {}
    for option_key, option_crop in (question_payload.get("option_crop_boxes") or {}).items():
        option_text = normalize_whitespace(option_texts.get(option_key) or "")
        if not option_crop or option_text:
            continue
        option_image_path = render_cap_crop_asset(
            source_document,
            int(page_number),
            option_crop,
            asset_dir / f"q{display_number:03d}_option_{option_key}.png",
            asset_kind="option",
        )
        if option_image_path:
            option_image_paths[option_key] = option_image_path
    question_payload["option_image_paths"] = option_image_paths


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
    should_collect_scanned_fallback = (
        str(year) in {"102", "103"}
        or official_question_count is None
        or raw_unique_count != official_question_count
    )
    if should_collect_scanned_fallback:
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
                "crop_box": item.get("crop_box"),
                "context": context,
                "stem": stem,
                "options": options,
                "correct_answer": correct_answer,
                "parse_status": parse_status,
                "candidate_score": score_question_candidate(stem, options, context, correct_answer),
            }
        )

    if official_question_count:
        for missing_number in range(1, official_question_count + 1):
            if missing_number in candidate_buckets:
                continue
            inferred_page = infer_missing_question_page(candidate_buckets, missing_number, default_page=1)
            fallback_answer = answer_map.get(missing_number, "")
            candidate_buckets[missing_number].append(
                {
                    "number": missing_number,
                    "source_number": missing_number,
                    "page_number": inferred_page,
                    "page_image_path": page_assets.get(inferred_page),
                    "crop_box": None,
                    "context": "",
                    "stem": "",
                    "options": {"A": "", "B": "", "C": "", "D": ""},
                    "correct_answer": fallback_answer,
                    "parse_status": "missing_question_visual_fallback",
                    "candidate_score": -1,
                }
            )
            issues.append(
                {
                    "question_number": missing_number,
                    "display_source_number": missing_number,
                    "reason": "missing_question_visual_fallback",
                    "page_number": inferred_page,
                }
            )

    page_cache: dict[int, dict] = {}
    with fitz.open(pdf_path) as source_document:
        for normalized_number in sorted(candidate_buckets):
            candidates = sorted(
                candidate_buckets[normalized_number],
                key=lambda item: (item["candidate_score"], len(item["options"]), len(item["stem"])),
                reverse=True,
            )
            best = candidates[0]
            crop_box = best.get("crop_box")
            if not crop_box:
                for candidate in candidates:
                    if candidate.get("crop_box"):
                        crop_box = candidate["crop_box"]
                        break
            question_payload = {
                "year": year,
                "subject_slug": subject_slug,
                "number": best["number"],
                "source_number": best["source_number"],
                "display_number": len(questions) + 1,
                "page_number": best["page_number"],
                "page_image_path": best["page_image_path"],
                "crop_box": crop_box,
                "question_crop_box": crop_box,
                "question_visual_crop_box": None,
                "group_crop_box": None,
                "option_crop_boxes": {},
                "question_image_path": None,
                "group_image_path": None,
                "option_image_paths": {},
                "option_layout": "none",
                "parse_status": best["parse_status"],
                "context": best["context"],
                "stem": best["stem"],
                "options": best["options"],
                "correct_answer": best["correct_answer"],
            }
            question_payload["visual_primary"] = should_prioritize_visual(
                year,
                subject_slug,
                question_payload["stem"],
                question_payload["options"],
                question_payload["parse_status"],
            )

            page_number = question_payload.get("page_number")
            if page_number:
                analysis = get_cap_page_analysis(source_document, page_cache, page_number, subject_slug)
                band_crop_box = infer_question_band_crop_box(
                    analysis,
                    int(best["source_number"]),
                    fallback_crop_box=crop_box,
                )
                if band_crop_box:
                    question_payload["crop_box"] = band_crop_box
                    question_payload["question_crop_box"] = band_crop_box
                    markers = find_option_markers_in_band(analysis, band_crop_box, subject_slug)
                    question_crop_box, option_crop_boxes, option_layout = build_question_and_option_crop_boxes(
                        analysis,
                        band_crop_box,
                        markers,
                    )
                    question_payload["question_crop_box"] = question_crop_box or band_crop_box
                    question_payload["question_visual_crop_box"] = infer_question_visual_crop_box(
                        analysis,
                        question_payload["question_crop_box"],
                        subject_slug,
                    )
                    question_payload["option_layout"] = option_layout
                    if should_extract_option_visuals(question_payload):
                        question_payload["option_crop_boxes"] = option_crop_boxes
                    if question_payload["context"] and question_has_visual_reference(question_payload):
                        question_payload["group_crop_box"] = (
                            question_payload["question_visual_crop_box"]
                            or question_payload["question_crop_box"]
                        )

            materialize_cap_question_assets(source_document, year, subject_slug, question_payload)

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


def refresh_existing_visual_crops() -> dict:
    manifest = load_cap_manifest()
    refreshed = []

    for year_entry in sorted(manifest.get("years", []), key=lambda item: str(item.get("year"))):
        year = str(year_entry["year"])
        for subject_entry in year_entry.get("subjects", []):
            subject_slug = subject_entry["slug"]
            structured_path = CAP_STRUCTURED_ROOT / year / f"{subject_slug}.json"
            if not structured_path.exists():
                continue

            import json

            payload = json.loads(structured_path.read_text(encoding="utf-8"))
            pdf_relative = (payload.get("files") or {}).get("pdf")
            if not pdf_relative:
                continue
            pdf_path = DATA_ROOT / pdf_relative
            if not pdf_path.exists():
                continue

            changed = 0
            page_cache: dict[int, dict] = {}
            with fitz.open(pdf_path) as source_document:
                for question in payload.get("questions", []):
                    page_number = question.get("page_number")
                    band_crop_box = question.get("crop_box") or question.get("question_crop_box")
                    if not page_number or not band_crop_box:
                        continue

                    analysis = get_cap_page_analysis(source_document, page_cache, int(page_number), subject_slug)
                    markers = find_option_markers_in_band(analysis, band_crop_box, subject_slug)
                    question_crop_box, option_crop_boxes, option_layout = build_question_and_option_crop_boxes(
                        analysis,
                        band_crop_box,
                        markers,
                    )
                    if question_crop_box and question_crop_box != question.get("question_crop_box"):
                        question["question_crop_box"] = question_crop_box
                        changed += 1
                    if option_crop_boxes != (question.get("option_crop_boxes") or {}):
                        question["option_crop_boxes"] = option_crop_boxes
                        changed += 1
                    if option_layout != question.get("option_layout"):
                        question["option_layout"] = option_layout
                        changed += 1

                    visual_crop_box = infer_question_visual_crop_box(
                        analysis,
                        question.get("question_crop_box") or band_crop_box,
                        subject_slug,
                    )
                    if visual_crop_box != question.get("question_visual_crop_box"):
                        question["question_visual_crop_box"] = visual_crop_box
                        changed += 1

                    if question.get("context") and question_has_visual_reference(question):
                        next_group_crop = visual_crop_box or question.get("group_crop_box") or question_crop_box
                        if next_group_crop != question.get("group_crop_box"):
                            question["group_crop_box"] = next_group_crop
                            changed += 1

                    before_question_path = question.get("question_image_path")
                    before_group_path = question.get("group_image_path")
                    before_option_paths = dict(question.get("option_image_paths") or {})
                    materialize_cap_question_assets(source_document, year, subject_slug, question)
                    if (
                        question.get("question_image_path") != before_question_path
                        or question.get("group_image_path") != before_group_path
                        or dict(question.get("option_image_paths") or {}) != before_option_paths
                    ):
                        changed += 1

            if changed:
                write_json(structured_path, payload)
            refreshed.append(
                {
                    "year": year,
                    "subject": subject_slug,
                    "changed": changed,
                    "question_count": len(payload.get("questions") or []),
                }
            )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subjects": refreshed,
    }


if __name__ == "__main__":
    result = build_library()
    print(f"years: {len(result['years'])}")
    print(f"subjects: {sum(len(year['subjects']) for year in result['years'])}")
