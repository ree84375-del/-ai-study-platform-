from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(r"C:\Users\Good PC\Desktop\國中題庫\會考歷屆試題")
MANIFEST_PATH = Path(__file__).resolve().parent / "data" / "cap_review" / "cap_manifest.json"
CAP_ROOT = "https://cap.rcpet.edu.tw/examination.html"
YEAR_PAGE_TEMPLATE = "https://cap.rcpet.edu.tw/exam/{year}/{year}exam.html"
YEARS = [str(year) for year in range(102, 115)]
SUBJECT_LINKS = {
    "國文科": {"slug": "chinese", "label": "國文"},
    "英語（閱讀）": {"slug": "english", "label": "英語"},
    "數學科": {"slug": "math", "label": "數學"},
    "社會科": {"slug": "social", "label": "社會"},
    "自然科": {"slug": "science", "label": "自然"},
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


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def parse_links(html_text: str, base_url: str) -> list[tuple[str, str]]:
    parser = AnchorParser()
    parser.feed(html_text)
    return [(urljoin(base_url, href), label) for href, label in parser.links if href and label]


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]', "-", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned or "download"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_file(session: requests.Session, material: MaterialLink, destination: Path) -> None:
    if destination.exists():
        return

    response = session.get(material.download_url, timeout=120, stream=True)
    response.raise_for_status()

    if "text/html" in (response.headers.get("content-type") or "").lower():
        text = response.text
        confirm_match = re.search(r"confirm=([0-9A-Za-z_]+)", text)
        id_match = re.search(r"/d/([^/]+)/", material.view_url)
        if confirm_match and id_match:
            response = session.get(
                "https://drive.google.com/uc",
                params={"export": "download", "id": id_match.group(1), "confirm": confirm_match.group(1)},
                timeout=120,
                stream=True,
            )
            response.raise_for_status()

    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)


def collect_year_materials(session: requests.Session, year: str) -> dict[str, object]:
    page_url = YEAR_PAGE_TEMPLATE.format(year=year)
    links = parse_links(fetch_html(session, page_url), page_url)
    link_map = {label: url for url, label in links}
    issues: list[str] = []

    shared_dir = ROOT / "原始PDF" / year / "共用"
    ensure_dir(shared_dir)

    answer = MaterialLink("參考答案", link_map["參考答案"]) if "參考答案" in link_map else None
    explanation = MaterialLink("試題說明", link_map["試題說明"]) if "試題說明" in link_map else None
    analysis_folder = {"label": "官方分析資料夾", "url": link_map.get(f"{year}年國中教育會考各科試題分析", "")}

    if answer:
        download_file(session, answer, shared_dir / f"{year}_參考答案.pdf")
    else:
        issues.append("missing_answer")

    if explanation:
        download_file(session, explanation, shared_dir / f"{year}_試題說明.pdf")
    else:
        issues.append("missing_explanation")

    subjects = []
    for label, meta in SUBJECT_LINKS.items():
        view_url = link_map.get(label)
        if not view_url:
            issues.append(f"missing_subject:{label}")
            continue

        subject_dir = ROOT / "原始PDF" / year / meta["label"]
        ensure_dir(subject_dir)
        material = MaterialLink(label, view_url)
        local_path = subject_dir / f"{year}_{meta['label']}_試題.pdf"
        download_file(session, material, local_path)
        subjects.append(
            {
                "slug": meta["slug"],
                "label": meta["label"],
                "question": {
                    "label": label,
                    "url": material.view_url,
                    "download_url": material.download_url,
                    "local_path": str(local_path),
                },
                "notes": "原始官方題本已另存到會考歷屆試題資料夾，網站保留官方來源連結。",
            }
        )

    return {
        "year": year,
        "source_url": page_url,
        "answer": {
            "label": answer.label if answer else "",
            "url": answer.view_url if answer else "",
            "download_url": answer.download_url if answer else "",
            "local_path": str(shared_dir / f"{year}_參考答案.pdf") if answer else "",
        },
        "explanation": {
            "label": explanation.label if explanation else "",
            "url": explanation.view_url if explanation else "",
            "download_url": explanation.download_url if explanation else "",
            "local_path": str(shared_dir / f"{year}_試題說明.pdf") if explanation else "",
        },
        "analysis_folder": analysis_folder,
        "subjects": subjects,
        "issues": issues,
    }


def main() -> None:
    ensure_dir(ROOT)
    ensure_dir(MANIFEST_PATH.parent)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Codex downloader"})

    years = []
    for year in reversed(YEARS):
        years.append(collect_year_materials(session, year))

    manifest = {
        "title": "會考歷屆練習",
        "source_url": CAP_ROOT,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "years": years,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved manifest: {MANIFEST_PATH}")
    print(f"years: {len(years)}")


if __name__ == "__main__":
    main()
