# NarjoBot

A Discord bot for the **Narjo Music** server that provides structured bug reporting and feature requesting via slash commands inside Discord forum channels. Reports are submitted through guided modals, auto-organized with tags, and tracked with persistent status panels that moderators can update with a single click. An optional Gemini AI integration posts advisory comments on every submitted report.

---

## Features

- `/bugreport <platform> [category]` — Submit a structured bug report; music platform chosen from a native Discord dropdown
- `/request [category]` — Submit a feature request in the dedicated `#feature-requests` forum channel
- `/submit-log <file>` — Upload a Narjo `.txt` debug log into an existing bug report thread for automatic parsing and AI analysis
- Gemini-powered AI advisory comments posted on every bug report and feature request
- Deterministic log parsing (severity, error lines, key metrics, anomaly detection)
- Persistent status panels with one-click mod controls on every thread
- Auto-tagging threads with status, platform, and category tags on creation
- Pinned how-to posts via `!pinbugreport` and `!pinfeaturerequest`
- Reporter ping notifications when status changes
- Automatic thread archiving/locking on resolution
- Manually-created threads in the bug forum are auto-tagged and receive a status panel

---

## Requirements

- Python 3.12+
- A Discord bot token with the following intents enabled:
  - **Server Members Intent**
  - **Message Content Intent**
- A single Discord forum channel for all bug reports
- A separate Discord forum channel for feature requests
- Forum tags created in Discord matching the names in your `.env`
- A Google AI Studio API key (for Gemini AI comments — optional but recommended)

---

## Discord Setup

### 1. Create the Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, give it a name, and save
3. Go to **Bot** in the left sidebar
4. Click **Reset Token** and copy the token — you'll need it for your `.env`
5. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
6. Go to **OAuth2 → URL Generator**
7. Under **Scopes**, select `bot` and `applications.commands`
8. Under **Bot Permissions**, select at minimum:
   - `Read Messages/View Channels`
   - `Send Messages`
   - `Manage Threads`
   - `Create Public Threads`
   - `Send Messages in Threads`
   - `Embed Links`
   - `Manage Messages`
9. Copy the generated URL, open it in your browser, and invite the bot to your server

### 2. Enable Developer Mode

To copy channel and role IDs in Discord:

1. Open Discord **Settings → Advanced**
2. Toggle **Developer Mode** on
3. Right-click any channel or role → **Copy ID**

### 3. Create Forum Channels

Create one **Forum** channel for all bug reports (e.g. `#bug-reports`) and one for feature requests (e.g. `#feature-requests`). The bot now handles all platforms (Navidrome, Jellyfin, Emby, Plex) inside the single bug report forum — the platform is selected by the user as part of the `/bugreport` command.

### 4. Add Forum Tags

Tags must be created inside each forum channel in Discord **before** running the bot. The bot looks up tags by name — if a tag is missing or misspelled it will be silently skipped.

#### Bug report forum tags

**Status tags** (required for status panel to work):

| Tag Name | Purpose |
|----------|---------|
| `Unresolved` | Default tag for new reports |
| `Needs Info` | Waiting on reporter for more details |
| `Fixed` | Resolved |
| `Won't Fix` | Out of scope / can't reproduce |

**Platform tags** (applied automatically based on the platform chosen at submission):

| Tag Name | Platform |
|----------|---------|
| `Navidrome` | Navidrome / OpenSubsonic |
| `Jellyfin` | Jellyfin |
| `Emby` | Emby |
| `Plex` | Plex |

**Category tags** (optional, used by the `/bugreport` category selector):

| Tag Name | Purpose |
|----------|---------|
| `Other` | Miscellaneous |
| `UI` | Interface / layout issues |
| `Sync / Library` | Sync, metadata, library scans |
| `Performance` | Slowdowns, high resource usage |
| `Auth` | Login, permissions, token issues |

#### Feature request forum tags

**Status tags:**

| Tag Name | Purpose |
|----------|---------|
| `Open` | Default tag for new requests |
| `Planned` | Confirmed, on the roadmap |
| `In Progress` | Actively being built |
| `Completed` | Shipped |
| `Declined` | Won't be pursued |

**Category tags** (same names as bug report category tags above):

`Other`, `UI`, `Sync / Library`, `Performance`, `Auth`

> **Tip:** Tag names are case-insensitive in the bot's matching logic, but matching the casing in `env.example` exactly avoids confusion.

---

## Installation

### Option A — Run with Python directly

```bash
# 1. Clone the repo
git clone https://github.com/Blueion76/NarjoBot.git
cd NarjoBot

# 2. (Optional) Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp env.example .env
# Edit .env with your values (see Configuration section below)

# 5. Run the bot
python bot.py
```

### Option B — Run with Docker

```bash
# 1. Clone the repo
git clone https://github.com/Blueion76/NarjoBot.git
cd NarjoBot

# 2. Configure environment variables
cp env.example .env
# Edit .env with your values (see Configuration section below)

# 3. Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

---

## Configuration

Copy `env.example` to `.env` and fill in each value:

```env
# ── Required ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN=your-bot-token-here
MOD_ROLE_ID=000000000000000000           # Role allowed to update report statuses
GOOGLE_AI_STUDIO_API_KEY=your-key-here  # Get one free at aistudio.google.com

# ── Optional ───────────────────────────────────────────────────────────────────
PLATFORM_HINT="Narjo 1.3(70) — iOS 18.4"  # Placeholder in the version field

# ── Bug report forum channel ID (single unified forum) ────────────────────────
FORUM_BUG_REPORT_ID=000000000000000000

# ── Feature request forum channel ID ──────────────────────────────────────────
FORUM_FEATURE_REQUEST_ID=000000000000000000

# ── Bug report status tag names ───────────────────────────────────────────────
TAG_NAME_UNRESOLVED=Unresolved
TAG_NAME_NEEDS_INFO=Needs Info
TAG_NAME_FIXED=Fixed
TAG_NAME_WONT_FIX=Won't Fix

# ── Platform tag names (applied based on platform chosen at submission) ────────
TAG_NAME_NAVIDROME=Navidrome
TAG_NAME_JELLYFIN=Jellyfin
TAG_NAME_EMBY=Emby
TAG_NAME_PLEX=Plex

# ── Shared category tag names ─────────────────────────────────────────────────
TAG_NAME_OTHER=Other
TAG_NAME_UI=UI
TAG_NAME_SYNC=Sync / Library
TAG_NAME_PERFORMANCE=Performance
TAG_NAME_AUTH=Auth

# ── Feature request status tag names ─────────────────────────────────────────
TAG_NAME_REQ_OPEN=Open
TAG_NAME_REQ_PLANNED=Planned
TAG_NAME_REQ_IN_PROGRESS=In Progress
TAG_NAME_REQ_COMPLETED=Completed
TAG_NAME_REQ_DECLINED=Declined
```

### How to get IDs

| Value | How to get it |
|-------|---------------|
| `DISCORD_TOKEN` | Discord Developer Portal → your app → Bot → Reset Token |
| `GOOGLE_AI_STUDIO_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key |
| `MOD_ROLE_ID` | Discord → right-click the moderator role → Copy Role ID |
| `FORUM_BUG_REPORT_ID` | Discord → right-click the bug report forum channel → Copy Channel ID |
| `FORUM_FEATURE_REQUEST_ID` | Discord → right-click the feature request forum channel → Copy Channel ID |

> **Never commit your `.env` file.** It is already in `.gitignore`.

---

## Commands

### Slash Commands

| Command | Where to use | Who can use | Description |
|---------|-------------|-------------|-------------|
| `/bugreport <platform> [category]` | Inside `#bug-reports` | Anyone | Opens a modal to submit a structured bug report. Platform (Navidrome / OpenSubsonic, Jellyfin, Emby, Plex) is chosen from a dropdown before the modal opens. |
| `/request [category]` | Inside `#feature-requests` | Anyone | Opens a modal to submit a feature request |
| `/submit-log <file>` | Inside your own bug report thread | Reporter or mod | Uploads a Narjo `.txt` debug log, parses it, and posts a structured analysis embed and AI advisory comment in the thread |

Both `/bugreport` and `/request` accept an optional `category` argument: `Other`, `UI`, `Sync / Library`, `Performance`, `Auth`.

### Prefix Commands (Moderators Only)

These require the `Manage Channels` permission.

| Command | Where to run | Description |
|---------|-------------|-------------|
| `!pinbugreport` | Inside the bug-report forum or thread | Creates a pinned "How to Submit" guide thread |
| `!pinfeaturerequest` | Inside the feature-request forum or thread | Creates a pinned "How to Submit" guide thread |
| `!listtags` | Anywhere | Lists all forum tags and their IDs for every configured forum |
| `!bugstatus` | Anywhere | Prints the bot's current config: forum IDs, AI flags, tag names, mod role |

---

## Status Panels

Every submitted report or request gets an embed with action buttons posted automatically. Buttons stay active indefinitely — the bot persists views across restarts.

### Bug Report Buttons

| Button | Permission | Action |
|--------|-----------|--------|
| ✅ Fixed | Mod only | Tags thread Fixed, archives and locks it, pings reporter |
| 💬 Needs Info | Mod only | Tags thread Needs Info, pings reporter |
| ⛔ Won't Fix | Mod only | Tags thread Won't Fix, archives and locks it, pings reporter |
| 🔁 Reopen | Anyone | Tags thread Unresolved, unarchives and unlocks it |

### Feature Request Buttons

| Button | Permission | Action |
|--------|-----------|--------|
| 🗺️ Planned | Mod only | Tags thread Planned, pings requester |
| 🔨 In Progress | Mod only | Tags thread In Progress, pings requester |
| 🎉 Completed | Mod only | Tags thread Completed, archives and locks it, pings requester |
| ⛔ Declined | Mod only | Tags thread Declined, archives and locks it, pings requester |
| 🔁 Reopen | Anyone | Tags thread Open, unarchives and unlocks it |

---

## AI Features

When `GOOGLE_AI_STUDIO_API_KEY` is set, the bot posts advisory comments automatically using Gemini (`gemini-2.5-flash`). These are formatted as embeds with clearly labelled sections, not walls of text.

### Bug report advisory (posted on every `/bugreport` submission)

| Section | Content |
|---------|---------|
| **Cause** | Most likely root cause based on the form fields |
| **Evidence** | What in the report supports that cause |
| **Fix** | Code area or behavior to inspect |
| **Instrumentation** | What extra log data would help next time |

### Log analysis advisory (posted after `/submit-log`)

Same four sections as above, but driven by the parsed log data rather than form text. The log is also redacted (tokens, IPs, URLs, emails stripped) and optionally re-attached to the thread.

### Feature request refinement (posted on every `/request` submission)

| Section | Content |
|---------|---------|
| **User Value** | Who benefits and how |
| **Behavior** | Suggested behavior and acceptance criteria |
| **Edge Cases** | Implementation notes, edge cases, or risks |

AI comments are clearly labelled as advisory. If the AI is rate-limited or unavailable, a descriptive error embed is posted instead of a generic failure message.

---

## Log Submission (`/submit-log`)

Run `/submit-log` inside your existing bug report thread and attach a Narjo `.txt` debug log (exported from **Settings → More → Diagnostics**).

The bot will:

1. Validate and redact the log (removes tokens, IPs, URLs, emails)
2. Post a **Log Analysis** embed with severity, client info, playback context, key metrics, and detected anomalies
3. Post a **High-signal log lines** snippet for the most relevant error/warning lines
4. Re-attach a redacted copy of the log to the thread (if under 900 KB)
5. Post a **AI Advisory (Log Analysis)** embed with cause, evidence, fix, and instrumentation suggestions

Only the original reporter or a moderator can run `/submit-log` in a given thread.

---

## Troubleshooting

### `/bugreport` or `/request` doesn't appear in autocomplete

Slash commands are synced guild-by-guild on startup. **Restart the bot** — on startup it calls `copy_global_to` + `sync(guild=guild)` for every guild it's in, which registers commands instantly. If commands still don't appear after a restart, check the bot's console output for errors during `on_ready`.

### Commands say "wrong channel" when used in the right place

Run `!bugstatus` to check what forum IDs the bot has loaded. If any show `0`, the corresponding env var is missing or the bot wasn't restarted after the `.env` was updated.

### Tags aren't being applied to threads

Run `!listtags` to see what tags the bot can see in each forum. Compare against your `.env` tag name values — they must match exactly (the bot does case-insensitive comparison, but extra spaces will cause misses). Platform tags (Navidrome, Jellyfin, etc.) must be created in the bug report forum for them to be applied.

### AI comments aren't appearing

Check that `GOOGLE_AI_STUDIO_API_KEY` is set in your `.env` and that the `google-genai` package is installed (`pip install google-genai`). If the key is valid but the AI is unavailable, the bot will post a descriptive error embed rather than failing silently.

### `/submit-log` says "You can only use this in your own thread"

Only the user who originally submitted the bug report (or a moderator) can upload a log. If you submitted the report and are still seeing this, check that the thread's opening embed still has the original footer containing your Reporter ID.

### Bot goes offline after some time

If running with `python bot.py` directly in a terminal, the process dies when the session ends. Use a process manager like `systemd`, `pm2`, or Docker (recommended) to keep it running persistently.

### Buttons stop working after bot restart

This should not happen — views are re-registered on every startup via `bot.add_view(StatusPanel())` and `bot.add_view(FeatureRequestStatusPanel())`. If buttons show "This interaction failed", check that the bot is actually online.

---

## Project Structure

```
NarjoBot/
├── bot.py              # All bot logic
├── env.example         # Environment variable template
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image definition
├── docker-compose.yml  # Docker Compose config
└── .gitignore
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes
4. Push and open a pull request against `main`
