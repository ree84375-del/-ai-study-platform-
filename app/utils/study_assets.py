from __future__ import annotations

from pathlib import Path

from app.utils.document_ingest import load_json, normalize_whitespace


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
GUIDE_LIBRARY_MANIFEST_PATH = DATA_ROOT / "study_guides" / "guide_library_manifest.json"
CAP_LIBRARY_MANIFEST_PATH = DATA_ROOT / "cap_review" / "cap_practice_manifest.json"
GUIDE_STRUCTURED_ROOT = DATA_ROOT / "guide_structured" / "king_an"

GUIDE_SUBJECT_META = {
    "chinese": {
        "label": "國文",
        "icon": "fa-book-open",
        "description": "把閱讀、文意理解與主題筆記整理成可直接複習的講義入口。",
    },
    "english": {
        "label": "英文",
        "icon": "fa-language",
        "description": "用講義重整單字、文法、閱讀與重點句型，搭配題目複習更順。",
    },
    "math": {
        "label": "數學",
        "icon": "fa-calculator",
        "description": "把公式整理、題型拆解與解題策略收進同一個講義閱讀區。",
    },
    "nature": {
        "label": "自然",
        "icon": "fa-seedling",
        "description": "自然講義會依系列分成生物、理化與地科相關內容。",
    },
    "social": {
        "label": "社會",
        "icon": "fa-landmark-flag",
        "description": "社會講義依地理、歷史、公民系列分流，方便按主題複習。",
    },
}

CAP_SUBJECT_META = {
    "chinese": {
        "label": "國文",
        "icon": "fa-book-open",
        "description": "閱讀理解、語文運用與國學題組。",
    },
    "english": {
        "label": "英語",
        "icon": "fa-language",
        "description": "字彙、文法、閱讀與題組判讀。",
    },
    "math": {
        "label": "數學",
        "icon": "fa-calculator",
        "description": "觀念題、計算題與圖表題混合練習。",
    },
    "social": {
        "label": "社會",
        "icon": "fa-landmark",
        "description": "歷史、地理、公民整合的單科會考題。",
    },
    "science": {
        "label": "自然",
        "icon": "fa-flask",
        "description": "生物、理化、地科整合的單科會考題。",
    },
}

GUIDE_SUBJECT_ORDER = ["chinese", "english", "math", "nature", "social"]
CAP_SUBJECT_ORDER = ["chinese", "english", "math", "social", "science"]


def load_guide_library_manifest() -> dict:
    return load_json(GUIDE_LIBRARY_MANIFEST_PATH, default={"subjects": [], "issues": []})


def load_cap_library_manifest() -> dict:
    return load_json(CAP_LIBRARY_MANIFEST_PATH, default={"years": []})


def load_relative_json(relative_path: str) -> dict:
    if not relative_path:
        return {}
    return load_json(DATA_ROOT / relative_path, default={})


def _count_sections(chapters: list[dict]) -> int:
    return sum(len(chapter.get("sections", [])) for chapter in chapters)


def build_guide_library_catalog() -> list[dict]:
    catalog: list[dict] = []
    for subject_slug in GUIDE_SUBJECT_ORDER:
        meta = GUIDE_SUBJECT_META[subject_slug]
        subject_dir = GUIDE_STRUCTURED_ROOT / subject_slug
        series_entries = []

        if subject_dir.exists():
            for series_dir in sorted((item for item in subject_dir.iterdir() if item.is_dir()), key=lambda path: path.name):
                guide_entries = []
                for guide_path in sorted(series_dir.glob("*.json"), key=lambda path: path.name):
                    document = load_json(guide_path, default={})
                    if not document:
                        continue
                    chapters = document.get("chapters", [])
                    guide_entries.append(
                        {
                            "guide_value": guide_path.stem,
                            "title": document.get("title") or guide_path.stem,
                            "document_path": str(guide_path.relative_to(DATA_ROOT)),
                            "chapter_count": len(chapters),
                            "section_count": _count_sections(chapters),
                            "page_count": document.get("page_count", 0),
                            "summary": [
                                normalize_whitespace(line)
                                for line in (document.get("summary") or [])[:3]
                                if normalize_whitespace(line)
                            ],
                        }
                    )
                if guide_entries:
                    series_entries.append(
                        {
                            "series_value": series_dir.name,
                            "label": series_dir.name,
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
        for subject in year_entry.get("subjects", []):
            slug = subject.get("slug")
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
        for subject in year_entry.get("subjects", []):
            if subject.get("slug") != subject_slug:
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


def summarize_guide_document(guide_document: dict) -> dict:
    chapters = guide_document.get("chapters", [])
    return {
        "chapter_count": len(chapters),
        "section_count": _count_sections(chapters),
        "page_count": guide_document.get("page_count", 0),
        "summary": guide_document.get("summary", []),
    }
