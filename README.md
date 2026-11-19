# Content Studio & Automated Social Content Pipeline

A local-first, zero-dependency **Text & Markdown Content Studio** and RSS/notes pipeline for **LinkedIn**, **X (Twitter)**, and **Threads**. Built entirely with the Python 3.10+ standard library and vanilla HTML/CSS/JavaScript—no frameworks, no external packages, and no cloud lock-in.

---

## Key Features

- **Discover Feed Inbox (`Discover` tab)**
  - Pulls fresh posts from your configured RSS and Atom feeds into a centered inbox without cluttering your draft queue.
  - Every feed item offers **Open Original ↗**, **Send to Studio →** (automatically extracts full readable article text from the source webpage with graceful fallback to the RSS excerpt), and **Delete** (with **Reset Skipped** anytime).
- **Multi-Platform Studio Editor (`Studio` tab)**
  - **Draft Queue:** Filter by status (`All`, `Draft`, `Ready`, `Scheduled`, `Published`, `Archived`), search across titles/hooks/sources, and delete in 1 click with an **Undo** toast.
  - **Custom AI Prompt Suite:** Write custom rewrite instructions, apply 1-click **Saved Prompt Templates**, switch **Voice & Tone Profiles**, click **Adapt for Platform**, and step backward anytime with multi-step **Undo**.
  - **Live Multi-Platform Previews & Meters:**
    - **LinkedIn:** `210`-char above-the-fold hook meter (`...see more` fold toggle) and `3,000`-char limit.
    - **X (Twitter):** `280`-char single-post meter plus automatic multi-post thread preview split on blank lines (`1/N · chars/280`).
    - **Threads:** `500`-char meter and live Threads card preview.
    - Toggle **Desktop / Mobile** width, **Card: Light / Dark**, and **Obsidian Dark / Daylight Light** app themes.
- **5-Stage Kanban Board & Scheduler (`Board` tab)**
  - Drag and drop or use quick-move buttons across `Draft → Ready → Scheduled → Published → Archived`.
  - Filter the board by platform (`All Platforms`, `LinkedIn`, `X`, `Threads`) and delete any card in 1 click with **Undo**.
  - **Publish Scheduler:** Pick a date & time (or use 1-click presets), export `.ics` calendar reminders, and receive **in-app due alerts** (top banner + notification bell popover) with 1-click **Copy & Publish**.
- **Quick Idea Capture (`Notes` tab)**
  - Save rough ideas as plain `.md` files in `notes/` or click **Save & Draft Now** to immediately turn a note into a queue draft.
- **Universal 7-Provider AI Client (`AI Model` topbar switcher)**
  - Works offline out of the box with **Local Templates**, or connects to **Google Gemini**, **OpenAI**, **Anthropic Claude**, **OpenRouter**, **Ollama (Local)**, or any **Custom OpenAI-Compatible Endpoint** (LM Studio, Groq, DeepSeek, vLLM).
  - API keys are stored locally in `.ai_secrets.json` with owner-only `0600` file permissions and are masked in all API responses.

---

## Project Architecture

```text
content-studio/
├── studio.py            # Zero-dependency ThreadingHTTPServer + REST API (127.0.0.1:8765)
├── ai_client.py         # Universal 7-provider LLM client & local 0600 key manager
├── discover.py          # RSS/Atom inbox state manager & full-article HTML text extractor
├── pipeline.py          # Standalone CLI batch generator for RSS feeds & Markdown notes
├── config.json          # Active profile, feeds, AI provider config, templates & voices
├── launch.sh            # Desktop launcher (starts service/daemon & opens browser)
├── web/
│   ├── index.html       # Single-page Studio layout & modals
│   ├── styles.css       # Obsidian Dark & Daylight Light theme design system
│   ├── app.js           # Vanilla JS state management, live previews & API client
│   └── icon.svg         # App launcher icon
├── queue/YYYY-MM-DD/    # Plain Markdown draft files + daily INDEX.md
└── notes/               # Plain Markdown/text rough idea notes
```

### Runtime State Files (Auto-Generated)

| File | Purpose |
| :--- | :--- |
| `.ai_secrets.json` | Provider API keys saved from the UI (`chmod 600`, never exposed in raw form) |
| `.inbox_cache.json` | Cached Discover inbox items from the latest feed fetch |
| `.inbox_state.json` | Bounded history (last 1,000 IDs) of dismissed and sent Discover items |
| `.pipeline_state.json` | Bounded history (last 1,000 IDs) of items processed by `pipeline.py` |

---

## Quick Start & Cross-Platform Setup (Linux, Windows & macOS)

Because the entire backend uses **only the Python 3.10+ standard library** (`http.server`, `urllib.request`, `xml.etree.ElementTree`, `pathlib`, `json`, `re`) with OS-agnostic `pathlib.Path` file handling and zero compiled C extensions or third-party packages, it runs identically on **Linux**, **Windows**, and **macOS**.

**Prerequisite on any OS:** Python `3.10` or newer installed (`python3 --version` or `python --version`). No `pip install` or virtual environment is required.

### 1. Linux

```bash
# One-click launcher (starts background service if needed and opens browser)
./launch.sh

# Or run directly in the terminal
python3 studio.py --host 127.0.0.1 --port 8765
```

Manage the persistent `systemd --user` service:

```bash
systemctl --user status linkedin-content-studio.service
systemctl --user restart linkedin-content-studio.service
journalctl --user -u linkedin-content-studio.service -f
```

### 2. Microsoft Windows (Windows 10 / 11)

Open **PowerShell** or **Command Prompt** in the project folder:

```powershell
# Start the Web Studio server
python studio.py --host 127.0.0.1 --port 8765

# Then open in your browser:
start http://127.0.0.1:8765/
```

- **One-Click Windows Desktop Shortcut (`launch.bat`):**
  Create a `launch.bat` file in the project folder and double-click it anytime:
  ```bat
  @echo off
  cd /d "%~dp0"
  start "" /B pythonw studio.py --host 127.0.0.1 --port 8765
  timeout /t 1 /nobreak >nul
  start http://127.0.0.1:8765/
  ```
- **Run Automatically on Windows Login:** Place a shortcut to `launch.bat` inside your Windows Startup folder (`Win + R` → type `shell:startup`).

### 3. Apple macOS

Open **Terminal** in the project folder:

```bash
# Start the Web Studio server
python3 studio.py --host 127.0.0.1 --port 8765

# Open in your default browser
open http://127.0.0.1:8765/
```

- **One-Click Finder / Dock Shortcut (`launch.command`):**
  Save this as `launch.command` in the project folder and make it executable (`chmod +x launch.command`):
  ```bash
  #!/usr/bin/env bash
  cd "$(dirname "$0")"
  if ! pgrep -f "studio.py" >/dev/null 2>&1; then
    nohup python3 studio.py >/tmp/content-studio.log 2>&1 &
    sleep 0.6
  fi
  open "http://127.0.0.1:8765/"
  ```
- **Run Automatically on macOS Login:** Add `launch.command` under **System Settings → General → Login Items** (or load a user LaunchAgent plist in `~/Library/LaunchAgents/`).

### 4. Run the Standalone CLI Pipeline (All Operating Systems)

```bash
python3 pipeline.py                  # Draft up to max_items_per_run posts from notes + feeds
python3 pipeline.py --limit 3        # Draft at most 3 posts
python3 pipeline.py --source notes   # Draft only from notes/
python3 pipeline.py --source feeds   # Draft only from RSS/Atom feeds
python3 pipeline.py --dry-run        # Preview candidate items without writing files
python3 pipeline.py --reset-state    # Reset deduplication history before running
```
*(On Windows, substitute `python` for `python3`.)*

---

## Connecting an AI Provider

Click the **`AI: ...`** button in the top bar of the Web Studio to configure any provider:

| Provider | Protocol | Default Model | API Key Env Var Fallback |
| :--- | :--- | :--- | :--- |
| **Local Templates** | Offline | *(none)* | No key required |
| **Google Gemini** | Gemini REST | `gemini-2.5-flash` | `GEMINI_API_KEY` |
| **OpenAI** | OpenAI-Compatible | `gpt-4o-mini` | `OPENAI_API_KEY` |
| **Anthropic Claude** | Claude Messages | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| **OpenRouter** | OpenAI-Compatible | `google/gemini-2.5-flash` | `OPENROUTER_API_KEY` |
| **Ollama (Local)** | OpenAI-Compatible | `llama3.2` (`http://127.0.0.1:11434/v1`) | No key required |
| **Custom Endpoint** | OpenAI-Compatible | `local-model` (`http://127.0.0.1:1234/v1`) | `AI_API_KEY` (optional) |

Use **Fetch Models** in the modal to query live model IDs from your endpoint and **Test Connection** to verify latency and credentials.

---

## Draft Markdown Format

Every draft is stored as a portable Markdown file in `queue/YYYY-MM-DD/<NN>-<slug>.md`:

```markdown
# LinkedIn Draft: Post Title

- **Source:** [Hacker News](https://example.com/article)
- **Platform:** `linkedin`
- **Style:** `custom`
- **Generator:** `discover`
- **Hook Length:** 142 chars — OK (fits above '...see more')
- **Total Length:** 845 / 3000 chars
- **Status:** `[@] Scheduled`
- **Scheduled:** `2026-11-20T09:00`

---

## Post Copy (Ready to Paste)

Your post copy lives here...

---

## Optional First Comment (Put Links Here for Better Reach)
```

Status tokens map automatically between Markdown and the Kanban board:
- `[ ] Draft` → `draft`
- `[~] Ready to publish` → `ready`
- `[@] Scheduled` → `scheduled`
- `[x] Published` → `published`
- `[-] Archived` → `archived`

---

## REST API Reference (`studio.py`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/drafts` | List all drafts across `queue/` sorted newest first |
| `POST` | `/api/drafts/new` | Create a new draft file in `queue/<today>/` |
| `PUT` | `/api/drafts` | Update draft title, copy, platform, status, or `scheduled_for` |
| `POST` | `/api/drafts/delete` | Delete a draft file by relative queue ID (`id`) |
| `GET` | `/api/discover` | Load cached Discover Feed Inbox items |
| `POST` | `/api/discover/fetch` | Fetch live RSS/Atom feeds into the Discover inbox |
| `POST` | `/api/discover/reset` | Clear dismissed feed item history and re-fetch feeds |
| `POST` | `/api/discover/send` | Extract full article text (with summary fallback) and create a Studio draft |
| `POST` | `/api/discover/dismiss` | Dismiss/delete an item from the Discover Feed Inbox |
| `GET` | `/api/notes` | List all Markdown/text notes in `notes/` |
| `POST` | `/api/notes` | Save a new note in `notes/` (pass `draft_now: true` to draft immediately) |
| `POST` | `/api/notes/delete` | Delete a note by `filename` |
| `GET` | `/api/config` | Load config, masked AI state, prompt templates, and voice profiles |
| `PUT` | `/api/config` | Update preview profile identity and RSS/Atom feeds |
| `PUT` | `/api/studio/presets` | Save custom AI prompt templates, voice profiles, and active voice ID |
| `PUT` | `/api/ai` | Save active AI provider settings and/or API key |
| `POST` | `/api/ai/test` | Run a live connectivity check against the selected AI provider |
| `POST` | `/api/ai/models` | Fetch available model IDs from the provider endpoint |
| `POST` | `/api/ai/rewrite` | Rewrite or adapt draft copy using active Voice & Tone + custom prompt |


---

### Active Project License
This repository is released under the **MIT License** — see [LICENSE](./LICENSE) for full terms.
