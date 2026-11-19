#!/usr/bin/env python3
"""
Local Web Studio for the Automated LinkedIn Content Pipeline.

Zero-dependency Python standard library web server providing a REST API
and static frontend for curating feeds, editing multi-platform drafts,
managing a Kanban status board, capturing notes, and running AI prompts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import ai_client
import discover
import pipeline

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CONFIG_PATH = BASE_DIR / "config.json"

VALID_STATUSES = ("draft", "ready", "scheduled", "published", "archived")
VALID_PLATFORMS = ("linkedin", "x", "threads")

STATUS_TO_LABEL = {
    "draft": "[ ] Draft",
    "ready": "[~] Ready to publish",
    "scheduled": "[@] Scheduled",
    "published": "[x] Published",
    "archived": "[-] Archived",
}

DEFAULT_PROFILE = {
    "name": "Your Name",
    "handle": "yourhandle",
    "headline": "Software Engineer · AI Builder",
}

DEFAULT_PROMPT_TEMPLATES = [
    {
        "id": "tpl-takeaways",
        "name": "3 Practical Takeaways",
        "prompt": "Rewrite this with a punchy opening hook, 3 concise bulleted takeaways, and one discussion question at the end.",
    },
    {
        "id": "tpl-hook",
        "name": "Sharpen Hook",
        "prompt": "Keep the core ideas, but rewrite the opening 2 lines into a scroll-stopping hook.",
    },
    {
        "id": "tpl-story",
        "name": "Builder Story",
        "prompt": "Reframe this as a first-person story highlighting the real problem, what changed, and the practical lesson.",
    },
    {
        "id": "tpl-concise",
        "name": "Make Concise",
        "prompt": "Tighten the post by ~35% for crisp mobile reading while keeping the key insight.",
    },
]

DEFAULT_VOICE_PROFILES = [
    {
        "id": "voice-direct",
        "name": "Direct Engineer",
        "instructions": "Clear, pragmatic software engineer voice. Grounded, concrete, short sentences, zero corporate fluff.",
    },
    {
        "id": "voice-conversational",
        "name": "Conversational Builder",
        "instructions": "Warm, approachable peer-to-peer builder tone. Curious, honest, and easy to read.",
    },
    {
        "id": "voice-sharp",
        "name": "Sharp & Opinionated",
        "instructions": "Confident, concise, thoughtful contrarian angle backed by practical experience—never clickbait.",
    },
]

PLATFORM_GUIDELINES = {
    "linkedin": (
        "LinkedIn post: max 3000 chars. Start with a scroll-stopping 1-2 line hook under 180 chars "
        "(before '...see more'), use crisp short paragraphs or clean bullets, and end with one natural question."
    ),
    "x": (
        "X (Twitter) post: keep a single post under 280 chars; OR if the topic needs depth, format as a "
        "tight numbered thread (1/, 2/, 3/...) where each post is under 270 chars separated by blank lines."
    ),
    "threads": (
        "Threads post: conversational, natural peer-to-peer tone, strictly under 500 chars total."
    ),
}

BODY_SECTION_RE = re.compile(
    r"## Post Copy \(Ready to Paste\)\s*\n(.*?)\n---\s*\n## Optional First Comment[^\n]*\n(.*)$",
    re.DOTALL,
)

STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


def safe_subpath(root: Path, rel: str) -> Path:
    """Resolve `rel` under `root` and reject empty, absolute, or traversal paths."""
    if not rel or not isinstance(rel, str):
        raise ValueError("Missing relative path.")
    rel_path = Path(rel)
    if rel_path.is_absolute():
        raise ValueError("Absolute paths are not allowed.")
    root_resolved = root.resolve()
    target = (root_resolved / rel_path).resolve()
    if target == root_resolved or not target.is_relative_to(root_resolved):
        raise ValueError("Path escapes target directory.")
    return target


def normalize_scheduled_for(raw: Any) -> str:
    """Validate and normalize a local schedule timestamp as YYYY-MM-DDTHH:MM."""
    val = str(raw or "").strip().replace(" ", "T")
    if not val:
        return ""
    try:
        dt.datetime.strptime(val, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("scheduled_for must be formatted as YYYY-MM-DDTHH:MM.") from exc
    return val


def parse_status(raw: str) -> str:
    """Map status checkbox/text from markdown into normalized status key."""
    norm = (raw or "").strip().lower()
    for token, key in (
        ("[x]", "published"),
        ("published", "published"),
        ("[-]", "archived"),
        ("archived", "archived"),
        ("[@]", "scheduled"),
        ("scheduled", "scheduled"),
        ("[~]", "ready"),
    ):
        if token in norm:
            return key
    return "draft"


def _meta(header: str, field: str, default: str = "") -> str:
    m = re.search(rf"^-\s*\*\*{re.escape(field)}:\*\*\s*`?([^`\n]+)`?", header, re.MULTILINE)
    return m.group(1).strip() if m else default


def parse_draft_markdown(
    text: str, rel_id: str, date_str: str, filename: str
) -> dict[str, Any]:
    """Parse a pipeline markdown draft file into structured fields."""
    match = BODY_SECTION_RE.search(text)
    if match:
        header = text[: match.start()]
        post_copy = match.group(1).strip("\r\n")
        first_comment = match.group(2).strip("\r\n")
    else:
        header, post_copy, first_comment = "", text.strip("\r\n"), ""

    title_m = re.search(r"^#\s*(?:LinkedIn Draft:\s*)?(.+)$", header or text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else filename

    raw_source = _meta(header, "Source", "Manual Draft")
    link_m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", raw_source)
    source_name = link_m.group(1).strip() if link_m else raw_source
    source_link = link_m.group(2).strip() if link_m else ""

    platform = _meta(header, "Platform", "linkedin").lower()
    if platform not in VALID_PLATFORMS:
        platform = "linkedin"

    try:
        scheduled_for = normalize_scheduled_for(_meta(header, "Scheduled", ""))
    except ValueError:
        scheduled_for = ""

    first_chunk = post_copy.split("\n\n")[0] if post_copy else ""
    return {
        "id": rel_id,
        "date": date_str,
        "filename": filename,
        "title": title,
        "source_name": source_name,
        "source_link": source_link,
        "platform": platform,
        "style": _meta(header, "Style", "custom"),
        "generator": _meta(header, "Generator", "studio"),
        "status": parse_status(_meta(header, "Status", "")),
        "scheduled_for": scheduled_for,
        "post_copy": post_copy,
        "first_comment": first_comment,
        "hook_length": len(first_chunk),
        "total_length": len(post_copy),
    }


def serialize_draft_markdown(draft: dict[str, Any]) -> str:
    """Serialize structured draft fields back to pipeline markdown format."""
    title = (draft.get("title") or "Untitled Draft").strip()
    source_name = (draft.get("source_name") or "Manual Draft").strip()
    source_link = (draft.get("source_link") or "").strip()
    source_md = f"[{source_name}]({source_link})" if source_link else source_name

    platform = str(draft.get("platform") or "linkedin").strip().lower()
    if platform not in VALID_PLATFORMS:
        platform = "linkedin"
    style = (draft.get("style") or "custom").strip()
    generator = (draft.get("generator") or "studio").strip()
    status_key = draft.get("status", "draft")
    status_label = STATUS_TO_LABEL.get(status_key, STATUS_TO_LABEL["draft"])

    scheduled_for = normalize_scheduled_for(draft.get("scheduled_for", ""))
    scheduled_line = f"\n- **Scheduled:** `{scheduled_for}`" if scheduled_for else ""

    post_copy = (draft.get("post_copy") or "").strip("\r\n")
    first_comment = (draft.get("first_comment") or "").strip("\r\n")
    hook_len = len(post_copy.split("\n\n")[0]) if post_copy else 0
    hook_status = (
        "OK (fits above '...see more')"
        if hook_len <= pipeline.LINKEDIN_FOLD_LIMIT
        else "LONG (may clip before '...see more')"
    )

    return f"""# LinkedIn Draft: {title}

- **Source:** {source_md}
- **Platform:** `{platform}`
- **Style:** `{style}`
- **Generator:** `{generator}`
- **Hook Length:** {hook_len} chars — {hook_status}
- **Total Length:** {len(post_copy)} / {pipeline.LINKEDIN_MAX_CHARS} chars
- **Status:** `{status_label}`{scheduled_line}

---

## Post Copy (Ready to Paste)

{post_copy}

---

## Optional First Comment (Put Links Here for Better Reach)

{first_comment}
"""


def _normalize_profile(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return dict(DEFAULT_PROFILE)
    handle = str(raw.get("handle") or DEFAULT_PROFILE["handle"]).strip().lstrip("@")
    return {
        "name": str(raw.get("name") or DEFAULT_PROFILE["name"]).strip() or DEFAULT_PROFILE["name"],
        "handle": handle or DEFAULT_PROFILE["handle"],
        "headline": str(raw.get("headline") or DEFAULT_PROFILE["headline"]).strip(),
    }


def _write_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["profile"] = _normalize_profile(cfg.get("profile"))

    if not isinstance(cfg.get("prompt_templates"), list) or not cfg["prompt_templates"]:
        cfg["prompt_templates"] = [dict(t) for t in DEFAULT_PROMPT_TEMPLATES]
    if not isinstance(cfg.get("voice_profiles"), list) or not cfg["voice_profiles"]:
        cfg["voice_profiles"] = [dict(v) for v in DEFAULT_VOICE_PROFILES]

    voice_ids = {v.get("id") for v in cfg["voice_profiles"] if isinstance(v, dict)}
    if cfg.get("active_voice_id") not in voice_ids:
        cfg["active_voice_id"] = cfg["voice_profiles"][0]["id"]
    return cfg


def _clean_preset_list(
    raw: Any, text_key: str, prefix: str, label: str, require_nonempty: bool = False
) -> list[dict[str, str]]:
    if not isinstance(raw, list) or (require_nonempty and not raw):
        raise ValueError(f"Keep at least one {label}." if require_nonempty else f"{label}s must be a list.")
    cleaned = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Each {label} must be an object.")
        name = str(item.get("name") or "").strip()
        body = str(item.get(text_key) or "").strip()
        if not name or not body:
            raise ValueError(f"Each {label} needs a name and instructions.")
        pid = str(item.get("id") or f"{prefix}-{pipeline.slugify(name, 24)}-{idx}").strip()
        cleaned.append({"id": pid, "name": name, text_key: body})
    return cleaned


def save_studio_presets(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and save Studio AI prompt templates and voice/tone profiles."""
    existing = load_config()
    if "prompt_templates" in payload:
        existing["prompt_templates"] = _clean_preset_list(
            payload["prompt_templates"], "prompt", "tpl", "template"
        )
    if "voice_profiles" in payload:
        existing["voice_profiles"] = _clean_preset_list(
            payload["voice_profiles"], "instructions", "voice", "voice profile", require_nonempty=True
        )

    valid_ids = {v["id"] for v in existing["voice_profiles"]}
    requested_id = str(payload.get("active_voice_id") or "").strip()
    if requested_id in valid_ids:
        existing["active_voice_id"] = requested_id
    elif existing.get("active_voice_id") not in valid_ids:
        existing["active_voice_id"] = existing["voice_profiles"][0]["id"]

    _write_config(existing)
    return {
        "prompt_templates": existing["prompt_templates"],
        "voice_profiles": existing["voice_profiles"],
        "active_voice_id": existing["active_voice_id"],
    }


def save_config(updated: dict[str, Any]) -> dict[str, Any]:
    existing = load_config()
    if "feeds" in updated:
        feeds = updated["feeds"]
        if not isinstance(feeds, list):
            raise ValueError("feeds must be a list.")
        cleaned_feeds = []
        for feed in feeds:
            if not isinstance(feed, dict):
                raise ValueError("Each feed must be an object with name and url.")
            name, url = str(feed.get("name", "")).strip(), str(feed.get("url", "")).strip()
            if not name or not url:
                raise ValueError("Each feed requires both a name and a url.")
            cleaned_feeds.append({"name": name, "url": url})
        existing["feeds"] = cleaned_feeds

    if "profile" in updated:
        if not isinstance(updated["profile"], dict):
            raise ValueError("profile must be an object.")
        existing["profile"] = _normalize_profile(updated["profile"])

    _write_config(existing)
    return existing


def get_queue_dir(config: dict[str, Any]) -> Path:
    return BASE_DIR / config.get("output_dir", "queue")


def get_notes_dir(config: dict[str, Any]) -> Path:
    return BASE_DIR / config.get("notes_dir", "notes")


def list_all_drafts(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan queue directory for draft markdown files, sorted date desc, filename asc."""
    queue_dir = get_queue_dir(config)
    if not queue_dir.exists():
        return []

    drafts: list[dict[str, Any]] = []
    for path in queue_dir.rglob("*.md"):
        if not path.is_file() or path.name.upper() == "INDEX.MD":
            continue
        rel = path.relative_to(queue_dir).as_posix()
        date_str = path.parent.name if path.parent != queue_dir else ""
        try:
            drafts.append(parse_draft_markdown(path.read_text(encoding="utf-8"), rel, date_str, path.name))
        except OSError:
            continue

    drafts.sort(key=lambda d: d["filename"])
    drafts.sort(key=lambda d: d["date"], reverse=True)
    return drafts


def list_all_notes(config: dict[str, Any]) -> list[dict[str, Any]]:
    """List raw notes from notes directory sorted newest first."""
    notes_dir = get_notes_dir(config)
    if not notes_dir.exists():
        return []

    notes: list[tuple[float, dict[str, Any]]] = []
    for path in notes_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            raw, mtime = path.read_text(encoding="utf-8"), path.stat().st_mtime
        except OSError:
            continue
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        title = re.sub(r"^#+\s*", "", lines[0]) if lines else path.stem
        content = "\n".join(raw.splitlines()[1:]).strip() if len(raw.splitlines()) > 1 else ""
        notes.append(
            (
                mtime,
                {
                    "filename": path.name,
                    "title": title,
                    "content": content or raw.strip(),
                    "raw": raw,
                    "modified": dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                },
            )
        )
    notes.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in notes]


def create_new_draft(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new draft file under queue/<today>/ without colliding."""
    queue_dir = get_queue_dir(config)
    today = dt.date.today().isoformat()
    date_dir = queue_dir / today
    date_dir.mkdir(parents=True, exist_ok=True)

    title = (payload.get("title") or "New Post").strip()
    platform = str(payload.get("platform") or "linkedin").strip().lower()
    status = payload.get("status", "draft")

    existing_nums = [
        int(m.group(1))
        for p in date_dir.glob("*.md")
        if (m := re.match(r"^(\d+)-", p.name))
    ]
    next_num = max(existing_nums, default=0) + 1
    slug = pipeline.slugify(title)

    while (target := date_dir / f"{next_num:02d}-{slug}.md").exists():
        next_num += 1

    rendered = serialize_draft_markdown(
        {
            "title": title,
            "source_name": (payload.get("source_name") or "Studio Draft").strip(),
            "source_link": (payload.get("source_link") or "").strip(),
            "platform": platform if platform in VALID_PLATFORMS else "linkedin",
            "style": (payload.get("style") or "custom").strip(),
            "generator": (payload.get("generator") or "studio").strip(),
            "status": status if status in VALID_STATUSES else "draft",
            "scheduled_for": normalize_scheduled_for(payload.get("scheduled_for", "")),
            "post_copy": (payload.get("post_copy") or "").strip("\r\n"),
            "first_comment": (payload.get("first_comment") or "").strip("\r\n"),
        }
    )
    target.write_text(rendered, encoding="utf-8")
    return parse_draft_markdown(rendered, target.relative_to(queue_dir).as_posix(), today, target.name)


def run_pipeline_subprocess(
    source: str = "notes", limit: int = 5, timeout: int = 30
) -> dict[str, Any]:
    """Execute pipeline.py safely as a subprocess and return output + refreshed drafts."""
    proc = subprocess.run(
        [sys.executable, str(BASE_DIR / "pipeline.py"), "--source", source, "--limit", str(limit)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "drafts": list_all_drafts(load_config()),
    }


def trim_article_for_draft(text: str, max_chars: int = 2400) -> str:
    """Trim extracted article text cleanly on a paragraph or line boundary."""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    chunk = cleaned[:max_chars]
    split_pos = max(chunk.rfind("\n\n"), chunk.rfind("\n"))
    if split_pos > max_chars // 2:
        chunk = chunk[:split_pos]
    return chunk.rstrip() + "\n\n[Truncated from source article]"


def build_rewrite_prompt(body: dict[str, Any], config: dict[str, Any]) -> tuple[str, str]:
    """Construct system + user prompts incorporating active Voice & Tone and target platform."""
    platform = str(body.get("platform") or "linkedin").strip().lower()
    if platform not in VALID_PLATFORMS:
        platform = "linkedin"

    voices = config.get("voice_profiles") or DEFAULT_VOICE_PROFILES
    voice_id = str(body.get("voice_id") or config.get("active_voice_id") or "").strip()
    active_voice = next((v for v in voices if v.get("id") == voice_id), voices[0])

    title = str(body.get("title") or "").strip()
    post_copy = str(body.get("post_copy") or "").strip()
    custom_prompt = str(body.get("custom_prompt") or "").strip()

    if body.get("adapt_to_platform") and not custom_prompt:
        task_instruction = f"Adapt and rewrite this draft naturally for {platform.upper()}."
    else:
        task_instruction = (
            custom_prompt
            or "Polish and improve this post while keeping the main ideas clear and engaging."
        )

    system_prompt = (
        f"You are an editorial writing assistant.\n"
        f"Voice & Tone Profile ({active_voice.get('name', 'Custom')}): {active_voice.get('instructions', '')}\n"
        f"Target Platform Rules: {PLATFORM_GUIDELINES[platform]}\n"
        "Output ONLY the finished post text with no markdown code fences, explanations, or preamble."
    )
    user_prompt = (
        f"Instruction: {task_instruction}\n\n"
        f"Draft Title: {title or 'Untitled'}\n\n"
        f"Current Draft / Raw Source Text:\n{post_copy or title}\n\n"
        f"Output ONLY the revised {platform.upper()} post text."
    )
    return system_prompt, user_prompt


class StudioHandler(BaseHTTPRequestHandler):
    """HTTP request handler for static frontend assets and JSON REST API."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"[studio] {self.address_string()} - {format % args}\n")

    def send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, file_path: Path, content_type: str) -> None:
        if not file_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Asset not found."})
            return
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        if length > 2_000_000:
            raise ValueError("Request body too large.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON payload.") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def _delete_item(self, root: Path, rel: str, label: str) -> None:
        target = safe_subpath(root, rel)
        if not target.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": f"{label} not found."})
            return
        target.unlink()
        self.send_json(HTTPStatus.OK, {"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if static := STATIC_ROUTES.get(path):
            self.send_static(WEB_DIR / static[0], static[1])
            return

        try:
            config = load_config()
            if path == "/api/drafts":
                self.send_json(HTTPStatus.OK, {"drafts": list_all_drafts(config)})
            elif path == "/api/notes":
                self.send_json(HTTPStatus.OK, {"notes": list_all_notes(config)})
            elif path == "/api/config":
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "config": config,
                        "ai_state": ai_client.get_public_ai_state(config),
                        "prompt_templates": config.get("prompt_templates", []),
                        "voice_profiles": config.get("voice_profiles", []),
                        "active_voice_id": config.get("active_voice_id", ""),
                    },
                )
            elif path == "/api/discover":
                self.send_json(HTTPStatus.OK, {"items": discover.load_cached_items()})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown route."})
        except Exception as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self.read_json_body()
            config = load_config()

            if path == "/api/drafts/new":
                self.send_json(HTTPStatus.CREATED, {"draft": create_new_draft(config, body)})
            elif path == "/api/drafts/delete":
                self._delete_item(get_queue_dir(config), str(body.get("id") or ""), "Draft")
            elif path == "/api/notes/delete":
                self._delete_item(get_notes_dir(config), str(body.get("filename") or ""), "Note")
            elif path == "/api/notes":
                title = str(body.get("title") or "").strip()
                content = str(body.get("content") or "").strip()
                if not title and not content:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Provide a note title or content."})
                    return
                title = title or content.splitlines()[0][:60]
                notes_dir = get_notes_dir(config)
                notes_dir.mkdir(parents=True, exist_ok=True)
                base_slug = pipeline.slugify(title)
                candidate = notes_dir / f"{base_slug}.md"
                suffix = 2
                while candidate.exists():
                    candidate = notes_dir / f"{base_slug}-{suffix}.md"
                    suffix += 1
                candidate.write_text(f"# {title}\n\n{content}\n" if content else f"# {title}\n", encoding="utf-8")

                result: dict[str, Any] = {
                    "note": {"filename": candidate.name, "title": title, "content": content}
                }
                if body.get("draft_now"):
                    run_res = run_pipeline_subprocess(source="notes", limit=5, timeout=30)
                    result["pipeline_output"] = run_res["stdout"] or run_res["stderr"]
                    result["drafts"] = run_res["drafts"]
                self.send_json(HTTPStatus.CREATED, result)
            elif path == "/api/ai/test":
                self.send_json(HTTPStatus.OK, ai_client.test_connection(config, body))
            elif path == "/api/ai/models":
                self.send_json(HTTPStatus.OK, {"models": ai_client.fetch_available_models(config, body)})
            elif path == "/api/discover/fetch":
                self.send_json(HTTPStatus.OK, {"items": discover.fetch_inbox_items(config)})
            elif path == "/api/discover/reset":
                discover.reset_dismissed()
                self.send_json(HTTPStatus.OK, {"items": discover.fetch_inbox_items(config)})
            elif path == "/api/discover/dismiss":
                discover.dismiss_item(str(body.get("id") or ""))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif path == "/api/discover/send":
                title = str(body.get("title") or "Untitled Post").strip()
                raw_text = str(body.get("text") or "").strip()
                summary = str(body.get("summary") or "").strip()
                url = str(body.get("url") or "").strip()
                platform = str(body.get("platform") or "linkedin").strip().lower()

                if not raw_text and url and (body.get("fetch_full") or not summary):
                    try:
                        extracted = discover.fetch_and_extract_url(url, timeout=12)
                        raw_text = str(extracted.get("full_text") or "").strip()
                    except Exception:
                        raw_text = ""

                created = create_new_draft(
                    config,
                    {
                        "title": title,
                        "post_copy": trim_article_for_draft(raw_text or summary, max_chars=2400) or title,
                        "platform": platform if platform in VALID_PLATFORMS else "linkedin",
                        "source_name": str(body.get("source_name") or "Discover Inbox").strip(),
                        "source_link": url,
                        "generator": "discover",
                        "style": "custom",
                    },
                )
                if body.get("id"):
                    discover.mark_sent(str(body["id"]))
                self.send_json(HTTPStatus.CREATED, {"draft": created})
            elif path == "/api/ai/rewrite":
                if ai_client.get_ai_settings(config)["provider"] == "local_templates":
                    raise ValueError("No AI model connected. Click the AI Model button in the top bar to connect one.")
                if not str(body.get("post_copy") or body.get("title") or "").strip():
                    raise ValueError("Add a title or draft text first before rewriting.")
                sys_p, user_p = build_rewrite_prompt(body, config)
                rewritten, model_used = ai_client.generate_text(user_p, config, system_prompt=sys_p, timeout=40)
                self.send_json(HTTPStatus.OK, {"post_copy": rewritten, "model_used": model_used})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown route."})
        except (ValueError, RuntimeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except subprocess.TimeoutExpired:
            self.send_json(HTTPStatus.GATEWAY_TIMEOUT, {"error": "Pipeline run timed out."})
        except Exception as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self.read_json_body()
            config = load_config()

            if path == "/api/drafts":
                rel_id = str(body.get("id") or "")
                queue_dir = get_queue_dir(config)
                target = safe_subpath(queue_dir, rel_id)
                if not target.is_file():
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Draft not found."})
                    return

                date_str = target.parent.name if target.parent != queue_dir else ""
                current = parse_draft_markdown(target.read_text(encoding="utf-8"), rel_id, date_str, target.name)

                if "title" in body:
                    current["title"] = str(body["title"]).strip() or current["title"]
                for key in ("post_copy", "first_comment"):
                    if key in body:
                        current[key] = str(body[key])
                if "platform" in body:
                    plat = str(body["platform"]).strip().lower()
                    if plat not in VALID_PLATFORMS:
                        raise ValueError(f"Invalid platform '{plat}'.")
                    current["platform"] = plat
                if "style" in body:
                    current["style"] = str(body["style"]).strip() or current["style"]
                if "status" in body:
                    st = str(body["status"]).strip()
                    if st not in VALID_STATUSES:
                        raise ValueError(f"Invalid status '{st}'.")
                    current["status"] = st
                if "scheduled_for" in body:
                    current["scheduled_for"] = normalize_scheduled_for(body["scheduled_for"])

                rendered = serialize_draft_markdown(current)
                target.write_text(rendered, encoding="utf-8")
                self.send_json(HTTPStatus.OK, {"draft": parse_draft_markdown(rendered, rel_id, date_str, target.name)})
            elif path == "/api/config":
                self.send_json(HTTPStatus.OK, {"config": save_config(body)})
            elif path == "/api/studio/presets":
                self.send_json(HTTPStatus.OK, save_studio_presets(body))
            elif path == "/api/ai":
                ai_client.save_ai_settings(CONFIG_PATH, body)
                self.send_json(HTTPStatus.OK, ai_client.get_public_ai_state(load_config()))
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown route."})
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description="LinkedIn Content Studio local server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()

    server = ReusableThreadingHTTPServer((args.host, args.port), StudioHandler)
    print(f"LinkedIn Content Studio running at http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down LinkedIn Content Studio.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
