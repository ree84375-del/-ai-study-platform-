from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.utils.document_ingest import load_json, normalize_whitespace


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
GUIDE_LIBRARY_MANIFEST_PATH = DATA_ROOT / "study_guides" / "guide_library_manifest.json"
CAP_LIBRARY_MANIFEST_PATH = DATA_ROOT / "cap_review" / "cap_practice_manifest.json"
CAP_LIBRARY_AUDIT_PATH = DATA_ROOT / "cap_review" / "cap_rebuild_audit.json"
GUIDE_STRUCTURED_ROOT = DATA_ROOT / "guide_structured" / "king_an"

PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")
CONTROL_RE = re.compile(r"[\u0000-\u001f\u007f]")
SHORT_ASCII_CLUSTER_RE = re.compile(r"(?:\b[A-Za-z]{1,4}\b(?:\s+|$)){5,}")
SUSPICIOUS_GUIDE_SNIPPETS = (
    "Go 考 Beh",
    "Beh eee",
    "SHARP WEAR",
    "BHF!",
    "ASUS ER",
)

GUIDE_SUBJECT_META = {
    "chinese": {
        "label": "國文",
        "icon": "fa-book-open",
        "description": "整理文本重點、題型策略與閱讀脈絡，適合先看講義再回去練題。",
    },
    "english": {
        "label": "英語",
        "icon": "fa-language",
        "description": "把複習講義拆成章與小節，閱讀時先看重點，再搭配原始講義頁面對照。",
    },
    "math": {
        "label": "數學",
        "icon": "fa-calculator",
        "description": "公式、解題策略與章節重點拆開整理，閱讀節奏會比原始檔更清楚。",
    },
    "nature": {
        "label": "自然",
        "icon": "fa-seedling",
        "description": "生物、理化、地科的講義都會依章節整理，方便直接按單元閱讀。",
    },
    "social": {
        "label": "社會",
        "icon": "fa-landmark-flag",
        "description": "地理、歷史、公民的複習講義都能按章節閱讀，快速找到想複習的主題。",
    },
}

CAP_SUBJECT_META = {
    "chinese": {
        "label": "國文",
        "icon": "fa-book-open",
        "description": "閱讀題組、語文理解與文本判讀，適合先預覽再正式作答。",
    },
    "english": {
        "label": "英語",
        "icon": "fa-language",
        "description": "只收閱讀題，方便直接做互動式練習，不混入聽力題。",
    },
    "math": {
        "label": "數學",
        "icon": "fa-calculator",
        "description": "目前只收選擇題，保留圖像頁面並逐題作答，不先混入非選。",
    },
    "social": {
        "label": "社會",
        "icon": "fa-landmark",
        "description": "整合地理、歷史、公民的會考題，題組與材料頁會保留在一起。",
    },
    "science": {
        "label": "自然",
        "icon": "fa-flask",
        "description": "圖表與題組會整塊顯示，避免把實驗與情境題切得太碎。",
    },
}

GUIDE_SUBJECT_ORDER = ["chinese", "english", "math", "nature", "social"]
CAP_SUBJECT_ORDER = ["chinese", "english", "math", "social", "science"]


def load_relative_json(relative_path: str) -> dict:
    if not relative_path:
        return {}
    normalized = str(relative_path).replace("\\", "/").strip("/")
    return load_json(DATA_ROOT / normalized, default={})


@lru_cache(maxsize=1)
def load_guide_library_manifest() -> dict:
    return load_json(GUIDE_LIBRARY_MANIFEST_PATH, default={"subjects": [], "issues": []})


@lru_cache(maxsize=1)
def load_cap_library_manifest() -> dict:
    return load_json(CAP_LIBRARY_MANIFEST_PATH, default={"years": []})


@lru_cache(maxsize=1)
def load_cap_library_audit() -> dict:
    return load_json(CAP_LIBRARY_AUDIT_PATH, default={"years": []})


def _count_sections(chapters: list[dict]) -> int:
    return sum(len(chapter.get("sections", [])) for chapter in chapters)


def sanitize_guide_text(text: str | None) -> str:
    raw = str(text or "")
    if not raw:
        return ""

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.replace("\u3000", " ").replace("\xa0", " ")
    raw = PRIVATE_USE_RE.sub("", raw)
    raw = CONTROL_RE.sub(" ", raw)

    lines = []
    for line in raw.splitlines():
        normalized = normalize_whitespace(line)
        if not normalized:
            continue
        normalized = normalized.strip("•·▪◆◇■□▶►")
        normalized = normalize_whitespace(normalized)
        if normalized:
            lines.append(normalized)
    return "\n".join(lines).strip()


def sanitize_guide_title(text: str | None, fallback: str = "") -> str:
    cleaned = sanitize_guide_text(text).replace("\n", " ")
    cleaned = normalize_whitespace(cleaned)
    return cleaned or fallback


def guide_text_looks_garbled(text: str | None, subject_slug: str | None = None) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return True

    cleaned = sanitize_guide_text(raw)
    if not cleaned:
        return True

    if "�" in raw:
        return True
    if any(snippet in cleaned for snippet in SUSPICIOUS_GUIDE_SNIPPETS):
        return True

    private_use_count = len(PRIVATE_USE_RE.findall(raw))
    if private_use_count >= 8:
        return True

    if subject_slug == "english" and SHORT_ASCII_CLUSTER_RE.search(cleaned):
        return True

    ascii_tokens = re.findall(r"[A-Za-z]{1,4}", cleaned)
    if ascii_tokens:
        short_ratio = sum(1 for token in ascii_tokens if len(token) <= 3) / len(ascii_tokens)
        if short_ratio > 0.72 and len(ascii_tokens) >= 12 and "." not in cleaned and "?" not in cleaned:
            return True

    return False


def _clean_summary_lines(lines: list[str] | None, subject_slug: str | None = None, limit: int = 6) -> list[str]:
    cleaned_lines = []
    for raw_line in lines or []:
        line = sanitize_guide_title(raw_line)
        if not line or guide_text_looks_garbled(line, subject_slug):
            continue
        if line in cleaned_lines:
            continue
        cleaned_lines.append(line)
        if len(cleaned_lines) >= limit:
            break
    return cleaned_lines


def _clip_catalog_line(text: str, limit: int = 56) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _fallback_summary_from_content(content: str, limit: int = 3) -> list[str]:
    cleaned = sanitize_guide_text(content)
    if not cleaned:
        return []
    lines = []
    for line in cleaned.splitlines():
        if len(line) < 8:
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _cap_audit_lookup() -> dict[str, dict[str, int]]:
    audit = load_cap_library_audit()
    lookup: dict[str, dict[str, int]] = {}
    for year_entry in audit.get("years", []):
        lookup[str(year_entry.get("year"))] = {
            str(slug): int(count)
            for slug, count in (year_entry.get("subjects") or {}).items()
        }
    return lookup


def _is_cap_subject_verified(year_value: str, subject_entry: dict) -> bool:
    expected = _cap_audit_lookup().get(str(year_value), {}).get(str(subject_entry.get("slug")))
    if expected is None:
        return False
    return int(subject_entry.get("question_count", 0) or 0) == int(expected)


def build_guide_reader_payload(guide_document: dict, subject_slug: str | None = None) -> dict:
    raw_chapters = guide_document.get("chapters") or []
    chapters = []
    visual_section_count = 0

    for chapter_index, raw_chapter in enumerate(raw_chapters, start=1):
        chapter_title = sanitize_guide_title(raw_chapter.get("title"), f"第 {chapter_index} 章")
        page_start = int(raw_chapter.get("page_start") or 1)
        page_end = int(raw_chapter.get("page_end") or page_start)
        sections = []
        chapter_visual_count = 0

        for section_index, raw_section in enumerate(raw_chapter.get("sections") or [], start=1):
            section_title = sanitize_guide_title(raw_section.get("title"), f"第 {section_index} 小節")
            summary_points = _clean_summary_lines(raw_section.get("summary_points") or [], subject_slug, limit=4)
            raw_content = raw_section.get("content") or ""
            visual_fallback = guide_text_looks_garbled(raw_content, subject_slug)
            display_content = "" if visual_fallback else sanitize_guide_text(raw_content)
            if not summary_points and display_content:
                summary_points = _fallback_summary_from_content(display_content, limit=3)
            if visual_fallback:
                chapter_visual_count += 1
                visual_section_count += 1

            sections.append(
                {
                    "title": section_title,
                    "page_start": int(raw_section.get("page_start") or page_start),
                    "page_end": int(raw_section.get("page_end") or page_end),
                    "summary_points": summary_points,
                    "display_content": display_content,
                    "visual_fallback": visual_fallback,
                }
            )

        chapters.append(
            {
                "title": chapter_title,
                "page_start": page_start,
                "page_end": page_end,
                "page_numbers": list(range(page_start, page_end + 1)),
                "sections": sections,
                "section_count": len(sections),
                "has_visual_fallback": chapter_visual_count > 0,
                "uses_visual_primary": bool(sections) and chapter_visual_count == len(sections),
            }
        )

    summary = _clean_summary_lines(guide_document.get("summary") or [], subject_slug, limit=6)
    if not summary:
        summary = [chapter["title"] for chapter in chapters[:4]]

    return {
        "title": sanitize_guide_title(guide_document.get("title"), "未命名講義"),
        "summary": summary,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "section_count": sum(chapter["section_count"] for chapter in chapters),
        "page_count": int(guide_document.get("page_count") or 0),
        "has_visual_fallback": visual_section_count > 0,
        "visual_section_count": visual_section_count,
    }


@lru_cache(maxsize=1)
def build_guide_library_catalog() -> list[dict]:
    catalog: list[dict] = []

    for subject_slug in GUIDE_SUBJECT_ORDER:
        meta = GUIDE_SUBJECT_META[subject_slug]
        subject_dir = GUIDE_STRUCTURED_ROOT / subject_slug
        series_entries = []

        if subject_dir.exists():
            series_dirs = sorted((item for item in subject_dir.iterdir() if item.is_dir()), key=lambda path: path.name)
            for series_dir in series_dirs:
                guide_entries = []
                for guide_path in sorted(series_dir.glob("*.json"), key=lambda path: path.name):
                    document = load_json(guide_path, default={})
                    if not document:
                        continue

                    reader_payload = build_guide_reader_payload(document, subject_slug)
                    guide_entries.append(
                        {
                            "guide_value": guide_path.stem,
                            "title": reader_payload["title"],
                            "document_path": str(guide_path.relative_to(DATA_ROOT)).replace("\\", "/"),
                            "chapter_count": reader_payload["chapter_count"],
                            "section_count": reader_payload["section_count"],
                            "page_count": reader_payload["page_count"],
                            "summary": [_clip_catalog_line(line) for line in reader_payload["summary"][:3]],
                            "chapter_titles": [chapter["title"] for chapter in reader_payload["chapters"][:3]],
                            "text_quality": (
                                "visual"
                                if reader_payload["chapter_count"] and reader_payload["visual_section_count"] >= max(1, reader_payload["section_count"] // 2)
                                else "clean"
                            ),
                        }
                    )

                if guide_entries:
                    series_entries.append(
                        {
                            "series_value": series_dir.name,
                            "label": sanitize_guide_title(series_dir.name, series_dir.name),
                            "guide_count": len(guide_entries),
                            "guides": guide_entries,
                        }
                    )

        catalog.append(
            {
                "slug": subject_slug,
                "label": meta["label"],
                "icon": meta["icon"],
                "description": meta["description"],
                "series": series_entries,
                "series_count": len(series_entries),
                "guide_count": sum(item["guide_count"] for item in series_entries),
                "available": bool(series_entries),
            }
        )

    return catalog


def get_guide_catalog_subject(catalog: list[dict], subject_slug: str | None) -> dict | None:
    if subject_slug:
        for subject in catalog:
            if subject.get("slug") == subject_slug:
                return subject
    for subject in catalog:
        if subject.get("available"):
            return subject
    return catalog[0] if catalog else None


def get_guide_catalog_series(subject_entry: dict | None, series_value: str | None) -> dict | None:
    if not subject_entry:
        return None
    if series_value:
        for series in subject_entry.get("series", []):
            if series.get("series_value") == series_value:
                return series
    series_list = subject_entry.get("series", [])
    return series_list[0] if series_list else None


def get_guide_catalog_guide(series_entry: dict | None, guide_value: str | None) -> dict | None:
    if not series_entry:
        return None
    if guide_value:
        for guide in series_entry.get("guides", []):
            if guide.get("guide_value") == guide_value:
                return guide
    guide_list = series_entry.get("guides", [])
    return guide_list[0] if guide_list else None


def get_guide_subject(manifest: dict, subject_slug: str | None) -> dict | None:
    return get_guide_catalog_subject(build_guide_library_catalog(), subject_slug)


def get_guide_series(subject_entry: dict | None, series_slug: str | None) -> dict | None:
    return get_guide_catalog_series(subject_entry, series_slug)


def get_guide_document(subject_entry: dict | None, series_entry: dict | None, guide_slug: str | None) -> dict | None:
    guide_entry = get_guide_catalog_guide(series_entry, guide_slug)
    if not guide_entry:
        return None
    return load_relative_json(guide_entry.get("document_path", ""))


def build_guide_subject_cards(manifest: dict, active_subject_slug: str | None = None) -> list[dict]:
    cards = []
    for subject in build_guide_library_catalog():
        cards.append(
            {
                "slug": subject.get("slug"),
                "label": subject.get("label"),
                "icon": subject.get("icon"),
                "description": subject.get("description"),
                "series_count": subject.get("series_count", 0),
                "guide_count": subject.get("guide_count", 0),
                "is_active": subject.get("slug") == active_subject_slug,
                "available": subject.get("available", False),
            }
        )
    return cards


def get_cap_years(manifest: dict) -> list[str]:
    return [str(year.get("year")) for year in manifest.get("years", [])]


def get_cap_year_entries(manifest: dict, selected_years: list[str]) -> list[dict]:
    lookup = {str(year.get("year")): year for year in manifest.get("years", [])}
    return [lookup[year] for year in selected_years if year in lookup]


def build_cap_subject_cards(manifest: dict, selected_years: list[str], active_subject_slug: str | None = None) -> list[dict]:
    counts = {}
    ready_counts = {}
    question_totals = {}

    for year_entry in get_cap_year_entries(manifest, selected_years):
        year_value = str(year_entry.get("year"))
        for subject in year_entry.get("subjects", []):
            slug = subject.get("slug")
            if not slug or not _is_cap_subject_verified(year_value, subject):
                continue
            counts[slug] = counts.get(slug, 0) + 1
            question_totals[slug] = question_totals.get(slug, 0) + int(subject.get("question_count", 0) or 0)
            if subject.get("practice_ready"):
                ready_counts[slug] = ready_counts.get(slug, 0) + 1

    cards = []
    for slug in CAP_SUBJECT_ORDER:
        meta = CAP_SUBJECT_META[slug]
        cards.append(
            {
                "slug": slug,
                "label": meta["label"],
                "icon": meta["icon"],
                "description": meta["description"],
                "year_count": counts.get(slug, 0),
                "ready_year_count": ready_counts.get(slug, 0),
                "question_count": question_totals.get(slug, 0),
                "is_active": slug == active_subject_slug,
                "available": counts.get(slug, 0) > 0,
            }
        )
    return cards


def load_cap_documents(manifest: dict, selected_years: list[str], subject_slug: str) -> list[dict]:
    documents = []
    for year_entry in get_cap_year_entries(manifest, selected_years):
        year_value = str(year_entry.get("year"))
        for subject in year_entry.get("subjects", []):
            if subject.get("slug") != subject_slug:
                continue
            if not _is_cap_subject_verified(year_value, subject):
                continue
            document = load_relative_json(subject.get("structured_path", ""))
            if document:
                documents.append(document)
    return documents


def flatten_cap_questions(documents: list[dict]) -> list[dict]:
    flattened = []
    display_number = 1
    for document in documents:
        year = str(document.get("year"))
        for question in document.get("questions", []):
            item = {
                **question,
                "year": year,
                "subject_slug": document.get("subject_slug"),
                "subject_label": document.get("subject_label"),
                "practice_ready": document.get("practice_ready", False),
                "source_question_number": question.get("number"),
                "display_number": display_number,
                "question_key": f"{year}:{question.get('number')}",
            }
            flattened.append(item)
            display_number += 1
    return flattened


def count_available_cap_questions(documents: list[dict]) -> int:
    return sum(len(document.get("questions", [])) for document in documents)


def summarize_guide_document(guide_document: dict, subject_slug: str | None = None) -> dict:
    reader_payload = build_guide_reader_payload(guide_document, subject_slug)
    return {
        "chapter_count": reader_payload["chapter_count"],
        "section_count": reader_payload["section_count"],
        "page_count": reader_payload["page_count"],
        "summary": reader_payload["summary"],
        "visual_section_count": reader_payload["visual_section_count"],
        "has_visual_fallback": reader_payload["has_visual_fallback"],
    }
