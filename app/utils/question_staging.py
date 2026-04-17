
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data"
STAGING_DIR = DATA_ROOT / "question_staging"
CAP_REVIEW_DIR = DATA_ROOT / "cap_review"


def _safe_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _json_item_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("questions", "items", "records", "rows", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 1 if payload else 0
    return 0


def _status_counts(payload: Any) -> dict[str, int]:
    rows = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("questions", "items", "records", "rows", "results"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    counts = Counter()
    for item in rows:
        if isinstance(item, dict):
            counts[str(item.get("status") or item.get("review_status") or "needs_review")] += 1
    return dict(counts)


def _extract_issue_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ("issue_count", "issues", "missing", "failed", "failures", "problems"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return sum(v for v in value.values() if isinstance(v, int))
    total = 0
    for value in payload.values():
        if isinstance(value, list):
            total += len(value)
    return total


def _summarize_json_file(path: Path) -> dict[str, Any]:
    payload = _safe_json(path)
    return {
        "name": path.name,
        "modified": path.stat().st_mtime,
        "modified_label": path.stat().st_mtime,
        "size_kb": round(path.stat().st_size / 1024, 1),
        "item_count": _json_item_count(payload),
        "issue_count": _extract_issue_count(payload),
        "status_counts": _status_counts(payload),
        "readable": payload is not None,
    }


def build_question_staging_payload(formal_question_count: int = 0) -> dict[str, Any]:
    staging_files = []
    if STAGING_DIR.exists():
        staging_files = sorted(
            (_summarize_json_file(path) for path in STAGING_DIR.glob("*.json")),
            key=lambda item: item["modified"],
            reverse=True,
        )

    review_files = []
    if CAP_REVIEW_DIR.exists():
        review_files = sorted(
            (_summarize_json_file(path) for path in CAP_REVIEW_DIR.glob("*.json")),
            key=lambda item: item["modified"],
            reverse=True,
        )[:18]

    staged_question_count = sum(item["item_count"] for item in staging_files)
    pending_count = 0
    approved_count = 0
    rejected_count = 0
    for item in staging_files:
        counts = item.get("status_counts") or {}
        pending_count += counts.get("draft", 0) + counts.get("needs_review", 0) + counts.get("pending", 0)
        approved_count += counts.get("approved", 0)
        rejected_count += counts.get("rejected", 0)

    phase_status = [
        {"phase": "Phase 1", "title": "日式動畫設計語言", "status": "完成", "detail": "櫻花、和紙、朱印、御守、鳥居光影與低干擾動效已成為共用規格。"},
        {"phase": "Phase 2", "title": "共用 VFX 系統", "status": "完成", "detail": "CSS/JS 粒子、光環、浮動、reduced-motion fallback 已建立。"},
        {"phase": "Phase 3", "title": "成就獎盃模組", "status": "完成", "detail": "成就頁獎盃採 SSR 風格，使用局部 2.5D/PBR-like 光影，不全站獎盃化。"},
        {"phase": "Phase 4", "title": "首頁更新", "status": "完成", "detail": "首頁保留日式學習主城，使用氛圍動效與成就預覽。"},
        {"phase": "Phase 5", "title": "刷題頁更新", "status": "完成", "detail": "刷題入口維持副本分流，一般題庫仍鎖定整理中。"},
        {"phase": "Phase 6", "title": "弱點模考更新", "status": "完成", "detail": "弱點模考與錯題流程保留，結果與成就可使用新 VFX。"},
        {"phase": "Phase 7", "title": "成就頁大更新", "status": "完成", "detail": "成就頁是獎盃主舞台，加入稀有度與 SSR 展示櫃。"},
        {"phase": "Phase 8", "title": "題庫審核室", "status": "完成", "detail": "後台獨立審核室已建立，可查看 staging 與 audit 批次。"},
        {"phase": "Phase 9", "title": "題庫大更新安全閘", "status": "鎖定", "detail": "新題庫只進 staging；未經你說可以，不進前台 published 流程。"},
        {"phase": "Phase 10", "title": "測試與公告", "status": "待最後確認", "detail": "程式檢查通過後，才發布大更新公告。"},
    ]

    return {
        "stats": {
            "formal_question_count": formal_question_count,
            "staged_batch_count": len(staging_files),
            "staged_question_count": staged_question_count,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "audit_file_count": len(review_files),
        },
        "staging_files": staging_files,
        "review_files": review_files,
        "phase_status": phase_status,
        "front_gate": {
            "locked": True,
            "rule": "staging / needs_review / approved-but-unpublished 題目一律不進前台；只有你明確允許後才可發布。",
            "publish_state": "題庫大更新審核機制已就緒；新題庫尚未上架。",
        },
    }
