from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

from app.utils.document_ingest import extract_pdf_pages, save_extraction_docx


REPO_ROOT = Path(__file__).resolve().parent
DATA_ROOT = REPO_ROOT / "data"
MANIFEST_PATH = DATA_ROOT / "cap_review" / "cap_manifest.json"
PROJECT_PDF_ROOT = DATA_ROOT / "cap_practice_sources"
PROJECT_WORD_ROOT = DATA_ROOT / "cap_practice_word"
DESKTOP_PDF_ROOT = Path(r"C:\Users\Good PC\Desktop\國中題庫pdf\會考歷屆練習")
DESKTOP_WORD_ROOT = Path(r"C:\Users\Good PC\Desktop\國中題庫\會考歷屆練習")
AUDIT_PATH = DATA_ROOT / "cap_review" / "cap_material_audit.json"
DESKTOP_AUDIT_PATH = DESKTOP_PDF_ROOT / "會考歷屆檢查清單.txt"

CAP_ROOT = "https://cap.rcpet.edu.tw/examination.html"
YEAR_PAGE_TEMPLATE = "https://cap.rcpet.edu.tw/exam/{year}/{year}exam.html"
YEARS = [str(year) for year in range(102, 115)]

QUESTION_SUBJECTS = [
    {"labels": ["國文科"], "slug": "chinese", "label": "國文"},
    {"labels": ["英語科", "英語（閱讀）"], "slug": "english", "label": "英語"},
    {"labels": ["數學科"], "slug": "math", "label": "數學"},
    {"labels": ["社會科"], "slug": "social", "label": "社會"},
    {"labels": ["自然科"], "slug": "science", "label": "自然"},
]

SHARED_LABELS = {
    "參考答案": "answers",
    "試題說明": "explanation",
}


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            label = " ".join("".join(self._parts).split())
            self.links.append((self._href, label))
            self._href = None
            self._parts = []


@dataclass
class MaterialLink:
    label: str
    view_url: str

    @property
    def download_url(self) -> str:
        match = re.search(r"/d/([^/]+)/", self.view_url)
        if not match:
            return self.view_url
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    @property
    def file_id(self) -> str | None:
        match = re.search(r"/d/([^/]+)/", self.view_url)
        return match.group(1) if match else None


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def parse_links(html_text: str, base_url: str) -> list[tuple[str, str]]:
    parser = AnchorParser()
    parser.feed(html_text)
    return [(urljoin(base_url, href), label) for href, label in parser.links if href and label]


def download_file(session: requests.Session, material: MaterialLink, destination: Path) -> Path:
    ensure_dir(destination.parent)
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    response = session.get(material.download_url, timeout=240, stream=True)
    response.raise_for_status()

    content_type = (response.headers.get("content-type") or "").lower()
    if "text/html" in content_type:
        text = response.text
        confirm_match = re.search(r"confirm=([0-9A-Za-z_]+)", text)
        if confirm_match and material.file_id:
            response = session.get(
                "https://drive.google.com/uc",
                params={"export": "download", "id": material.file_id, "confirm": confirm_match.group(1)},
                timeout=240,
                stream=True,
            )
            response.raise_for_status()

    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    return destination


def sync_pdf_to_desktop(source: Path, destination: Path) -> Path:
    ensure_dir(destination.parent)
    if destination.exists() and destination.stat().st_size == source.stat().st_size:
        return destination
    shutil.copy2(source, destination)
    return destination


def render_docx_for_pdf(pdf_path: Path, output_path: Path, title: str, metadata: dict[str, str]) -> Path:
    ensure_dir(output_path.parent)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    pages = extract_pdf_pages(pdf_path, ocr_threshold=70)
    save_extraction_docx(output_path, title=title, pages=pages, metadata=metadata)
    return output_path


def collect_year_materials(session: requests.Session, year: str) -> dict[str, object]:
    page_url = YEAR_PAGE_TEMPLATE.format(year=year)
    links = parse_links(fetch_html(session, page_url), page_url)
    link_map = {label: url for url, label in links}
    issues: list[str] = []

    shared_dir = ensure_dir(PROJECT_PDF_ROOT / year / "shared")
    desktop_shared_dir = ensure_dir(DESKTOP_PDF_ROOT / year / "shared")
    word_shared_dir = ensure_dir(PROJECT_WORD_ROOT / year / "shared")
    desktop_word_shared_dir = ensure_dir(DESKTOP_WORD_ROOT / year / "shared")

    shared_materials = {}
    for label, slug in SHARED_LABELS.items():
        view_url = link_map.get(label)
        if not view_url:
            issues.append(f"missing_shared:{label}")
            continue
        material = MaterialLink(label, view_url)
        pdf_path = download_file(session, material, shared_dir / f"{year}_{slug}.pdf")
        desktop_pdf_path = sync_pdf_to_desktop(pdf_path, desktop_shared_dir / pdf_path.name)
        docx_path = render_docx_for_pdf(
            pdf_path,
            word_shared_dir / f"{year}_{slug}.docx",
            title=f"{year} 會考 {label}",
            metadata={"年份": year, "類型": label, "來源": page_url},
        )
        desktop_docx_path = sync_pdf_to_desktop(docx_path, desktop_word_shared_dir / docx_path.name)
        shared_materials[slug] = {
            "label": label,
            "url": material.view_url,
            "download_url": material.download_url,
            "local_path": str(pdf_path),
            "desktop_pdf_path": str(desktop_pdf_path),
            "word_path": str(docx_path),
            "desktop_word_path": str(desktop_docx_path),
        }

    subjects = []
    for meta in QUESTION_SUBJECTS:
        label = next((candidate for candidate in meta["labels"] if link_map.get(candidate)), None)
        view_url = link_map.get(label) if label else None
        if not view_url:
            issues.append(f"missing_subject:{meta['label']}")
            continue

        subject_dir = ensure_dir(PROJECT_PDF_ROOT / year / meta["slug"])
        desktop_subject_dir = ensure_dir(DESKTOP_PDF_ROOT / year / meta["slug"])
        word_subject_dir = ensure_dir(PROJECT_WORD_ROOT / year / meta["slug"])
        desktop_word_subject_dir = ensure_dir(DESKTOP_WORD_ROOT / year / meta["slug"])

        material = MaterialLink(label, view_url)
        pdf_path = download_file(session, material, subject_dir / f"{year}_{meta['slug']}.pdf")
        desktop_pdf_path = sync_pdf_to_desktop(pdf_path, desktop_subject_dir / pdf_path.name)
        docx_path = render_docx_for_pdf(
            pdf_path,
            word_subject_dir / f"{year}_{meta['slug']}.docx",
            title=f"{year} 會考 {meta['label']}",
            metadata={"年份": year, "科目": meta["label"], "來源": page_url},
        )
        desktop_docx_path = sync_pdf_to_desktop(docx_path, desktop_word_subject_dir / docx_path.name)

        subjects.append(
            {
                "slug": meta["slug"],
                "label": meta["label"],
                "question": {
                    "label": label,
                    "url": material.view_url,
                    "download_url": material.download_url,
                    "local_path": str(pdf_path),
                    "desktop_pdf_path": str(desktop_pdf_path),
                    "word_path": str(docx_path),
                    "desktop_word_path": str(desktop_docx_path),
                },
            }
        )

    return {
        "year": year,
        "source_url": page_url,
        "answer": shared_materials.get("answers", {}),
        "explanation": shared_materials.get("explanation", {}),
        "subjects": subjects,
        "issues": issues,
    }


def write_audit(manifest: dict) -> None:
    ensure_dir(AUDIT_PATH.parent)
    AUDIT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "會考歷屆題本下載與轉檔檢查清單",
        f"產生時間：{manifest['generated_at']}",
        "",
    ]
    for year_entry in manifest["years"]:
        lines.append(f"{year_entry['year']} 年")
        subject_slugs = [subject["slug"] for subject in year_entry.get("subjects", [])]
        lines.append(f"  科目：{', '.join(subject_slugs) if subject_slugs else '無'}")
        if year_entry.get("issues"):
            lines.append(f"  問題：{', '.join(year_entry['issues'])}")
        else:
            lines.append("  問題：無")
        lines.append("")

    ensure_dir(DESKTOP_AUDIT_PATH.parent)
    DESKTOP_AUDIT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dir(MANIFEST_PATH.parent)
    ensure_dir(PROJECT_PDF_ROOT)
    ensure_dir(PROJECT_WORD_ROOT)
    ensure_dir(DESKTOP_PDF_ROOT)
    ensure_dir(DESKTOP_WORD_ROOT)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Codex downloader"})

    years = []
    for year in YEARS:
        years.append(collect_year_materials(session, year))

    manifest = {
        "title": "會考歷屆練習來源",
        "source_url": CAP_ROOT,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "years": years,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_audit(manifest)
    print(f"saved manifest: {MANIFEST_PATH}")
    print(f"desktop pdf root: {DESKTOP_PDF_ROOT}")
    print(f"desktop word root: {DESKTOP_WORD_ROOT}")


if __name__ == "__main__":
    main()
