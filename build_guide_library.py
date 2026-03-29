from __future__ import annotations

import json
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
    hash_file,
    load_json,
    normalize_multiline_text,
    normalize_whitespace,
    save_extraction_docx,
    slugify,
    write_json,
)


SOURCE_MANIFEST = DATA_ROOT / "study_guides" / "king_an_manifest.json"
GUIDE_SOURCE_ROOT = DATA_ROOT / "guide_sources" / "king_an"
GUIDE_WORD_ROOT = DATA_ROOT / "guide_word" / "king_an"
GUIDE_STRUCTURED_ROOT = DATA_ROOT / "guide_structured" / "king_an"
GUIDE_LIBRARY_MANIFEST = DATA_ROOT / "study_guides" / "guide_library_manifest.json"

SELECTED_SERIES = {
    "chinese": {"雙向溝通複習講義", "新思維複習講義", "國文主題讚"},
    "english": {"雙向溝通複習講義", "新思維複習講義", "圖解735輕鬆讀複習講義"},
    "math": {"雙向溝通複習講義", "圖解735輕鬆讀複習講義"},
    "nature": {"生物－雙向溝通複習講義", "理化－雙向溝通複習講義", "理化－圖解735輕鬆讀複習講義", "地球科學－雙向溝通複習講義"},
    "social": {"歷史－雙向溝通複習講義", "地理－雙向溝通複習講義", "公民－雙向溝通複習講義", "公民－圖解735輕鬆讀複習講義"},
}
SERIES_DESCRIPTIONS = {
    "雙向溝通複習講義": "用解題策略、題型分析與重點整理來做整體複習。",
    "新思維複習講義": "把國文或英文閱讀重點改寫成較好吸收的複習節奏。",
    "國文主題讚": "把國文常見主題拆成可快速回頭看的主題筆記。",
    "圖解735輕鬆讀複習講義": "用圖解、分點與範例協助建立觀念與快速複習。",
    "歷史－雙向溝通複習講義": "用歷史主題整理與重點回顧來建立時代脈絡。",
    "地理－雙向溝通複習講義": "把地理重點整理成區域、現象與概念的複習講義。",
    "公民－雙向溝通複習講義": "整理公民制度、法律、經濟與生活議題的講義。",
    "公民－圖解735輕鬆讀複習講義": "用圖解方式整理公民主題與常考觀念。",
    "生物－雙向溝通複習講義": "整理生物的重要概念、系統與常見比較。",
    "理化－雙向溝通複習講義": "整理理化公式、現象、實驗與觀念題型。",
    "理化－圖解735輕鬆讀複習講義": "用圖解整理理化常考觀念與步驟。",
    "地球科學－雙向溝通複習講義": "整理地科現象、系統與圖表判讀重點。",
}
HEADING_PRIMARY_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百\d]+[章回單元篇節]"),
    re.compile(r"^[一二三四五六七八九十百]+[／/、.． ]"),
    re.compile(r"^(主題|單元|Lesson|Unit)\s*[A-Za-z0-9一二三四五六七八九十]"),
]
HEADING_SECONDARY_PATTERNS = [
    re.compile(r"^[（(][一二三四五六七八九十\d]+[)）]"),
    re.compile(r"^[一二三四五六七八九十\d]+、"),
    re.compile(r"^\d+[、.． ]"),
    re.compile(r"^(重點|觀念|技巧|策略|範例|解析|延伸)"),
]


def pick_selected_categories(subject_entry: dict) -> list[dict]:
    selected_prefixes = SELECTED_SERIES.get(subject_entry["slug"], set())
    categories = []
    for category in subject_entry.get("categories", []):
        label = normalize_whitespace(category.get("label", ""))
        if label in selected_prefixes:
            categories.append(category)
    return categories


def clean_guide_line(line: str) -> str:
    line = normalize_whitespace(line)
    if not line:
        return ""
    if re.fullmatch(r"\d+", line):
        return ""
    if "國教會考" in line and "第" in line and "題" in line:
        return ""
    return line


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[。！？!?])\s+|\n+", text)
    return [normalize_whitespace(chunk) for chunk in chunks if normalize_whitespace(chunk)]


def build_key_points(text: str, limit: int = 3) -> list[str]:
    points = []
    for sentence in split_sentences(text):
        if len(sentence) < 8:
            continue
        points.append(sentence)
        if len(points) >= limit:
            break
    return points


def is_primary_heading(line: str) -> bool:
    if len(line) > 34:
        return False
    if any(pattern.match(line) for pattern in HEADING_PRIMARY_PATTERNS):
        return True
    if "──" in line and len(line) <= 28:
        return True
    return False


def is_secondary_heading(line: str) -> bool:
    if len(line) > 38:
        return False
    return any(pattern.match(line) for pattern in HEADING_SECONDARY_PATTERNS)


def structure_guide(pages: list[dict]) -> list[dict]:
    chapters = []
    current_chapter = None
    current_section = None

    def ensure_chapter(title: str, page_number: int) -> dict:
        nonlocal current_chapter, current_section
        current_chapter = {
            "title": title,
            "page_start": page_number,
            "page_end": page_number,
            "sections": [],
        }
        chapters.append(current_chapter)
        current_section = None
        return current_chapter

    def ensure_section(title: str, page_number: int) -> dict:
        nonlocal current_section
        if current_chapter is None:
            ensure_chapter("主題整理", page_number)
        current_section = {
            "title": title,
            "page_start": page_number,
            "page_end": page_number,
            "content_lines": [],
        }
        current_chapter["sections"].append(current_section)
        return current_section

    for page in pages:
        page_number = page["page_number"]
        for raw_line in str(page.get("text") or "").splitlines():
            line = clean_guide_line(raw_line)
            if not line:
                continue

            if is_primary_heading(line):
                ensure_chapter(line, page_number)
                continue

            if is_secondary_heading(line):
                ensure_section(line, page_number)
                continue

            if current_chapter is None:
                ensure_chapter("主題整理", page_number)
            if current_section is None:
                ensure_section("核心內容", page_number)

            current_chapter["page_end"] = page_number
            current_section["page_end"] = page_number
            current_section["content_lines"].append(line)

    if not chapters:
        return []

    for chapter in chapters:
        if not chapter["sections"]:
            chapter["sections"].append(
                {
                    "title": "核心內容",
                    "page_start": chapter["page_start"],
                    "page_end": chapter["page_end"],
                    "content_lines": [],
                }
            )

        for section in chapter["sections"]:
            content = normalize_multiline_text("\n".join(section.pop("content_lines", [])))
            section["content"] = content
            section["summary_points"] = build_key_points(content)

    return [chapter for chapter in chapters if any(section.get("content") for section in chapter["sections"])]


def build_subject_reader_label(subject_slug: str) -> str:
    mapping = {
        "chinese": "國文",
        "english": "英文",
        "math": "數學",
        "nature": "自然",
        "social": "社會",
    }
    return mapping.get(subject_slug, subject_slug)


def select_items() -> tuple[list[dict], list[str]]:
    manifest = load_json(SOURCE_MANIFEST, default={"subjects": []})
    selected_subjects = []
    issues = []
    for subject in manifest.get("subjects", []):
        categories = pick_selected_categories(subject)
        requested = SELECTED_SERIES.get(subject["slug"], set())
        available_labels = {normalize_whitespace(category.get("label", "")) for category in categories}
        missing = sorted(requested - available_labels)
        for missing_label in missing:
            issues.append(f"{subject['label']} 缺少指定系列：{missing_label}")
        if categories:
            selected_subjects.append({**subject, "categories": categories})
    return selected_subjects, issues


def build_library() -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Codex guide builder"})
    selected_subjects, issues = select_items()
    seen_hashes = {}
    manifest_subjects = []
    duplicate_files = []

    for subject in selected_subjects:
        subject_slug = subject["slug"]
        subject_label = build_subject_reader_label(subject_slug)
        series_entries = []

        for category in subject["categories"]:
            series_label = normalize_whitespace(category["label"])
            series_slug = slugify(series_label)
            guide_entries = []

            for item in category.get("items", []):
                title = normalize_whitespace(item.get("title", ""))
                guide_slug = slugify(title)
                pdf_path = GUIDE_SOURCE_ROOT / subject_slug / series_slug / f"{guide_slug}.pdf"
                docx_path = GUIDE_WORD_ROOT / subject_slug / series_slug / f"{guide_slug}.docx"
                structured_path = GUIDE_STRUCTURED_ROOT / subject_slug / series_slug / f"{guide_slug}.json"

                download_to_path(item["download_url"], pdf_path, session=session)
                file_hash = hash_file(pdf_path)
                if file_hash in seen_hashes:
                    duplicate_files.append(
                        {
                            "duplicate_of": seen_hashes[file_hash],
                            "removed_file": str(pdf_path),
                            "title": title,
                        }
                    )
                    pdf_path.unlink(missing_ok=True)
                    continue
                seen_hashes[file_hash] = str(pdf_path)

                pages = extract_pdf_pages(pdf_path)
                save_extraction_docx(
                    docx_path,
                    title=title,
                    pages=pages,
                    metadata={
                        "科目": subject_label,
                        "講義系列": series_label,
                        "來源": item.get("download_url", ""),
                    },
                )
                chapters = structure_guide(pages)
                guide_payload = {
                    "subject_slug": subject_slug,
                    "subject_label": subject_label,
                    "series_slug": series_slug,
                    "series_label": series_label,
                    "title": title,
                    "guide_slug": guide_slug,
                    "download_url": item.get("download_url", ""),
                    "source_page_url": item.get("source_page_url", ""),
                    "files": {
                        "pdf": str(pdf_path.relative_to(DATA_ROOT)),
                        "docx": str(docx_path.relative_to(DATA_ROOT)),
                    },
                    "page_count": len(pages),
                    "ocr_pages": [page["page_number"] for page in pages if page["source"] != "direct"],
                    "chapters": chapters,
                    "summary": build_key_points("\n".join(section.get("content", "") for chapter in chapters for section in chapter["sections"]), limit=5),
                    "issues": [],
                }
                write_json(structured_path, guide_payload)

                guide_entries.append(
                    {
                        "title": title,
                        "guide_slug": guide_slug,
                        "structured_path": str(structured_path.relative_to(DATA_ROOT)),
                        "chapter_count": len(chapters),
                        "section_count": sum(len(chapter["sections"]) for chapter in chapters),
                        "page_count": len(pages),
                    }
                )

            series_entries.append(
                {
                    "label": series_label,
                    "slug": series_slug,
                    "description": SERIES_DESCRIPTIONS.get(series_label, "整理成章節與小節後的複習講義。"),
                    "guides": guide_entries,
                    "guide_count": len(guide_entries),
                }
            )

        manifest_subjects.append(
            {
                "slug": subject_slug,
                "label": subject_label,
                "series": [entry for entry in series_entries if entry["guides"]],
            }
        )

    payload = {
        "title": "AI 學習講義",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_manifest": str(SOURCE_MANIFEST.relative_to(DATA_ROOT)),
        "subjects": [subject for subject in manifest_subjects if subject["series"]],
        "issues": issues,
        "duplicate_files": duplicate_files,
    }
    write_json(GUIDE_LIBRARY_MANIFEST, payload)
    return payload


if __name__ == "__main__":
    result = build_library()
    print(f"subjects: {len(result['subjects'])}")
    print(f"issues: {len(result['issues'])}")
    print(f"duplicates: {len(result['duplicate_files'])}")
