#!/usr/bin/env python3
"""
Feed Inbox & Full-Article Reader Extractor for Content Studio.

Fetches RSS/Atom entries into a curated Discover inbox without cluttering the
draft queue, tracks skipped/sent items, and extracts clean readable article text
from external URLs using only the Python standard library.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pipeline

BASE_DIR = Path(__file__).resolve().parent
INBOX_STATE_PATH = BASE_DIR / ".inbox_state.json"
INBOX_CACHE_PATH = BASE_DIR / ".inbox_cache.json"

MAX_ARTICLE_CHARS = 16000

NOISE_TAG_RE = re.compile(
    r"<(script|style|noscript|svg|nav|footer|header|aside)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|div|section|article|main|br|li|tr|h[1-6]|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, type(default)):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_inbox_state() -> dict[str, list[str]]:
    data = _read_json(INBOX_STATE_PATH, {})
    return {
        "dismissed_ids": list(data.get("dismissed_ids") or [])[-1000:],
        "sent_ids": list(data.get("sent_ids") or [])[-1000:],
    }


def save_inbox_state(state: dict[str, list[str]]) -> None:
    _write_json(
        INBOX_STATE_PATH,
        {
            "dismissed_ids": list(dict.fromkeys(state.get("dismissed_ids") or []))[-1000:],
            "sent_ids": list(dict.fromkeys(state.get("sent_ids") or []))[-1000:],
        },
    )


def dismiss_item(item_id: str) -> None:
    if not item_id:
        return
    state = load_inbox_state()
    if item_id not in state["dismissed_ids"]:
        state["dismissed_ids"].append(item_id)
    save_inbox_state(state)
    if cached := load_cached_items():
        save_cached_items([it for it in cached if it.get("id") != item_id])


def mark_sent(item_id: str) -> None:
    if not item_id:
        return
    state = load_inbox_state()
    if item_id not in state["sent_ids"]:
        state["sent_ids"].append(item_id)
    save_inbox_state(state)
    if cached := load_cached_items():
        for it in cached:
            if it.get("id") == item_id:
                it["already_sent"] = True
        save_cached_items(cached)


def reset_dismissed() -> None:
    state = load_inbox_state()
    state["dismissed_ids"] = []
    save_inbox_state(state)


def load_cached_items() -> list[dict[str, Any]]:
    return _read_json(INBOX_CACHE_PATH, [])


def save_cached_items(items: list[dict[str, Any]]) -> None:
    _write_json(INBOX_CACHE_PATH, items)


def fetch_inbox_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch fresh RSS/Atom items, filtering out dismissed items and caching locally."""
    state = load_inbox_state()
    dismissed, sent = set(state["dismissed_ids"]), set(state["sent_ids"])

    raw_items: list[pipeline.ContentItem] = []
    for feed in config.get("feeds", []):
        name, url = str(feed.get("name") or "").strip(), str(feed.get("url") or "").strip()
        if name and url:
            raw_items.extend(pipeline.fetch_feed(name, url))

    seen_ids: set[str] = set()
    items: list[dict[str, Any]] = []
    for it in raw_items:
        if it.item_id in dismissed or it.item_id in seen_ids:
            continue
        seen_ids.add(it.item_id)
        items.append(
            {
                "id": it.item_id,
                "source_name": it.source_name,
                "title": it.title,
                "summary": it.summary,
                "link": it.link,
                "published": it.published,
                "already_sent": it.item_id in sent,
            }
        )

    save_cached_items(items)
    return items


def _strip_tags_clean(fragment: str) -> str:
    text = html.unescape( re.sub(r"<[^>]+>", " ", BLOCK_BREAK_RE.sub("\n", fragment)) )
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.splitlines()]
    cleaned_lines: list[str] = []
    for ln in lines:
        if ln or (cleaned_lines and cleaned_lines[-1] != ""):
            cleaned_lines.append(ln)
    return "\n".join(cleaned_lines).strip()


def extract_readable_text(raw_html: str, fallback_title: str = "") -> dict[str, Any]:
    """Extract clean article title and readable text from an HTML document."""
    og_m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    )
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, re.IGNORECASE | re.DOTALL)

    if og_m:
        extracted_title = html.unescape(og_m.group(1)).strip()
    elif match := (title_m or h1_m):
        extracted_title = pipeline.strip_html(match.group(1))
    else:
        extracted_title = ""

    title = extracted_title or fallback_title or "Untitled Article"
    cleaned_html = NOISE_TAG_RE.sub(" ", COMMENT_RE.sub(" ", raw_html))

    candidate_text = ""
    for tag in ("article", "main"):
        matches = re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", cleaned_html, re.IGNORECASE | re.DOTALL)
        if matches:
            joined = "\n\n".join(_strip_tags_clean(m) for m in matches).strip()
            if len(joined) >= 250:
                candidate_text = joined
                break

    if not candidate_text:
        body_m = re.search(r"<body\b[^>]*>(.*?)</body>", cleaned_html, re.IGNORECASE | re.DOTALL)
        candidate_text = _strip_tags_clean(body_m.group(1) if body_m else cleaned_html)

    truncated = len(candidate_text) > MAX_ARTICLE_CHARS
    if truncated:
        candidate_text = candidate_text[:MAX_ARTICLE_CHARS].rstrip() + "..."

    return {
        "title": title,
        "full_text": candidate_text,
        "word_count": len(candidate_text.split()) if candidate_text else 0,
        "truncated": truncated,
    }


def fetch_and_extract_url(url: str, timeout: int = 12) -> dict[str, Any]:
    """Fetch a web URL and extract readable full-article text."""
    clean_url = (url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please provide a valid http:// or https:// URL.")

    req = urllib.request.Request(
        clean_url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LinkedInContentStudio/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            raw_bytes = resp.read(1_500_000)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not load URL: {exc}") from exc

    decoded = raw_bytes.decode("utf-8", errors="replace")
    source_name = parsed.netloc.removeprefix("www.")

    if "text/plain" in content_type:
        text = decoded[:MAX_ARTICLE_CHARS].strip()
        return {
            "url": clean_url,
            "source_name": source_name,
            "title": clean_url,
            "full_text": text,
            "word_count": len(text.split()),
            "truncated": len(decoded) > MAX_ARTICLE_CHARS,
        }

    return {
        "url": clean_url,
        "source_name": source_name,
        **extract_readable_text(decoded, fallback_title=clean_url),
    }
