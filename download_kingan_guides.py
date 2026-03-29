from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(r"C:\Users\Good PC\Desktop\國中題庫\講義素材\金安")
MANIFEST_PATH = Path(__file__).resolve().parent / "data" / "study_guides" / "king_an_manifest.json"
SERVICE_ROOT = "https://www.king-an.com.tw/jh-school/service"
SUBJECT_SOURCES = [
    {
        "slug": "chinese",
        "label": "國文",
        "icon": "fa-book-open",
        "description": "國文複習講義與歷屆補充教材。",
        "url": "https://www.king-an.com.tw/jh-school/service/category/7-chinese",
    },
    {
        "slug": "english",
        "label": "英文",
        "icon": "fa-language",
        "description": "英文複習講義、歷屆題組翻譯與補充講義。",
        "url": "https://www.king-an.com.tw/jh-school/service/category/13-english",
    },
    {
        "slug": "math",
        "label": "數學",
        "icon": "fa-calculator",
        "description": "數學複習講義與歷屆學用教材。",
        "url": "https://www.king-an.com.tw/jh-school/service/category/14-math",
    },
    {
        "slug": "nature",
        "label": "自然",
        "icon": "fa-seedling",
        "description": "自然科複習講義，含生物、理化與地球科學教材。",
        "url": "https://www.king-an.com.tw/jh-school/service/category/30-natural",
    },
    {
        "slug": "social",
        "label": "社會",
        "icon": "fa-landmark",
        "description": "社會科複習講義，含歷史、地理、公民補充教材。",
        "url": "https://www.king-an.com.tw/jh-school/service/category/46-social",
    },
]


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


@dataclass(frozen=True)
class DownloadItem:
    title: str
    download_url: str
    source_page_url: str
    local_path: str


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def parse_links(html_text: str, base_url: str) -> list[tuple[str, str]]:
    parser = AnchorParser()
    parser.feed(html_text)
    return [(urljoin(base_url, href), label) for href, label in parser.links if href]


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]', "-", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned or "download"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_file(session: requests.Session, url: str, destination: Path) -> None:
    if destination.exists():
        return
    response = session.get(url, timeout=120, stream=True)
    response.raise_for_status()
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)


def crawl_subject(session: requests.Session, subject: dict[str, str]) -> dict[str, object]:
    ensure_dir(ROOT / subject["label"])
    visited_pages: set[str] = set()
    seen_downloads: set[str] = set()
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(subject["url"], tuple())])
    collected: list[tuple[tuple[str, ...], DownloadItem]] = []

    while queue:
        page_url, category_path = queue.popleft()
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        links = parse_links(fetch_html(session, page_url), page_url)
        category_links: list[tuple[str, str]] = []
        download_links: dict[str, str] = {}

        for href, label in links:
            normalized_label = label.strip()
            if not normalized_label:
                continue
            if "?download=" in href:
                if normalized_label != "下載":
                    download_links[href] = normalized_label
                elif href not in download_links:
                    download_links[href] = ""
                continue
            if "/jh-school/service/category/" in href and href != page_url and normalized_label != subject["label"]:
                category_links.append((href, normalized_label))

        for href, label in category_links:
            if href not in visited_pages:
                next_path = category_path + (label,)
                queue.append((href, next_path))

        for href, label in download_links.items():
            if href in seen_downloads:
                continue
            seen_downloads.add(href)
            title = label or href.split(":")[-1]
            local_dir = ROOT / subject["label"]
            for segment in category_path:
                local_dir /= sanitize_filename(segment)
            ensure_dir(local_dir)
            filename = sanitize_filename(title if title.lower().endswith(".pdf") else f"{title}.pdf")
            destination = local_dir / filename
            download_file(session, href, destination)
            collected.append(
                (
                    category_path,
                    DownloadItem(
                        title=title.removesuffix(".pdf"),
                        download_url=href,
                        source_page_url=page_url,
                        local_path=str(destination),
                    ),
                )
            )

    grouped: dict[tuple[str, ...], list[DownloadItem]] = defaultdict(list)
    for category_path, item in collected:
        grouped[category_path].append(item)

    categories = []
    for category_path, items in sorted(grouped.items(), key=lambda entry: (entry[0], len(entry[1]))):
        label = " / ".join(category_path) if category_path else "主題整理"
        description = f"收錄 {label} 的講義與下載教材。" if category_path else f"收錄 {subject['label']} 的主題教材。"
        categories.append(
            {
                "label": label,
                "description": description,
                "items": [
                    {
                        "title": item.title,
                        "download_url": item.download_url,
                        "source_page_url": item.source_page_url,
                        "local_path": item.local_path,
                    }
                    for item in sorted(items, key=lambda value: value.title)
                ],
            }
        )

    return {
        "slug": subject["slug"],
        "label": subject["label"],
        "icon": subject["icon"],
        "description": subject["description"],
        "source_url": subject["url"],
        "download_count": len(collected),
        "categories": categories,
    }


def main() -> None:
    ensure_dir(ROOT)
    ensure_dir(MANIFEST_PATH.parent)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Codex downloader"})

    subjects = [crawl_subject(session, subject) for subject in SUBJECT_SOURCES]

    manifest = {
        "title": "AI 學習講義",
        "source_url": SERVICE_ROOT,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subjects": subjects,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved manifest: {MANIFEST_PATH}")
    print(f"subjects: {len(subjects)}")


if __name__ == "__main__":
    main()
