from __future__ import annotations

import re


BOOKLET_PATTERN = re.compile(r"(第[一二三四五六]冊)")
CURRICULUM_PREFIX_PATTERN = re.compile(r"^(?:\d+\s*課綱|[新舊]?\s*課綱)\s*[-－—_:：]?\s*")
SUBJECT_PREFIX_PATTERN = re.compile(r"^(國文|英語|英文|數學|社會|自然|地理|歷史|公民|生物|理化|地科)")


def normalize_spacing(text: str | None) -> str:
    return " ".join((text or "").replace("\u3000", " ").replace("\xa0", " ").split())


def strip_curriculum_prefix(text: str | None) -> str:
    cleaned = normalize_spacing(text)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = CURRICULUM_PREFIX_PATTERN.sub("", cleaned).strip()
    return cleaned


def clean_scope_label(text: str | None) -> str:
    cleaned = strip_curriculum_prefix(text)
    return cleaned.strip(" _-|｜：:")


def split_tag_parts(tags_value: str | None) -> list[str]:
    return [clean_scope_label(part) for part in str(tags_value or "").split("|") if clean_scope_label(part)]


def split_source_parts(source_unit: str | None) -> list[str]:
    return [clean_scope_label(part) for part in str(source_unit or "").split("_") if clean_scope_label(part)]


def extract_subject_and_booklet(raw_text: str | None) -> tuple[str, str, str]:
    cleaned = normalize_spacing(raw_text).strip(" _-|｜")
    if not cleaned:
        return "", "", ""

    subject_match = SUBJECT_PREFIX_PATTERN.match(cleaned)
    subject = subject_match.group(1) if subject_match else ""
    if subject:
        cleaned = cleaned[len(subject):].strip()

    booklet_match = BOOKLET_PATTERN.search(cleaned)
    if booklet_match:
        booklet = booklet_match.group(1)
        tail = clean_scope_label(cleaned[booklet_match.end():])
        return subject, booklet, tail

    return subject, "", clean_scope_label(cleaned)


def detect_booklet_label(*values: str | None) -> str:
    for value in values:
        match = BOOKLET_PATTERN.search(str(value or ""))
        if match:
            return match.group(1)
    return ""


def extract_question_hierarchy(
    category_value: str | None = "",
    tags_value: str | None = "",
    subject_label: str | None = "",
) -> dict[str, str]:
    category_parts = split_source_parts(category_value)
    tag_parts = split_tag_parts(tags_value)
    topic = tag_parts[0] if tag_parts else ""
    source_parts = split_source_parts(tag_parts[1] if len(tag_parts) > 1 else "")

    booklet = ""
    chapter = ""

    if category_parts:
        first_subject, first_booklet, first_tail = extract_subject_and_booklet(category_parts[0])
        booklet = first_booklet
        chapter_candidates = []
        if first_tail:
            chapter_candidates.append(first_tail)
        chapter_candidates.extend(category_parts[1:])
        if chapter_candidates:
            chapter = clean_scope_label(chapter_candidates[0])
        if not subject_label and first_subject:
            subject_label = first_subject

    if source_parts:
        first_subject, first_booklet, first_tail = extract_subject_and_booklet(source_parts[0])
        if first_booklet and not booklet:
            booklet = first_booklet
        source_chapter_candidates = []
        if first_tail:
            source_chapter_candidates.append(first_tail)
        source_chapter_candidates.extend(source_parts[1:])
        if source_chapter_candidates and not chapter:
            chapter = clean_scope_label(source_chapter_candidates[0])
        if len(source_chapter_candidates) > 1 and not topic:
            topic = clean_scope_label(source_chapter_candidates[1])
        if not subject_label and first_subject:
            subject_label = first_subject

    if not booklet:
        booklet = detect_booklet_label(category_value, tags_value, subject_label)

    chapter = clean_scope_label(chapter)
    topic = clean_scope_label(topic) or chapter

    if topic.startswith(chapter) and chapter and topic != chapter:
        topic = clean_scope_label(topic[len(chapter):]) or topic

    return {
        "subject": clean_scope_label(subject_label),
        "booklet": booklet,
        "chapter": chapter,
        "topic": topic,
    }


def build_category_label(booklet: str | None, chapter: str | None) -> str:
    booklet = clean_scope_label(booklet)
    chapter = clean_scope_label(chapter)
    if booklet and chapter:
        return f"{booklet}_{chapter}"[:100]
    return (chapter or booklet)[:100]


def build_tags_label(topic: str | None, booklet: str | None, chapter: str | None) -> str:
    topic = clean_scope_label(topic)
    booklet = clean_scope_label(booklet)
    chapter = clean_scope_label(chapter)
    source_parts = [part for part in [booklet, chapter, topic] if part]
    parts = []
    if topic:
        parts.append(topic)
    if source_parts:
        parts.append("_".join(source_parts))
    return " | ".join(parts)[:100]


def build_normalized_metadata(
    *,
    subject_label: str | None = "",
    volume: str | None = "",
    category: str | None = "",
    title: str | None = "",
    source_unit: str | None = "",
) -> dict[str, str]:
    raw_category = "_".join(part for part in [normalize_spacing(volume), normalize_spacing(category)] if part)
    raw_tags_parts = [normalize_spacing(title), normalize_spacing(source_unit)]
    raw_tags = " | ".join(part for part in raw_tags_parts if part)
    hierarchy = extract_question_hierarchy(raw_category, raw_tags, subject_label)

    return {
        "booklet": hierarchy["booklet"],
        "chapter": hierarchy["chapter"],
        "topic": hierarchy["topic"],
        "category": build_category_label(hierarchy["booklet"], hierarchy["chapter"]),
        "tags": build_tags_label(hierarchy["topic"], hierarchy["booklet"], hierarchy["chapter"]),
    }
