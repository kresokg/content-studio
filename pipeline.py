#!/usr/bin/env python3
"""
Automated LinkedIn Content Pipeline

Pulls fresh topics from configured RSS/Atom feeds and local notes, deduplicates
them, and generates ready-to-edit LinkedIn post drafts in a dated markdown queue.
Zero external dependencies required (Python 3.10+ standard library).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import ai_client

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"

LINKEDIN_FOLD_LIMIT = 210
LINKEDIN_MAX_CHARS = 3000

POST_STYLES = [
    "tactical_breakdown",
    "contrarian_take",
    "builder_lesson",
    "quick_curated_insight",
]


@dataclass
class ContentItem:
    item_id: str
    source_type: str  # "feed" or "note"
    source_name: str
    title: str
    summary: str
    link: str
    published: str


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "post"


def make_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("processed_ids"), list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed_ids": []}


def save_state(path: Path, state: dict) -> None:
    state["processed_ids"] = state["processed_ids"][-1000:]
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def fetch_feed(name: str, url: str, timeout: int = 12) -> list[ContentItem]:
    items: list[ContentItem] = []
    req = urllib.request.Request(
        url, headers={"User-Agent": "LinkedInContentPipeline/1.0 (+https://local.pipeline)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
        print(f"[warn] Could not load feed '{name}' ({url}): {exc}", file=sys.stderr)
        return items

    rss_items = root.findall(".//item")
    if rss_items:
        raw_entries = [
            (
                elem.findtext("title") or "",
                (elem.findtext("link") or "").strip(),
                elem.findtext("description") or "",
                (elem.findtext("pubDate") or "").strip(),
            )
            for elem in rss_items
        ]
    else:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        atom_entries = root.findall(".//atom:entry", ns) or root.findall(".//entry")
        raw_entries = []
        for elem in atom_entries:
            link_el = elem.find("atom:link", ns) or elem.find("link")
            raw_entries.append(
                (
                    elem.findtext("atom:title", namespaces=ns) or elem.findtext("title") or "",
                    link_el.attrib.get("href", "").strip() if link_el is not None else "",
                    elem.findtext("atom:summary", namespaces=ns)
                    or elem.findtext("atom:content", namespaces=ns)
                    or elem.findtext("summary")
                    or "",
                    (
                        elem.findtext("atom:updated", namespaces=ns)
                        or elem.findtext("atom:published", namespaces=ns)
                        or ""
                    ).strip(),
                )
            )

    for raw_title, link, raw_desc, pub in raw_entries:
        title = strip_html(raw_title)
        if not title:
            continue
        items.append(
            ContentItem(
                item_id=make_id(f"feed:{link or title}"),
                source_type="feed",
                source_name=name,
                title=title,
                summary=strip_html(raw_desc)[:600],
                link=link,
                published=pub,
            )
        )
    return items


def load_notes(notes_dir: Path) -> list[ContentItem]:
    if not notes_dir.exists():
        return []
    items: list[ContentItem] = []
    for path in sorted(notes_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        first_line = re.sub(r"^#+\s*", "", lines[0])
        body = " ".join(lines[1:]) if len(lines) > 1 else first_line
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        items.append(
            ContentItem(
                item_id=make_id(f"note:{path.name}:{hashlib.md5(raw.encode()).hexdigest()}"),
                source_type="note",
                source_name=f"Note ({path.name})",
                title=first_line,
                summary=body[:800],
                link="",
                published=mtime,
            )
        )
    return items


def build_post_prompt(item: ContentItem, style: str, config: dict) -> str:
    hashtags = " ".join(config.get("default_hashtags", []))
    return f"""You are a LinkedIn ghostwriter for someone in: {config.get('niche')}.
Target audience: {config.get('audience')}.
Tone: {config.get('tone')}.
Post style: {style}.

Source ({item.source_name}):
Title: {item.title}
Context: {item.summary}
Link: {item.link or 'N/A'}

Write a single high-engagement LinkedIn post:
1. Start with a punchy 1-2 line hook (under 180 characters so it grabs attention before '...see more').
2. Use short paragraphs and scannable bullet points (no walls of text).
3. Add a genuine takeaway relevant to {config.get('niche')}.
4. End with one natural question to spark comments.
5. Finish with 3-4 relevant hashtags (you can draw from: {hashtags}).
6. Do NOT wrap in markdown code fences or add preamble. Output only the post text.
"""


def draft_locally(item: ContentItem, style: str, config: dict) -> str:
    hashtags = " ".join(config.get("default_hashtags", ["#Tech", "#CareerGrowth"])[:4])
    clean_summary = item.summary.strip() or item.title
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_summary) if len(s.strip()) > 20]
    bullets = sentences[:3] if sentences else [item.title]

    templates = {
        "contrarian_take": (
            f"Unpopular opinion on {item.title}:\n\nMost people overlook the part that actually matters.",
            "Here's what caught my attention:\n\n"
            + "\n".join(f"→ {b}" for b in bullets)
            + "\n\nMy takeaway:\nDon't just follow the hype—test how this changes your day-to-day workflow.",
            "Agree or disagree? How are you approaching this right now?",
        ),
        "builder_lesson": (
            f"A quick lesson worth sharing:\n\n{item.title}",
            "What stood out to me:\n\n"
            + "\n".join(f"• {b}" for b in bullets)
            + "\n\nWhy this matters if you're building in tech:\nSmall, consistent execution compounds way faster than waiting for the perfect setup.",
            "What's one small thing you shipped or learned this week?",
        ),
        "tactical_breakdown": (
            f"Worth bookmarking if you work in {config.get('niche', 'tech')}:\n\n{item.title}",
            "The short breakdown:\n\n"
            + "\n".join(f"{idx}. {b}" for idx, b in enumerate(bullets, start=1))
            + "\n\nActionable next step:\nPick one idea above and try it on a real project this week.",
            "Which of these points hits closest to home for you?",
        ),
    }
    hook, body, cta = templates.get(
        style,
        (
            f"Just came across this via {item.source_name}:\n\n{item.title}",
            "Key highlights:\n\n"
            + "\n".join(f"- {b}" for b in bullets)
            + "\n\n[Add 1–2 sentences with your personal perspective before posting]",
            "Have you seen this yet? Curious what your take is.",
        ),
    )
    return "\n\n".join([hook, body, cta, hashtags])


def render_draft_markdown(item: ContentItem, style: str, post_text: str, mode: str) -> str:
    hook_len = len(post_text.split("\n\n")[0])
    total_len = len(post_text)
    hook_status = (
        "OK (fits above '...see more')"
        if hook_len <= LINKEDIN_FOLD_LIMIT
        else "LONG (may clip before '...see more')"
    )
    source_line = f"[{item.source_name}]({item.link})" if item.link else item.source_name
    comment = f"Original source: {item.link}" if item.link else "Add a link to your repo, portfolio, or related resource here."
    return f"""# LinkedIn Draft: {item.title}

- **Source:** {source_line}
- **Platform:** `linkedin`
- **Style:** `{style}`
- **Generator:** `{mode}`
- **Hook Length:** {hook_len} chars — {hook_status}
- **Total Length:** {total_len} / {LINKEDIN_MAX_CHARS} chars
- **Status:** `[~] Ready to publish`

---

## Post Copy (Ready to Paste)

{post_text}

---

## Optional First Comment (Put Links Here for Better Reach)

{comment}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated LinkedIn Content Pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to config.json")
    parser.add_argument("--source", choices=["all", "feeds", "notes"], default="all", help="Which sources to pull")
    parser.add_argument("--limit", type=int, default=None, help="Max drafts to generate this run")
    parser.add_argument("--dry-run", action="store_true", help="Preview items without writing files or updating state")
    parser.add_argument("--reset-state", action="store_true", help="Clear deduplication history before running")
    args = parser.parse_args()

    config = load_config(args.config)
    state_path = BASE_DIR / config.get("state_file", ".pipeline_state.json")

    if args.reset_state and state_path.exists():
        state_path.unlink()
        print("[info] Cleared pipeline state.")

    state = load_state(state_path)
    seen = set(state["processed_ids"])

    candidates: list[ContentItem] = []
    if args.source in {"all", "notes"}:
        candidates.extend(load_notes(BASE_DIR / config.get("notes_dir", "notes")))
    if args.source in {"all", "feeds"}:
        for feed in config.get("feeds", []):
            candidates.extend(fetch_feed(feed["name"], feed["url"]))

    fresh_items = [item for item in candidates if item.item_id not in seen]
    max_items = args.limit if args.limit is not None else int(config.get("max_items_per_run", 5))
    selected = fresh_items[:max_items]

    if not selected:
        print("No new items to draft. Add a note to notes/ or run with --reset-state.")
        return 0

    if args.dry_run:
        print(f"[dry-run] Would generate {len(selected)} LinkedIn drafts:")
        for idx, item in enumerate(selected, start=1):
            print(f"  {idx}. [{item.source_name}] {item.title}")
        return 0

    today = dt.date.today().isoformat()
    out_dir = BASE_DIR / config.get("output_dir", "queue") / today
    out_dir.mkdir(parents=True, exist_ok=True)

    use_ai = ai_client.get_ai_settings(config).get("provider", "local_templates") != "local_templates"
    generated_files: list[tuple[ContentItem, Path, str]] = []

    for idx, item in enumerate(selected):
        style = POST_STYLES[idx % len(POST_STYLES)]
        post_text, mode = None, "local-template"

        if use_ai:
            try:
                post_text, mode = ai_client.generate_text(build_post_prompt(item, style, config), config, timeout=30)
            except Exception as exc:
                print(f"[warn] AI generation failed ({exc}), falling back to local template.", file=sys.stderr)

        if not post_text:
            post_text, mode = draft_locally(item, style, config), "local-template"

        draft_path = out_dir / f"{idx + 1:02d}-{slugify(item.title)}.md"
        draft_path.write_text(render_draft_markdown(item, style, post_text, mode), encoding="utf-8")
        state["processed_ids"].append(item.item_id)
        generated_files.append((item, draft_path, style))

    index_lines = [
        f"# LinkedIn Content Queue — {today}",
        "",
        f"Generated {len(generated_files)} draft(s) for **{config.get('niche')}**.",
        "",
        "| # | Source | Style | Draft |",
        "|---|---|---|---|",
        *[
            f"| {idx} | {item.source_name} | `{style}` | [{path.name}](./{path.name}) |"
            for idx, (item, path, style) in enumerate(generated_files, start=1)
        ],
    ]
    (out_dir / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    save_state(state_path, state)

    print(f"Generated {len(generated_files)} LinkedIn draft(s) in {out_dir}:")
    for _, path, style in generated_files:
        print(f"  - {path.name} ({style})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
