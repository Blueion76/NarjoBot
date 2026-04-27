# NarjoBot

A Discord bot for the **Narjo Music** server that provides structured bug reporting and feature requesting via slash commands inside Discord forum channels. Reports are submitted through guided modals, auto-organized with tags, and tracked with persistent status panels that moderators can update with a single click.

---

## Features

- `/bugreport` — Submit a structured bug report in any configured app forum channel
- `/request` — Submit a feature request in the dedicated `#feature-request` forum channel
- Persistent status panels with one-click mod controls on every thread
- Auto-tagging threads with status and category tags on creation
- Pinned how-to posts via `!pinbugreport` and `!pinfeaturerequest`
- Reporter ping notifications when status changes
- Automatic thread archiving/locking on resolution
- Manually-created threads in bug forums are auto-tagged and receive a status panel

---

## Requirements

- Python 3.12+
- A Discord bot token with the following intents enabled:
  - **Server Members Intent**
  - **Message Content Intent**
- Discord forum channels set up for each app and for feature requests
- Forum tags created in Discord matching the names in your `.env`

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

Create one **Forum** channel per app you want to track bugs for (e.g. `#navidrome-bugs`, `#plex-bugs`), plus one shared **Forum** channel for feature requests (e.g. `#feature-requests`).

### 4. Add Forum Tags

Tags must be created inside each forum channel in Discord **before** running the bot. The bot looks up tags by name — if a tag is missing or misspelled, it will be silently skipped.

#### Bug report forum tags (add to each app's forum channel)

**Status tags** (required for status panel to work):

| Tag Name | Purpose |
|----------|---------|
| `Unresolved` | Default tag for new reports |
| `Needs Info` | Waiting on reporter for more details |
| `Fixed` | Resolved |
| `Won't Fix` | Out of scope / can't reproduce |

**Category tags** (optional, used by `/bugreport` category selector):

| Tag Name | Purpose |
|----------|---------|
| `Other` | Miscellaneous |
| `UI` | Interface / layout issues |
| `Sync / Library` | Sync, metadata, library scans |
| `Performance` | Slowdowns, high resource usage |
| `Auth` | Login, permissions, token issues |

#### Feature request forum tags (add to the `#feature-requests` forum)

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

> **Tip:** Tag names are case-insensitive in the bot's matching logic, but it's best practice to match the casing in `env.example` exactly to avoid confusion.

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
MOD_ROLE_ID=000000000000000000        # Role allowed to update report statuses

# ── Optional ───────────────────────────────────────────────────────────────────
PLATFORM_HINT="Narjo 1.3(70) - iOS 26.4"   # Placeholder text in the bug report version field

# ── Bug report forum channel IDs (one per app) ────────────────────────────────
FORUM_NAVIDROME_ID=000000000000000000
FORUM_PLEX_ID=000000000000000000
FORUM_JELLYFIN_ID=000000000000000000
FORUM_EMBY_ID=000000000000000000

# ── Feature request forum channel ID ──────────────────────────────────────────
FORUM_FEATURE_REQUEST_ID=000000000000000000

# ── Bug report status tag names ───────────────────────────────────────────────
TAG_NAME_UNRESOLVED=Unresolved
TAG_NAME_NEEDS_INFO=Needs Info
TAG_NAME_FIXED=Fixed
TAG_NAME_WONT_FIX=Won't Fix

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
| `MOD_ROLE_ID` | Discord → right-click the moderator role → Copy Role ID |
| `FORUM_*_ID` | Discord → right-click the forum channel → Copy Channel ID |

> **Never commit your `.env` file.** It is already in `.gitignore`.

---

## Commands

### Slash Commands

| Command | Where to use | Who can use | Description |
|---------|-------------|-------------|-------------|
| `/bugreport [category]` | Inside a configured bug-report forum | Anyone | Opens a modal to submit a structured bug report |
| `/request [category]` | Inside `#feature-requests` | Anyone | Opens a modal to submit a feature request |

Both commands accept an optional `category` argument from a preset list: `Other`, `UI`, `Sync / Library`, `Performance`, `Auth`.

### Prefix Commands (Moderators Only)

These require the `Manage Channels` permission.

| Command | Where to run | Description |
|---------|-------------|-------------|
| `!pinbugreport` | Inside a bug-report forum or thread | Creates a pinned "How to Submit" guide thread |
| `!pinfeaturerequest` | Inside the feature-request forum or thread | Creates a pinned "How to Submit" guide thread |
| `!listtags` | Anywhere | Lists all forum tags and their IDs for every configured forum |
| `!bugstatus` | Anywhere | Prints the bot's current config: forum IDs, tag names, mod role |

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

## Troubleshooting

### `/bugreport` or `/request` doesn't appear in autocomplete

Slash commands are synced guild-by-guild on startup. **Restart the bot** — on startup, the bot calls `copy_global_to` + `sync(guild=guild)` for every guild it's in, which registers commands instantly. If commands still don't appear after a restart, check the bot's console output for errors during `on_ready`.

### Commands say "wrong channel" when used in the right place

Run `!bugstatus` to check what forum IDs the bot has loaded. If any show `0`, the corresponding env var is missing or the bot wasn't restarted after the `.env` was updated.

### Tags aren't being applied to threads

Run `!listtags` to see what tags the bot can see in each forum. Compare against your `.env` tag name values — they must match exactly (the bot does case-insensitive comparison, but extra spaces will cause misses).

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
