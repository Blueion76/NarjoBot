"""
Narjo Discord Bot — Merged Edition

Combines:
  • Modal-based bug reports and feature requests (with status panels) from bot.py
  • AI advisory summaries (Gemini) and log parsing from narjo_issue_bot.py

Commands:
  /bugreport  <platform> [category]  — Opens the bug report modal; platform chosen as slash-command option
  /request    [category]             — Opens the feature request modal
  /submit-log <log_file>             — Upload a .txt debug log into an existing bug thread

Prefix commands (mod-only):
  !pinbugreport       — Create a pinned how-to post in the bug report forum
  !pinfeaturerequest  — Create a pinned how-to post in the feature request forum
  !listtags           — List all forum tags across configured channels
  !bugstatus          — Print bot config summary

Install:
    pip install -U discord.py python-dotenv google-genai

Run:
    python bot.py
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import textwrap
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

try:
    from google import genai
except Exception:
    genai = None

load_dotenv()


# =============================================================================
# CONFIGURATION — set values in your .env file
# =============================================================================

TOKEN                   = os.getenv("DISCORD_TOKEN")
MOD_ROLE_ID             = int(os.getenv("MOD_ROLE_ID", 0))
GOOGLE_AI_STUDIO_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY", "")

# Universal platform hint shown as a placeholder in the modal form
PLATFORM_HINT = os.getenv("PLATFORM_HINT", "Narjo 1.3(73) — iOS 26.4")

# ── Single unified bug report forum ───────────────────────────────────────────
BUG_REPORT_FORUM_ID = int(os.getenv("FORUM_BUG_REPORT_ID", 0))

# Platform display names, embed colours, and slash-command choice values
PLATFORMS: dict[str, discord.Color] = {
    "Navidrome / OpenSubsonic": discord.Color.from_str("#FF8200"),
    "Jellyfin":                 discord.Color.from_str("#00A4DC"),
    "Emby":                     discord.Color.from_str("#52B54B"),
    "Plex":                     discord.Color.from_str("#E5A00D"),
}

# Forum tag names to apply per platform (must exist in your Discord forum)
PLATFORM_TAG_NAMES: dict[str, str] = {
    "Navidrome / OpenSubsonic": os.getenv("TAG_NAME_NAVIDROME", "Navidrome"),
    "Jellyfin":                 os.getenv("TAG_NAME_JELLYFIN", "Jellyfin"),
    "Emby":                     os.getenv("TAG_NAME_EMBY", "Emby"),
    "Plex":                     os.getenv("TAG_NAME_PLEX", "Plex"),
}

# ── Shared feature request forum ──────────────────────────────────────────────
FEATURE_REQUEST_FORUM_ID = int(os.getenv("FORUM_FEATURE_REQUEST_ID", 0))
FEATURE_REQUEST_COLOR    = discord.Color.from_str("#5865F2")

# ── Bug report tag names ───────────────────────────────────────────────────────
STATUS_TAG_NAMES = {
    "unresolved": os.getenv("TAG_NAME_UNRESOLVED", "Unresolved"),
    "needs_info": os.getenv("TAG_NAME_NEEDS_INFO", "Needs Info"),
    "fixed":      os.getenv("TAG_NAME_FIXED", "Fixed"),
    "wont_fix":   os.getenv("TAG_NAME_WONT_FIX", "Won't Fix"),
}
CATEGORY_TAG_NAMES = {
    "other":       os.getenv("TAG_NAME_OTHER", "Other"),
    "ui":          os.getenv("TAG_NAME_UI", "UI"),
    "sync":        os.getenv("TAG_NAME_SYNC", "Sync / Library"),
    "performance": os.getenv("TAG_NAME_PERFORMANCE", "Performance"),
    "auth":        os.getenv("TAG_NAME_AUTH", "Auth"),
}

# ── Feature request tag names ─────────────────────────────────────────────────
REQUEST_STATUS_TAG_NAMES = {
    "open":        os.getenv("TAG_NAME_REQ_OPEN", "Open"),
    "planned":     os.getenv("TAG_NAME_REQ_PLANNED", "Planned"),
    "in_progress": os.getenv("TAG_NAME_REQ_IN_PROGRESS", "In Progress"),
    "completed":   os.getenv("TAG_NAME_REQ_COMPLETED", "Completed"),
    "declined":    os.getenv("TAG_NAME_REQ_DECLINED", "Declined"),
}
# Feature requests share the same category tags as bug reports
REQUEST_CATEGORY_TAG_NAMES = CATEGORY_TAG_NAMES

# ── AI settings ───────────────────────────────────────────────────────────────
GEMINI_MODEL                = "gemini-2.5-flash"
ENABLE_AI_RECOMMENDATION    = True   # AI comment after bug report modal submit
ENABLE_AI_FEATURE_REFINEMENT = True  # AI comment after feature request submit
ENABLE_AI_LOG_ANALYSIS      = True   # AI comment after /submit-log

# ── Log upload limits ─────────────────────────────────────────────────────────
MAX_LOG_BYTES                  = 2_000_000
MAX_AI_INPUT_CHARS             = 24_000
MAX_ERROR_LINES                = 40
MAX_REDACTED_ATTACHMENT_BYTES  = 900_000
ATTACH_REDACTED_LOG_COPY       = True

PINNED_THREAD_PREFIX = "📌 How to Submit a "


# =============================================================================
# APP CONTEXT (passed to Gemini)
# =============================================================================

NARJO_CONTEXT = """
Narjo is a music player app for iOS. It is used as a client for self-hosted
music servers including Navidrome/Subsonic-compatible servers and Emby. Relevant
debugging areas include iOS AVPlayer/AVQueuePlayer behavior, buffering,
crossfade/gapless playback, transcoding/direct streaming, network interruptions,
route changes, CarPlay, offline downloads/cache behavior, scrobbling, and
server/client API compatibility.
"""


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class LogMetrics:
    total_events:          Optional[int] = None
    warnings_errors:       Optional[int] = None

    transitions:           Optional[int] = None
    crossfade_events:      Optional[int] = None
    pre_buffer_events:     Optional[int] = None
    pre_cache_events:      Optional[int] = None

    desync_events:         Optional[int] = None
    transcoding_errors:    Optional[int] = None
    interruptions:         Optional[int] = None
    recovery_attempts:     Optional[int] = None
    recovery_failures:     Optional[int] = None

    avqueue_events:        Optional[int] = None
    avqueue_failures:      Optional[int] = None

    stalls_detected:       Optional[int] = None
    buffer_empty_events:   Optional[int] = None
    seeks:                 Optional[int] = None
    auto_recovery_attempts: Optional[int] = None

    scrobble_events:       Optional[int] = None
    scrobble_successes:    Optional[int] = None
    scrobble_failures:     Optional[int] = None
    scrobbles_skipped:     Optional[int] = None


@dataclass
class ParsedLog:
    filename: str
    log_hash: str

    generated_at:           Optional[str] = None
    device:                 Optional[str] = None
    ios_version:            Optional[str] = None
    app_version:            Optional[str] = None
    build:                  Optional[str] = None
    playback_mode:          Optional[str] = None
    auto_resume_on_reconnect: Optional[str] = None
    server_type:            Optional[str] = None
    scrobbling:             Optional[str] = None

    metrics:                LogMetrics = field(default_factory=LogMetrics)

    event_type_counts:      dict[str, int] = field(default_factory=dict)
    repeated_event_patterns: list[str]     = field(default_factory=list)
    error_lines:            list[str]      = field(default_factory=list)
    anomaly_flags:          list[str]      = field(default_factory=list)
    suggested_tags:         list[str]      = field(default_factory=list)

    deterministic_summary:  str  = ""
    severity:               str  = "Low"


# =============================================================================
# SHARED UTILITIES
# =============================================================================

def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    return int(value) if value.isdigit() else None


def _find_value(log_text: str, label: str) -> Optional[str]:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", log_text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _find_int(log_text: str, label: str) -> Optional[int]:
    return _safe_int(_find_value(log_text, label))


def redact_sensitive_data(text: str) -> str:
    replacements = [
        (r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._\-]+",  r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)[A-Za-z0-9._\-]+",       r"\1[REDACTED]"),
        (r"(?i)(token\s*[:=]\s*)[A-Za-z0-9._\-]+",             r"\1[REDACTED]"),
        (r"(?i)(password\s*[:=]\s*)\S+",                        r"\1[REDACTED]"),
        (r"(?i)(session\s*[:=]\s*)[A-Za-z0-9._\-]+",           r"\1[REDACTED]"),
        (r"https?://[^\s)>\]]+",                                "[REDACTED_URL]"),
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                       "[REDACTED_IP]"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]"),
    ]
    redacted = text
    for pattern, replacement in replacements:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def chunk_text(text: str, max_len: int = 1900) -> list[str]:
    chunks: list[str] = []
    text = text.strip()
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at < 500:
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def clean_title(text: str, max_len: int = 95) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"[#`*_~>|]", "", cleaned)
    return cleaned[:max_len] if cleaned else "Untitled"


def normalize_tag_name(value: str) -> str:
    return value.casefold().strip()


def find_tag_by_name(forum: discord.ForumChannel, name: str) -> discord.ForumTag | None:
    target = normalize_tag_name(name)
    return discord.utils.find(lambda t: normalize_tag_name(t.name) == target, forum.available_tags)


def get_status_tag_ids_for_forum(forum: discord.ForumChannel, status_names: dict) -> set[int]:
    ids = set()
    for tag_name in status_names.values():
        tag = find_tag_by_name(forum, tag_name)
        if tag:
            ids.add(tag.id)
    return ids


def is_bug_report_thread(thread: discord.Thread) -> bool:
    """True if the thread lives in the unified bug report forum."""
    return bool(thread and thread.parent_id == BUG_REPORT_FORUM_ID)


async def get_platform_for_thread(thread: discord.Thread) -> str:
    """
    Reads the platform back from the thread's opening embed field so that
    /submit-log and the AI prompt know which server backend is involved.
    """
    try:
        starter = thread.starter_message or await thread.fetch_message(thread.id)
    except Exception:
        return "Unknown"
    if starter:
        for embed in starter.embeds:
            for field in embed.fields:
                if field.name == "🎵 Music Platform":
                    return field.value or "Unknown"
    return "Unknown"


async def get_reporter(thread: discord.Thread) -> discord.Member | None:
    if thread.owner and thread.owner.id != bot.user.id:
        return thread.owner
    try:
        starter = thread.starter_message or await thread.fetch_message(thread.id)
    except Exception:
        return None
    if starter and starter.embeds:
        embed = starter.embeds[0]
        if embed.footer and embed.footer.text:
            m = re.search(r"Reporter ID:\s*(\d+)", embed.footer.text)
            if m:
                uid = int(m.group(1))
                member = thread.guild.get_member(uid)
                if member:
                    return member
                try:
                    return await thread.guild.fetch_member(uid)
                except Exception:
                    return None
    return None


# =============================================================================
# DETERMINISTIC LOG PARSING
# =============================================================================

def parse_event_counts(log_text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in re.finditer(r"^\[[^\]]+\]\s+\[([^\]]+)\]", log_text, re.MULTILINE):
        event_type = match.group(1).strip()
        counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def extract_error_lines(log_text: str, max_lines: int = MAX_ERROR_LINES) -> list[str]:
    patterns = re.compile(
        r"error|failed|failure|fatal|exception|panic|crash|stall|interrupt|timeout|"
        r"desync|overrun|unseekable|mismatch|buffer empty|recovery",
        re.IGNORECASE,
    )
    lines: list[str] = []
    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped and patterns.search(stripped):
            lines.append(stripped)
            if len(lines) >= max_lines:
                break
    return lines


def detect_repeated_patterns(log_text: str) -> list[str]:
    candidates = {
        "Crossfade Scheduled":          log_text.count("Crossfade Scheduled"),
        "RESUME: player.play() called": log_text.count("RESUME: player.play() called"),
        "Recovery Attempt":             len(re.findall(r"Recovery Attempt|Recovery Attempts", log_text, re.I)),
        "Buffer Empty":                 len(re.findall(r"Buffer Empty", log_text, re.I)),
        "AVPlayer Error":               len(re.findall(r"AVPlayer Error", log_text, re.I)),
        "Transcoding Error":            len(re.findall(r"Transcoding Error", log_text, re.I)),
    }
    findings: list[str] = []
    for label, count in candidates.items():
        if label in {"Crossfade Scheduled", "RESUME: player.play() called"} and count >= 25:
            findings.append(f"High-frequency loop: '{label}' appears {count} times.")
        elif count >= 5:
            findings.append(f"Repeated signal: '{label}' appears {count} times.")
    return findings


def derive_severity(parsed: ParsedLog) -> str:
    m = parsed.metrics
    hard_failure_signals = [
        m.recovery_failures  or 0,
        m.transcoding_errors or 0,
        m.avqueue_failures   or 0,
        m.scrobble_failures  or 0,
    ]
    if any(v >= 3 for v in hard_failure_signals):
        return "High"
    if (m.warnings_errors or 0) >= 50:
        return "High"
    if (m.interruptions or 0) >= 3:
        return "High"
    if (m.recovery_attempts or 0) >= 10:
        return "Medium"
    if (m.warnings_errors or 0) >= 10:
        return "Medium"
    if parsed.repeated_event_patterns:
        return "Medium"
    return "Low"


def derive_anomalies(parsed: ParsedLog) -> list[str]:
    m = parsed.metrics
    anomalies: list[str] = []
    if (m.warnings_errors or 0) > 0:
        anomalies.append(f"{m.warnings_errors} warning/error event(s) reported by the log summary.")
    if (m.recovery_attempts or 0) > 0:
        anomalies.append(f"{m.recovery_attempts} recovery attempt(s) recorded.")
    if (m.recovery_failures or 0) > 0:
        anomalies.append(f"{m.recovery_failures} recovery failure(s) recorded.")
    if (m.interruptions or 0) > 0:
        anomalies.append(f"{m.interruptions} interruption event(s) recorded.")
    if (m.transcoding_errors or 0) > 0:
        anomalies.append(f"{m.transcoding_errors} transcoding error(s) recorded.")
    if (m.avqueue_failures or 0) > 0:
        anomalies.append(f"{m.avqueue_failures} AVQueue failure(s) recorded.")
    if parsed.repeated_event_patterns:
        anomalies.extend(parsed.repeated_event_patterns)
    if parsed.event_type_counts:
        top = ", ".join(f"{k}: {v}" for k, v in list(parsed.event_type_counts.items())[:5])
        anomalies.append(f"Top event categories: {top}.")
    return anomalies


def derive_tags(parsed: ParsedLog) -> list[str]:
    tags = {"needs-triage"}
    m    = parsed.metrics
    text = " ".join(parsed.error_lines + parsed.repeated_event_patterns + parsed.anomaly_flags).lower()

    if parsed.playback_mode and "crossfade" in parsed.playback_mode.lower():
        tags.add("crossfade")
    if "crossfade" in text or (m.crossfade_events or 0) > 0:
        tags.add("crossfade")
    if "gapless" in text:
        tags.add("gapless")
    if "transcod" in text or (m.transcoding_errors or 0) > 0:
        tags.add("transcoding")
    if "buffer" in text or (m.buffer_empty_events or 0) > 0:
        tags.add("buffering")
    if "avqueue" in text or (m.avqueue_failures or 0) > 0:
        tags.add("avqueue")
    if "scrobble" in text or (m.scrobble_failures or 0) > 0:
        tags.add("scrobbling")
    if (m.recovery_attempts or 0) > 0 or "recovery" in text:
        tags.add("recovery")
    if parsed.severity:
        tags.add(parsed.severity.lower())

    return sorted(tags)


def make_deterministic_summary(parsed: ParsedLog) -> str:
    m = parsed.metrics
    parts = [
        f"Narjo iOS log from {parsed.device or 'unknown device'}",
        f"iOS {parsed.ios_version or 'unknown'}",
        f"app {parsed.app_version or 'unknown'} build {parsed.build or 'unknown'}",
    ]
    platform = parsed.server_type or "unknown server"
    mode     = parsed.playback_mode or "unknown playback mode"
    headline = f"{', '.join(parts)} using {platform}; playback mode: {mode}."

    metrics = (
        f"Warnings/Errors: {m.warnings_errors if m.warnings_errors is not None else 'unknown'}, "
        f"Interruptions: {m.interruptions if m.interruptions is not None else 'unknown'}, "
        f"Recovery Attempts: {m.recovery_attempts if m.recovery_attempts is not None else 'unknown'}, "
        f"Recovery Failures: {m.recovery_failures if m.recovery_failures is not None else 'unknown'}, "
        f"Transcoding Errors: {m.transcoding_errors if m.transcoding_errors is not None else 'unknown'}."
    )

    anomaly = " ".join(parsed.anomaly_flags[:3]) if parsed.anomaly_flags else "No high-confidence anomaly detected."
    return f"{headline}\n{metrics}\n{anomaly}"


def parse_narjo_log(log_text: str, filename: str) -> ParsedLog:
    redacted_for_hash = redact_sensitive_data(log_text)
    parsed = ParsedLog(filename=filename, log_hash=make_hash(redacted_for_hash))

    parsed.generated_at            = _find_value(log_text, "Generated")
    parsed.device                  = _find_value(log_text, "Device")
    parsed.ios_version             = _find_value(log_text, "iOS Version")
    parsed.app_version             = _find_value(log_text, "App Version")
    parsed.build                   = _find_value(log_text, "Build")
    parsed.playback_mode           = _find_value(log_text, "Playback Mode")
    parsed.auto_resume_on_reconnect = _find_value(log_text, "Auto-Resume on Reconnect")
    parsed.server_type             = _find_value(log_text, "Server Type")
    parsed.scrobbling              = _find_value(log_text, "Scrobbling")

    m = parsed.metrics
    m.total_events           = _find_int(log_text, "Total Events")
    m.warnings_errors        = _find_int(log_text, "Warnings/Errors")
    m.transitions            = _find_int(log_text, "Transitions")
    m.crossfade_events       = _find_int(log_text, "Crossfade Events")
    m.pre_buffer_events      = _find_int(log_text, "Pre-Buffer Events")
    m.pre_cache_events       = _find_int(log_text, "Pre-Cache Events")
    m.desync_events          = _find_int(log_text, "Desync Events")
    m.transcoding_errors     = _find_int(log_text, "Transcoding Errors")
    m.interruptions          = _find_int(log_text, "Interruptions")
    m.recovery_attempts      = _find_int(log_text, "Recovery Attempts")
    m.recovery_failures      = _find_int(log_text, "Recovery Failures")
    m.avqueue_events         = _find_int(log_text, "AVQueue Events")
    m.avqueue_failures       = _find_int(log_text, "AVQueue Failures")
    m.stalls_detected        = _find_int(log_text, "Stalls Detected")
    m.buffer_empty_events    = _find_int(log_text, "Buffer Empty Events")
    m.seeks                  = _find_int(log_text, "Seeks")
    m.auto_recovery_attempts = _find_int(log_text, "Auto-Recovery Attempts")
    m.scrobble_events        = _find_int(log_text, "Scrobble Events")
    m.scrobble_successes     = _find_int(log_text, "Scrobble Successes")
    m.scrobble_failures      = _find_int(log_text, "Scrobble Failures")
    m.scrobbles_skipped      = _find_int(log_text, "Scrobbles Skipped")

    parsed.event_type_counts      = parse_event_counts(log_text)
    parsed.repeated_event_patterns = detect_repeated_patterns(log_text)
    parsed.error_lines            = extract_error_lines(log_text)
    parsed.anomaly_flags          = derive_anomalies(parsed)
    parsed.severity               = derive_severity(parsed)
    parsed.deterministic_summary  = make_deterministic_summary(parsed)
    parsed.suggested_tags         = derive_tags(parsed)

    return parsed


# =============================================================================
# DISCORD FORMATTERS — Log Analysis
# =============================================================================

def make_log_analysis_embed(parsed: ParsedLog, reporter: discord.abc.User) -> discord.Embed:
    color = {
        "Low":    discord.Color.green(),
        "Medium": discord.Color.orange(),
        "High":   discord.Color.red(),
    }.get(parsed.severity, discord.Color.blurple())

    embed = discord.Embed(
        title="📋 Log Analysis",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="Severity", value=parsed.severity, inline=True)
    embed.add_field(name="Log Hash", value=f"`{parsed.log_hash}`", inline=True)

    client_bits = [
        f"Device: `{parsed.device or 'Unknown'}`",
        f"iOS: `{parsed.ios_version or 'Unknown'}`",
        f"Narjo: `{parsed.app_version or 'Unknown'}`",
        f"Build: `{parsed.build or 'Unknown'}`",
    ]
    embed.add_field(name="Client", value="\n".join(client_bits), inline=False)

    playback_bits = [
        f"Mode: `{parsed.playback_mode or 'Unknown'}`",
        f"Auto-resume: `{parsed.auto_resume_on_reconnect or 'Unknown'}`",
        f"Server: `{parsed.server_type or 'Unknown'}`",
        f"Scrobbling: `{parsed.scrobbling or 'Unknown'}`",
    ]
    embed.add_field(name="Playback Context", value="\n".join(playback_bits), inline=False)

    m = parsed.metrics
    metrics = [
        f"Total Events: `{m.total_events if m.total_events is not None else 'Unknown'}`",
        f"Warnings/Errors: `{m.warnings_errors if m.warnings_errors is not None else 'Unknown'}`",
        f"Interruptions: `{m.interruptions if m.interruptions is not None else 'Unknown'}`",
        f"Recovery Attempts: `{m.recovery_attempts if m.recovery_attempts is not None else 'Unknown'}`",
        f"Recovery Failures: `{m.recovery_failures if m.recovery_failures is not None else 'Unknown'}`",
        f"Transcoding Errors: `{m.transcoding_errors if m.transcoding_errors is not None else 'Unknown'}`",
    ]
    embed.add_field(name="Key Metrics", value="\n".join(metrics), inline=False)

    anomalies = parsed.anomaly_flags[:8] or ["No deterministic anomaly found."]
    embed.add_field(
        name="Deterministic Findings",
        value="\n".join(f"• {x}" for x in anomalies)[:1024],
        inline=False,
    )

    if parsed.suggested_tags:
        embed.add_field(
            name="Suggested Tags",
            value=", ".join(f"`{x}`" for x in parsed.suggested_tags),
            inline=False,
        )

    embed.set_footer(text=f"Uploaded by {reporter} • file: {parsed.filename}")
    return embed


def make_error_snippet_message(parsed: ParsedLog) -> Optional[str]:
    if not parsed.error_lines:
        return None
    snippet = "\n".join(parsed.error_lines[:MAX_ERROR_LINES])
    return f"**High-signal log lines**\n```text\n{snippet[:1700]}\n```"


# =============================================================================
# GEMINI AI FUNCTIONS
# =============================================================================

class AIError(Exception):
    """Wraps a Gemini failure with a user-facing reason."""
    def __init__(self, message: str, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


def gemini_generate_sync(prompt: str) -> str:
    if genai is None:
        raise AIError("The `google-genai` package isn't installed on this host.")
    if not GOOGLE_AI_STUDIO_API_KEY or GOOGLE_AI_STUDIO_API_KEY.startswith("PASTE_"):
        raise AIError("`GOOGLE_AI_STUDIO_API_KEY` is not configured in `.env`.")
    try:
        client   = genai.Client(api_key=GOOGLE_AI_STUDIO_API_KEY)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text     = getattr(response, "text", None)
        if not text:
            raise AIError("The model returned an empty response.")
        return text.strip()
    except AIError:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("429", "resource_exhausted", "quota", "rate limit")):
            raise AIError("The AI model is currently rate-limited. Try again in a minute.", rate_limited=True)
        if any(k in msg for k in ("503", "unavailable", "overloaded")):
            raise AIError("The AI service is temporarily unavailable. Try again shortly.")
        if any(k in msg for k in ("deadline", "timeout")):
            raise AIError("The AI request timed out. The log may be too large — try again.")
        raise AIError(f"Unexpected AI error: {type(exc).__name__}: {exc}")


def build_modal_bug_ai_prompt(
    app_name: str,
    summary: str,
    steps: str,
    expected_vs_actual: str,
    version_platform: str,
) -> str:
    """AI prompt for a bug report submitted via the modal form (no log file)."""
    return textwrap.dedent(f"""
    You are assisting the developer of Narjo, a music player app for iOS.

    {NARJO_CONTEXT}

    Bug report submitted via form:
    App: {app_name} | Version/OS: {version_platform}
    Summary: {summary}
    Steps: {steps}
    Expected vs Actual: {expected_vs_actual}

    Reply using EXACTLY these four labelled sections, each on its own line:
    CAUSE: <most likely root cause based on the description>
    EVIDENCE: <what in the report supports that cause>
    FIX: <code area or behavior to inspect / likely fix>
    INSTRUMENTATION: <what extra log data would help next time>

    Each section: 1–3 sentences. No preamble, no markdown outside the labels.
    """).strip()


def build_log_ai_prompt(app_name: str, parsed: ParsedLog, redacted_log: str) -> str:
    """AI prompt for a log-based analysis via /submit-log."""
    compact = {
        "filename":               parsed.filename,
        "log_hash":               parsed.log_hash,
        "device":                 parsed.device,
        "ios_version":            parsed.ios_version,
        "app_version":            parsed.app_version,
        "build":                  parsed.build,
        "playback_mode":          parsed.playback_mode,
        "server_type":            parsed.server_type,
        "severity":               parsed.severity,
        "metrics":                parsed.metrics.__dict__,
        "deterministic_findings": parsed.anomaly_flags,
        "high_signal_lines":      parsed.error_lines,
    }
    return textwrap.dedent(f"""
    You are assisting the developer of Narjo.

    {NARJO_CONTEXT}

    Platform: {app_name}
    Parser output: {compact}

    Redacted log excerpt:
    ```text
    {redacted_log[:MAX_AI_INPUT_CHARS]}
    ```

    Reply using EXACTLY these four labelled sections, each on its own line:
    CAUSE: <probable root cause — treat parser output as source of truth>
    EVIDENCE: <specific log signals that support the cause>
    FIX: <recommended fix or code area to inspect>
    INSTRUMENTATION: <extra instrumentation that would improve the next report>

    Each section: 1–3 sentences. No preamble, no markdown outside the labels.
    """).strip()


def build_feature_ai_prompt(summary: str, problem: str, proposed: str, benefit: str) -> str:
    return textwrap.dedent(f"""
    You are helping refine a feature request for Narjo.

    {NARJO_CONTEXT}

    Summary: {summary}
    Problem: {problem}
    Proposed: {proposed}
    Benefit: {benefit}

    Reply using EXACTLY these three labelled sections, each on its own line:
    USER VALUE: <who benefits and how>
    BEHAVIOR: <suggested behavior and acceptance criteria>
    EDGE CASES: <implementation notes, edge cases, or risks>

    Each section: 1–3 sentences. No preamble, no markdown outside the labels.
    """).strip()


# Section labels that match the prompt instructions for each flow
_AI_BUG_SECTIONS  = ["CAUSE", "EVIDENCE", "FIX", "INSTRUMENTATION"]
_AI_FEAT_SECTIONS = ["USER VALUE", "BEHAVIOR", "EDGE CASES"]


def _parse_ai_sections(text: str, labels: list[str]) -> dict[str, str]:
    """
    Splits AI output into sections by looking for LABEL: lines.
    Falls back to returning the full text under a single 'Summary' key.
    """
    pattern = re.compile(
        r"(?:^|\n)(" + "|".join(re.escape(l) for l in labels) + r")\s*[:\-]\s*",
        re.IGNORECASE,
    )
    parts = pattern.split(text.strip())

    # parts = [pre-text, label, content, label, content, ...]
    if len(parts) < 3:
        return {"Summary": text.strip()}

    result: dict[str, str] = {}
    it = iter(parts[1:])  # skip any pre-amble
    for label, content in zip(it, it):
        result[label.strip().title()] = content.strip()
    return result


async def post_ai_comment(
    thread: discord.Thread,
    header: str,
    prompt: str,
    section_labels: list[str],
    embed_color: discord.Color = discord.Color.blurple(),
) -> None:
    try:
        raw = await asyncio.to_thread(gemini_generate_sync, prompt)
    except AIError as exc:
        emoji     = "⏳" if exc.rate_limited else "⚠️"
        err_embed = discord.Embed(
            title=f"{emoji} AI Comment Unavailable",
            description=str(exc),
            color=discord.Color.yellow() if exc.rate_limited else discord.Color.red(),
        )
        err_embed.set_footer(text="The report/log was still saved successfully.")
        await thread.send(embed=err_embed)
        return

    sections = _parse_ai_sections(raw, section_labels)

    embed = discord.Embed(title=header, color=embed_color)
    for name, value in sections.items():
        embed.add_field(name=name, value=value[:1024], inline=False)
    embed.set_footer(text="AI advisory — treat as a starting point, not a definitive diagnosis.")

    await thread.send(embed=embed)


# =============================================================================
# BUG REPORT — STATUS PANEL & MODAL
# =============================================================================

BUG_OP_MESSAGES = {
    "fixed":      "Your bug report has been marked as **Fixed**. 🎉 Thanks for the report!",
    "needs_info": "Your bug report needs more information. A maintainer has questions — please reply with additional details.",
    "wont_fix":   "Your bug report has been marked as **Won't Fix**. This issue won't be addressed at this time.",
    "unresolved": "Your bug report has been **reopened** and marked as Unresolved.",
}
BUG_STATUS_LABELS = {
    "fixed":      "Fixed",
    "needs_info": "Needs Info",
    "wont_fix":   "Won't Fix",
    "unresolved": "Unresolved",
}

def bug_status_color(status_key: str) -> discord.Color:
    return {
        "fixed":      discord.Color.green(),
        "needs_info": discord.Color.yellow(),
        "wont_fix":   discord.Color.red(),
        "unresolved": discord.Color.light_grey(),
    }.get(status_key, discord.Color.blurple())

def bug_status_emoji(status_key: str) -> str:
    return {
        "fixed":      "🟢",
        "needs_info": "🟡",
        "wont_fix":   "⛔",
        "unresolved": "🔴",
    }.get(status_key, "❓")

def build_bug_status_embed(
    label: str, status_key: str,
    actor: discord.Member, op: discord.Member | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="🐛 Bug Report Status",
        description=f"Status updated to **{label}** by {actor.mention}",
        color=bug_status_color(status_key),
    )
    embed.add_field(name="Status",       value=f"{bug_status_emoji(status_key)} {label}", inline=True)
    embed.add_field(name="Submitted by", value=op.mention if op else "Unknown",            inline=True)
    embed.set_footer(text="Mods: Fixed / Needs Info / Won't Fix  ·  Anyone: Reopen")
    return embed

def build_initial_bug_status_embed(op: discord.Member | None) -> discord.Embed:
    embed = discord.Embed(
        title="🐛 Bug Report Status",
        description="Moderators can use the buttons below to update the status of this report.",
        color=discord.Color.light_grey(),
    )
    embed.add_field(name="Status",       value="🔴 Unresolved",                 inline=True)
    embed.add_field(name="Submitted by", value=op.mention if op else "Unknown", inline=True)
    embed.set_footer(text="Mods: Fixed / Needs Info / Won't Fix  ·  Anyone: Reopen")
    return embed


class StatusPanel(discord.ui.View):
    """Persistent bug report status panel."""

    def __init__(self):
        super().__init__(timeout=None)

    def _is_mod(self, interaction: discord.Interaction) -> bool:
        role = interaction.guild.get_role(MOD_ROLE_ID)
        return role in interaction.user.roles if role else False

    async def _set_status(self, interaction: discord.Interaction, status_key: str):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("❌ This button only works inside a forum thread.", ephemeral=True)
            return

        if not is_bug_report_thread(thread):
            await interaction.response.send_message("❌ This thread isn't in the bug-report forum.", ephemeral=True)
            return

        forum          = thread.parent
        tag_name       = STATUS_TAG_NAMES.get(status_key, status_key.title())
        new_tag_obj    = find_tag_by_name(forum, tag_name)
        status_tag_ids = get_status_tag_ids_for_forum(forum, STATUS_TAG_NAMES)
        kept_tags      = [t for t in thread.applied_tags if t.id not in status_tag_ids]
        new_tags       = kept_tags + ([new_tag_obj] if new_tag_obj else [])
        await thread.edit(applied_tags=new_tags)

        if status_key == "unresolved" and (thread.archived or thread.locked):
            await thread.edit(archived=False, locked=False)

        label = BUG_STATUS_LABELS.get(status_key, status_key.title())
        op    = await get_reporter(thread)
        embed = build_bug_status_embed(label, status_key, interaction.user, op)
        await interaction.response.edit_message(embed=embed, view=self)

        op_msg = BUG_OP_MESSAGES.get(status_key, f"Your report status changed to **{label}**.")
        if op:
            await thread.send(f"{op.mention} — {op_msg}")

        if status_key == "fixed":
            await thread.edit(archived=True, locked=True)

    async def _mod_set_status(self, interaction: discord.Interaction, status_key: str):
        if not self._is_mod(interaction):
            await interaction.response.send_message("❌ Only moderators can use this button.", ephemeral=True)
            return
        await self._set_status(interaction, status_key)

    @discord.ui.button(label="✅ Fixed",      style=discord.ButtonStyle.success,   custom_id="narjo_status_fixed")
    async def btn_fixed(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "fixed")

    @discord.ui.button(label="💬 Needs Info", style=discord.ButtonStyle.primary,   custom_id="narjo_status_needs_info")
    async def btn_needs_info(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "needs_info")

    @discord.ui.button(label="⛔ Won't Fix",  style=discord.ButtonStyle.danger,    custom_id="narjo_status_wont_fix")
    async def btn_wont_fix(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "wont_fix")

    @discord.ui.button(label="🔁 Reopen",     style=discord.ButtonStyle.secondary, custom_id="narjo_status_reopen")
    async def btn_reopen(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._set_status(interaction, "unresolved")


class BugReportModal(discord.ui.Modal):
    def __init__(self, platform: str, category_tag_key: str | None):
        super().__init__(title="Report a Narjo Bug")
        self.platform         = platform
        self.category_tag_key = category_tag_key

        self.summary = discord.ui.TextInput(
            label="Summary",
            placeholder="Brief description of the bug (becomes the thread title)",
            min_length=10,
            max_length=100,
            required=True,
        )
        self.steps = discord.ui.TextInput(
            label="Steps to Reproduce",
            style=discord.TextStyle.paragraph,
            placeholder="1. Open the app\n2. Navigate to...\n3. ...",
            min_length=10,
            max_length=500,
            required=True,
        )
        self.expected_vs_actual = discord.ui.TextInput(
            label="Expected vs Actual Behavior",
            style=discord.TextStyle.paragraph,
            placeholder="Expected: ...\nActual: ...",
            min_length=10,
            max_length=500,
            required=True,
        )
        self.version_platform = discord.ui.TextInput(
            label="App Version & OS Version",
            placeholder=PLATFORM_HINT,
            max_length=100,
            required=True,
        )

        self.add_item(self.summary)
        self.add_item(self.steps)
        self.add_item(self.expected_vs_actual)
        self.add_item(self.version_platform)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        forum = interaction.guild.get_channel(BUG_REPORT_FORUM_ID)
        if not isinstance(forum, discord.ForumChannel):
            await interaction.followup.send("❌ Bug report forum not found. Please contact a moderator.", ephemeral=True)
            return

        color = PLATFORMS.get(self.platform, discord.Color.blurple())

        report_embed = discord.Embed(title=f"🐛 {self.summary.value}", color=color)
        report_embed.add_field(name="🎵 Music Platform",     value=self.platform,                 inline=True)
        report_embed.add_field(name="📱 Version & OS",       value=self.version_platform.value,   inline=True)
        report_embed.add_field(name="👤 Reported by",        value=interaction.user.mention,      inline=True)
        report_embed.add_field(name="📋 Steps to Reproduce", value=self.steps.value,              inline=False)
        report_embed.add_field(name="🔄 Expected vs Actual", value=self.expected_vs_actual.value, inline=False)
        report_embed.set_footer(
            text=f"Submitted via /bugreport · Reporter ID: {interaction.user.id}"
        )

        unresolved_tag    = find_tag_by_name(forum, STATUS_TAG_NAMES["unresolved"])
        platform_tag      = find_tag_by_name(forum, PLATFORM_TAG_NAMES.get(self.platform, ""))
        category_tag_name = CATEGORY_TAG_NAMES.get(self.category_tag_key) if self.category_tag_key else None
        category_tag      = find_tag_by_name(forum, category_tag_name) if category_tag_name else None
        initial_tags      = [t for t in (unresolved_tag, platform_tag, category_tag) if t]

        # Prefix thread title with platform shorthand for easy scanning
        platform_short = self.platform.split("/")[0].strip()
        thread_name    = f"[{platform_short}] {self.summary.value}"[:100]

        thread, _ = await forum.create_thread(
            name=thread_name,
            embed=report_embed,
            applied_tags=initial_tags[:5],
        )

        await thread.send(embed=build_initial_bug_status_embed(interaction.user), view=StatusPanel())

        await interaction.followup.send(
            f"✅ Report submitted! → {thread.mention}\n"
            "📎 **Have a debug log?** Use `/submit-log` in your new thread to upload it — "
            "it will be parsed and an AI recommendation will be posted automatically.\n"
            "Find logs at **Settings → More → Diagnostics**.\n"
            "You'll be pinged if a maintainer needs more info.",
            ephemeral=True,
        )

        # Post AI advisory comment based on the form fields (no log yet)
        if ENABLE_AI_RECOMMENDATION:
            try:
                prompt = build_modal_bug_ai_prompt(
                    app_name=self.platform,
                    summary=self.summary.value,
                    steps=self.steps.value,
                    expected_vs_actual=self.expected_vs_actual.value,
                    version_platform=self.version_platform.value,
                )
                await post_ai_comment(
                    thread, "🤖 AI Advisory",
                    prompt, _AI_BUG_SECTIONS,
                    embed_color=discord.Color.blurple(),
                )
            except Exception:
                await thread.send(
                    "**AI advisory comment failed**\n"
                    "The report was created successfully, but the AI comment encountered an error.\n"
                    f"```text\n{traceback.format_exc()[-1200:]}\n```"
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message("❌ Something went wrong. Please try again or ping a mod.", ephemeral=True)
        raise error


# =============================================================================
# FEATURE REQUEST — STATUS PANEL & MODAL
# =============================================================================

REQUEST_STATUS_LABELS = {
    "open":        "Open",
    "planned":     "Planned",
    "in_progress": "In Progress",
    "completed":   "Completed",
    "declined":    "Declined",
}
REQUEST_OP_MESSAGES = {
    "open":        "Your feature request has been **reopened** and is marked as Open.",
    "planned":     "Great news! Your feature request has been marked as **Planned** — it's on our roadmap. 🗺️",
    "in_progress": "Your feature request is now **In Progress** — we're actively working on it! 🔨",
    "completed":   "Your feature request has been marked as **Completed**. 🎉 Thanks for the suggestion!",
    "declined":    "Your feature request has been marked as **Declined**. It won't be pursued at this time.",
}

def req_status_color(status_key: str) -> discord.Color:
    return {
        "open":        discord.Color.light_grey(),
        "planned":     discord.Color.blue(),
        "in_progress": discord.Color.yellow(),
        "completed":   discord.Color.green(),
        "declined":    discord.Color.red(),
    }.get(status_key, discord.Color.blurple())

def req_status_emoji(status_key: str) -> str:
    return {
        "open":        "📬",
        "planned":     "🗺️",
        "in_progress": "🔨",
        "completed":   "🎉",
        "declined":    "⛔",
    }.get(status_key, "❓")

def build_req_status_embed(
    label: str, status_key: str,
    actor: discord.Member, op: discord.Member | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="💡 Feature Request Status",
        description=f"Status updated to **{label}** by {actor.mention}",
        color=req_status_color(status_key),
    )
    embed.add_field(name="Status",       value=f"{req_status_emoji(status_key)} {label}", inline=True)
    embed.add_field(name="Requested by", value=op.mention if op else "Unknown",            inline=True)
    embed.set_footer(text="Mods: Planned / In Progress / Completed / Declined  ·  Anyone: Reopen")
    return embed

def build_initial_req_status_embed(op: discord.Member | None) -> discord.Embed:
    embed = discord.Embed(
        title="💡 Feature Request Status",
        description="Moderators can use the buttons below to update the status of this request.",
        color=discord.Color.light_grey(),
    )
    embed.add_field(name="Status",       value="📬 Open",                        inline=True)
    embed.add_field(name="Requested by", value=op.mention if op else "Unknown",  inline=True)
    embed.set_footer(text="Mods: Planned / In Progress / Completed / Declined  ·  Anyone: Reopen")
    return embed


class FeatureRequestStatusPanel(discord.ui.View):
    """Persistent feature request status panel."""

    def __init__(self):
        super().__init__(timeout=None)

    def _is_mod(self, interaction: discord.Interaction) -> bool:
        role = interaction.guild.get_role(MOD_ROLE_ID)
        return role in interaction.user.roles if role else False

    async def _set_status(self, interaction: discord.Interaction, status_key: str):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("❌ This button only works inside a forum thread.", ephemeral=True)
            return

        if not thread.parent_id or thread.parent_id != FEATURE_REQUEST_FORUM_ID:
            await interaction.response.send_message("❌ This thread isn't in the feature request forum.", ephemeral=True)
            return

        forum          = thread.parent
        tag_name       = REQUEST_STATUS_TAG_NAMES.get(status_key, status_key.title())
        new_tag_obj    = find_tag_by_name(forum, tag_name)
        status_tag_ids = get_status_tag_ids_for_forum(forum, REQUEST_STATUS_TAG_NAMES)
        kept_tags      = [t for t in thread.applied_tags if t.id not in status_tag_ids]
        new_tags       = kept_tags + ([new_tag_obj] if new_tag_obj else [])
        await thread.edit(applied_tags=new_tags)

        if status_key == "open" and (thread.archived or thread.locked):
            await thread.edit(archived=False, locked=False)

        label = REQUEST_STATUS_LABELS.get(status_key, status_key.title())
        op    = await get_reporter(thread)
        embed = build_req_status_embed(label, status_key, interaction.user, op)
        await interaction.response.edit_message(embed=embed, view=self)

        op_msg = REQUEST_OP_MESSAGES.get(status_key, f"Your request status changed to **{label}**.")
        if op:
            await thread.send(f"{op.mention} — {op_msg}")

        if status_key in ("completed", "declined"):
            await thread.edit(archived=True, locked=True)

    async def _mod_set_status(self, interaction: discord.Interaction, status_key: str):
        if not self._is_mod(interaction):
            await interaction.response.send_message("❌ Only moderators can use this button.", ephemeral=True)
            return
        await self._set_status(interaction, status_key)

    @discord.ui.button(label="🗺️ Planned",     style=discord.ButtonStyle.primary,   custom_id="narjo_req_planned")
    async def btn_planned(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "planned")

    @discord.ui.button(label="🔨 In Progress", style=discord.ButtonStyle.primary,   custom_id="narjo_req_in_progress")
    async def btn_in_progress(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "in_progress")

    @discord.ui.button(label="🎉 Completed",   style=discord.ButtonStyle.success,   custom_id="narjo_req_completed")
    async def btn_completed(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "completed")

    @discord.ui.button(label="⛔ Declined",    style=discord.ButtonStyle.danger,    custom_id="narjo_req_declined")
    async def btn_declined(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._mod_set_status(interaction, "declined")

    @discord.ui.button(label="🔁 Reopen",      style=discord.ButtonStyle.secondary, custom_id="narjo_req_reopen")
    async def btn_reopen(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._set_status(interaction, "open")


class FeatureRequestModal(discord.ui.Modal, title="Submit a Feature Request"):
    def __init__(self, category_tag_key: str | None):
        super().__init__()
        self.category_tag_key = category_tag_key

    summary = discord.ui.TextInput(
        label="Summary",
        placeholder="One-line description of your feature (becomes the thread title)",
        min_length=10,
        max_length=100,
        required=True,
    )
    problem = discord.ui.TextInput(
        label="Problem / Use Case",
        style=discord.TextStyle.paragraph,
        placeholder="What problem does this solve? Describe your use case.",
        min_length=10,
        max_length=500,
        required=True,
    )
    proposed = discord.ui.TextInput(
        label="Proposed Feature",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what you'd like to see added or changed.",
        min_length=10,
        max_length=500,
        required=True,
    )
    benefit = discord.ui.TextInput(
        label="Why Would This Help?",
        style=discord.TextStyle.paragraph,
        placeholder="How would this improve the experience for you or others?",
        min_length=10,
        max_length=300,
        required=True,
    )
    extra = discord.ui.TextInput(
        label="Extra Context (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Screenshots, examples from other apps, related links, etc.",
        max_length=500,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        forum = interaction.guild.get_channel(FEATURE_REQUEST_FORUM_ID)
        if not isinstance(forum, discord.ForumChannel):
            await interaction.followup.send(
                "❌ Feature request forum not found. Please contact a moderator.",
                ephemeral=True,
            )
            return

        report_embed = discord.Embed(title=f"💡 {self.summary.value}", color=FEATURE_REQUEST_COLOR)
        report_embed.add_field(name="🔍 Problem / Use Case", value=self.problem.value,          inline=False)
        report_embed.add_field(name="✨ Proposed Feature",    value=self.proposed.value,         inline=False)
        report_embed.add_field(name="🎯 Why Would This Help", value=self.benefit.value,         inline=False)
        report_embed.add_field(name="👤 Requested by",        value=interaction.user.mention,   inline=True)
        if self.extra.value:
            report_embed.add_field(name="📎 Extra Context", value=self.extra.value, inline=False)
        report_embed.set_footer(text=f"Submitted via /request · Reporter ID: {interaction.user.id}")

        open_tag     = find_tag_by_name(forum, REQUEST_STATUS_TAG_NAMES["open"])
        cat_tag_name = REQUEST_CATEGORY_TAG_NAMES.get(self.category_tag_key) if self.category_tag_key else None
        category_tag = find_tag_by_name(forum, cat_tag_name) if cat_tag_name else None
        initial_tags = [t for t in (open_tag, category_tag) if t]

        thread, _ = await forum.create_thread(
            name=self.summary.value,
            embed=report_embed,
            applied_tags=initial_tags,
        )

        await thread.send(embed=build_initial_req_status_embed(interaction.user), view=FeatureRequestStatusPanel())

        await interaction.followup.send(
            f"✅ Feature request submitted! → {thread.mention}\n"
            "You'll be pinged in that thread if there's an update.",
            ephemeral=True,
        )

        # Post AI feature refinement comment
        if ENABLE_AI_FEATURE_REFINEMENT:
            try:
                prompt = build_feature_ai_prompt(
                    summary=self.summary.value,
                    problem=self.problem.value,
                    proposed=self.proposed.value,
                    benefit=self.benefit.value,
                )
                await post_ai_comment(
                    thread, "🤖 AI Feature Refinement",
                    prompt, _AI_FEAT_SECTIONS,
                    embed_color=FEATURE_REQUEST_COLOR,
                )
            except Exception:
                await thread.send(
                    "**AI feature refinement failed**\n"
                    "The feature request was created successfully, but the AI comment encountered an error.\n"
                    f"```text\n{traceback.format_exc()[-1200:]}\n```"
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            "❌ Something went wrong. Please try again or ping a mod.",
            ephemeral=True,
        )
        raise error


# =============================================================================
# BOT SETUP
# =============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =============================================================================
# EVENTS
# =============================================================================

@bot.event
async def on_ready():
    bot.add_view(StatusPanel())
    bot.add_view(FeatureRequestStatusPanel())
    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    print(f"✅ Narjo Bot online as {bot.user} (ID: {bot.user.id})")
    print(f"   Bug report forum: {BUG_REPORT_FORUM_ID}")
    print(f"   Feature request forum: {FEATURE_REQUEST_FORUM_ID}")
    print(f"   AI enabled: bug={ENABLE_AI_RECOMMENDATION}, log={ENABLE_AI_LOG_ANALYSIS}, feature={ENABLE_AI_FEATURE_REFINEMENT}")


@bot.event
async def on_thread_create(thread: discord.Thread):
    """Auto-tag and post the status panel for manually-created threads in bug report forums."""
    if thread.owner_id == bot.user.id:
        return  # already handled by modal submission

    if thread.parent_id != BUG_REPORT_FORUM_ID:
        return  # not a watched bug report forum

    forum          = thread.parent
    unresolved_tag = find_tag_by_name(forum, STATUS_TAG_NAMES["unresolved"])
    if unresolved_tag:
        current_tags = list(thread.applied_tags)
        if unresolved_tag not in current_tags:
            await thread.edit(applied_tags=current_tags + [unresolved_tag])

    await thread.send(embed=build_initial_bug_status_embed(thread.owner), view=StatusPanel())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Prevent user messages in bot-created pinned threads
    channel = message.channel
    if isinstance(channel, discord.Thread) and isinstance(channel.parent, discord.ForumChannel):
        if channel.owner_id == bot.user.id and channel.name.startswith(PINNED_THREAD_PREFIX):
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    await bot.process_commands(message)


# =============================================================================
# SLASH COMMANDS
# =============================================================================

@bot.tree.command(name="bugreport", description="Submit a Narjo bug report")
@app_commands.describe(
    platform="Which music server are you using?",
    category="Category of the bug (optional)",
)
@app_commands.choices(
    platform=[
        app_commands.Choice(name="Navidrome / OpenSubsonic", value="Navidrome / OpenSubsonic"),
        app_commands.Choice(name="Jellyfin",                 value="Jellyfin"),
        app_commands.Choice(name="Emby",                     value="Emby"),
        app_commands.Choice(name="Plex",                     value="Plex"),
    ],
    category=[
        app_commands.Choice(name="Other",          value="other"),
        app_commands.Choice(name="UI",             value="ui"),
        app_commands.Choice(name="Sync / Library", value="sync"),
        app_commands.Choice(name="Performance",    value="performance"),
        app_commands.Choice(name="Auth",           value="auth"),
    ]
)
async def bugreport(
    interaction: discord.Interaction,
    platform: app_commands.Choice[str],
    category: app_commands.Choice[str] | None = None,
):
    try:
        # Allow the command from inside the forum itself or any of its threads
        channel   = interaction.channel
        lookup_id = interaction.channel_id
        if hasattr(channel, "parent_id") and channel.parent_id:
            lookup_id = channel.parent_id

        if lookup_id != BUG_REPORT_FORUM_ID:
            await interaction.response.send_message(
                f"❌ Please use `/bugreport` inside <#{BUG_REPORT_FORUM_ID}>.",
                ephemeral=True,
            )
            return

        category_key = category.value if category else None
        await interaction.response.send_modal(
            BugReportModal(platform=platform.value, category_tag_key=category_key)
        )
    except Exception as e:
        print(f"[bugreport error] {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            await interaction.response.send_message(
                f"❌ Something went wrong (`{type(e).__name__}: {e}`). Please screenshot this and ping a mod.",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            pass


@bot.tree.command(name="request", description="Submit a feature request in the #feature-request channel")
@app_commands.choices(
    category=[
        app_commands.Choice(name="Other",          value="other"),
        app_commands.Choice(name="UI",             value="ui"),
        app_commands.Choice(name="Sync / Library", value="sync"),
        app_commands.Choice(name="Performance",    value="performance"),
        app_commands.Choice(name="Auth",           value="auth"),
    ]
)
async def request(interaction: discord.Interaction, category: app_commands.Choice[str] | None = None):
    try:
        lookup_id = interaction.channel_id

        if lookup_id != FEATURE_REQUEST_FORUM_ID:
            channel   = interaction.channel
            parent_id = getattr(channel, "parent_id", None)
            if parent_id:
                lookup_id = parent_id
            else:
                fetched   = await interaction.guild.fetch_channel(interaction.channel_id)
                parent_id = getattr(fetched, "parent_id", None)
                lookup_id = parent_id if parent_id else interaction.channel_id

        if lookup_id != FEATURE_REQUEST_FORUM_ID:
            channel_mention = f"<#{FEATURE_REQUEST_FORUM_ID}>" if FEATURE_REQUEST_FORUM_ID else "the #feature-request channel"
            await interaction.response.send_message(
                f"❌ Please use `/request` inside {channel_mention}.",
                ephemeral=True,
            )
            return

        category_key = category.value if category else None
        await interaction.response.send_modal(FeatureRequestModal(category_tag_key=category_key))

    except Exception as e:
        print(f"[request error] {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            await interaction.response.send_message(
                f"❌ Something went wrong (`{type(e).__name__}: {e}`). Please screenshot this and ping a mod.",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            pass


@bot.tree.command(
    name="submit-log",
    description="Upload a Narjo debug log (.txt) into your existing bug report thread for analysis.",
)
@app_commands.describe(
    log_file="Narjo playback/debug log exported from Settings → More → Diagnostics.",
)
async def submit_log(interaction: discord.Interaction, log_file: discord.Attachment) -> None:
    """
    Must be used inside an existing bug report thread.
    Parses the log, posts a structured analysis embed, high-signal error lines,
    and an AI advisory recommendation.
    """
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Verify we're inside a bug report thread
    thread = interaction.channel
    if not isinstance(thread, discord.Thread):
        await interaction.followup.send(
            "❌ Use `/submit-log` inside your bug report thread, not in a regular channel.",
            ephemeral=True,
        )
        return

    if not is_bug_report_thread(thread):
        await interaction.followup.send(
            "❌ This thread isn't in the bug-report forum. `/submit-log` only works inside bug report threads.",
            ephemeral=True,
        )
        return

    platform = await get_platform_for_thread(thread)

    # Only the original reporter or a mod can submit a log
    mod_role = interaction.guild.get_role(MOD_ROLE_ID) if MOD_ROLE_ID else None
    is_mod   = bool(mod_role and mod_role in interaction.user.roles)

    if not is_mod:
        reporter = await get_reporter(thread)
        if reporter is None or reporter.id != interaction.user.id:
            await interaction.followup.send(
                "❌ You can only use `/submit-log` in your own bug report thread.",
                ephemeral=True,
            )
            return

    # Validate the attachment
    if not log_file.filename.lower().endswith(".txt"):
        await interaction.followup.send("❌ Please upload a `.txt` Narjo debug log.", ephemeral=True)
        return

    if log_file.size and log_file.size > MAX_LOG_BYTES:
        await interaction.followup.send(
            f"❌ That log is too large (limit: {MAX_LOG_BYTES // 1_000_000} MB).",
            ephemeral=True,
        )
        return

    try:
        raw = await log_file.read()
    except Exception as exc:
        await interaction.followup.send(f"❌ Could not read the uploaded log: {exc}", ephemeral=True)
        return

    if len(raw) > MAX_LOG_BYTES:
        await interaction.followup.send(
            f"❌ That log is too large (limit: {MAX_LOG_BYTES // 1_000_000} MB).",
            ephemeral=True,
        )
        return

    log_text     = raw.decode("utf-8", errors="replace")
    redacted_log = redact_sensitive_data(log_text)
    parsed       = parse_narjo_log(redacted_log, log_file.filename)

    # Post analysis embed
    analysis_embed = make_log_analysis_embed(parsed, interaction.user)
    files: list[discord.File] = []

    if ATTACH_REDACTED_LOG_COPY:
        encoded = redacted_log.encode("utf-8", errors="replace")
        if len(encoded) <= MAX_REDACTED_ATTACHMENT_BYTES:
            files.append(
                discord.File(
                    fp=io.BytesIO(encoded),
                    filename=f"redacted-{log_file.filename}",
                )
            )

    await thread.send(
        content=f"📋 **Log uploaded by {interaction.user.mention}**",
        embed=analysis_embed,
        files=files or discord.utils.MISSING,
    )

    # Post high-signal error lines if any
    error_snippet = make_error_snippet_message(parsed)
    if error_snippet:
        await thread.send(error_snippet)

    await interaction.followup.send("✅ Log analysed — results posted in the thread.", ephemeral=True)

    # Post AI recommendation
    if ENABLE_AI_LOG_ANALYSIS:
        try:
            prompt = build_log_ai_prompt(platform, parsed, redacted_log)
            await post_ai_comment(
                thread, "🤖 AI Advisory (Log Analysis)",
                prompt, _AI_BUG_SECTIONS,
                embed_color=discord.Color.blurple(),
            )
        except Exception:
            await thread.send(
                "**AI advisory comment failed**\n"
                "The log was analysed successfully, but the AI comment encountered an error.\n"
                f"```text\n{traceback.format_exc()[-1200:]}\n```"
            )


# =============================================================================
# PREFIX UTILITY COMMANDS (mod-only)
# =============================================================================

@bot.command(name="pinbugreport")
@commands.has_permissions(manage_channels=True)
async def pinbugreport(ctx: commands.Context):
    """Run inside the bug report forum channel or a thread within it."""
    if isinstance(ctx.channel, discord.Thread) and isinstance(ctx.channel.parent, discord.ForumChannel):
        forum = ctx.channel.parent
    elif isinstance(ctx.channel, discord.ForumChannel):
        forum = ctx.channel
    else:
        await ctx.send("❌ Run this command inside the bug report forum channel or one of its threads.")
        return

    if forum.id != BUG_REPORT_FORUM_ID:
        await ctx.send("❌ This forum channel isn't the configured bug report forum. Check your `.env`.")
        return

    embed = discord.Embed(
        title="📌 How to Submit a Bug Report",
        description=(
            "Found a bug in Narjo? Use the `/bugreport` command right here in this channel "
            "to submit a structured report. It takes about a minute and helps maintainers "
            "reproduce and fix issues faster."
        ),
        color=discord.Color.red(),
    )
    embed.add_field(
        name="How to submit",
        value=(
            "1. Type `/bugreport` in this channel\n"
            "2. Choose your **music platform** and optional category\n"
            "3. Fill out the form that appears\n"
            "4. Hit Submit — a thread will be created automatically"
        ),
        inline=False,
    )
    embed.add_field(
        name="What to include",
        value=(
            "• **Steps to reproduce** — exactly what you did\n"
            "• **Expected vs actual behavior** — what should happen vs what did\n"
            f"• **Version & OS** — e.g. `{PLATFORM_HINT}`\n"
            "• **Debug logs** (optional) — after submitting, run `/submit-log` in your thread\n"
            "  (find logs at Settings → More → Diagnostics)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Supported platforms",
        value="\n".join(f"• {p}" for p in PLATFORMS),
        inline=False,
    )
    embed.add_field(
        name="Status tags",
        value=(
            "🔴 **Unresolved** — open, being looked at\n"
            "🟡 **Needs Info** — maintainer has questions, check your thread\n"
            "🟢 **Fixed** — resolved in a recent update\n"
            "⛔ **Won't Fix** — out of scope or can't reproduce\n\n"
            "🔁 You can **Reopen** a closed report if the bug comes back."
        ),
        inline=False,
    )
    embed.set_footer(text="Search existing posts before submitting to avoid duplicates.")

    thread, _ = await forum.create_thread(
        name=f"{PINNED_THREAD_PREFIX}Bug Report",
        embed=embed,
    )
    await thread.edit(pinned=True)
    await ctx.send(f"✅ Pinned post created: {thread.mention}", delete_after=10)


@bot.command(name="pinfeaturerequest")
@commands.has_permissions(manage_channels=True)
async def pinfeaturerequest(ctx: commands.Context):
    """Run inside the feature request forum channel or a thread within it."""
    if isinstance(ctx.channel, discord.Thread) and isinstance(ctx.channel.parent, discord.ForumChannel):
        forum = ctx.channel.parent
    elif isinstance(ctx.channel, discord.ForumChannel):
        forum = ctx.channel
    else:
        await ctx.send("❌ Run this command inside the feature request forum channel or one of its threads.")
        return

    if forum.id != FEATURE_REQUEST_FORUM_ID:
        await ctx.send("❌ This forum channel isn't the configured feature request forum. Check your `.env`.")
        return

    embed = discord.Embed(
        title="📌 How to Submit a Feature Request",
        description=(
            "Have an idea for Narjo? Use the `/request` command right here in this channel "
            "to submit a structured feature request. It only takes a minute!"
        ),
        color=FEATURE_REQUEST_COLOR,
    )
    embed.add_field(
        name="How to submit",
        value=(
            "1. Type `/request` in this channel\n"
            "2. Fill out the form that appears\n"
            "3. Hit Submit — a thread will be created automatically"
        ),
        inline=False,
    )
    embed.add_field(
        name="What to include",
        value=(
            "• **Problem / Use Case** — what problem does your idea solve?\n"
            "• **Proposed Feature** — describe what you'd like added or changed\n"
            "• **Why would this help?** — how would it improve things for you or others?\n"
            "• **Extra context** (optional) — examples, screenshots, links"
        ),
        inline=False,
    )
    embed.add_field(
        name="Status tags",
        value=(
            "📬 **Open** — received and under consideration\n"
            "🗺️ **Planned** — confirmed, on our roadmap\n"
            "🔨 **In Progress** — actively being built\n"
            "🎉 **Completed** — shipped in a recent update\n"
            "⛔ **Declined** — won't be pursued at this time\n"
            "🏷️ **Other** — general or uncategorized requests\n"
            "🧭 **UI** — interface or layout suggestions\n"
            "🔁 **Sync / Library** — sync, metadata, or library features\n"
            "⚡ **Performance** — speed, efficiency improvements\n"
            "🔐 **Auth** — login, account, or permissions features\n\n"
            "🔁 Declined requests can be **Reopened** if circumstances change."
        ),
        inline=False,
    )
    embed.set_footer(text="Search existing requests before submitting to avoid duplicates.")

    thread, _ = await forum.create_thread(
        name=f"{PINNED_THREAD_PREFIX}Feature Request",
        embed=embed,
    )
    await thread.edit(pinned=True)
    await ctx.send(f"✅ Pinned post created: {thread.mention}", delete_after=10)


@bot.command(name="listtags")
@commands.has_permissions(manage_channels=True)
async def listtags(ctx: commands.Context):
    """List all forum tags across every configured channel."""
    output = []

    bug_forum = bot.get_channel(BUG_REPORT_FORUM_ID)
    if isinstance(bug_forum, discord.ForumChannel):
        tags = [f"  `{t.id}` — {t.emoji or ''} {t.name}" for t in bug_forum.available_tags]
        output.append(f"**Bug Reports** (#{bug_forum.name}):\n" + ("\n".join(tags) if tags else "  (no tags)"))
    else:
        output.append(f"**Bug Reports:** ❌ not found (ID `{BUG_REPORT_FORUM_ID}`)")

    req_forum = bot.get_channel(FEATURE_REQUEST_FORUM_ID)
    if isinstance(req_forum, discord.ForumChannel):
        tags = [f"  `{t.id}` — {t.emoji or ''} {t.name}" for t in req_forum.available_tags]
        output.append(f"**Feature Requests** (#{req_forum.name}):\n" + ("\n".join(tags) if tags else "  (no tags)"))
    else:
        output.append(f"**Feature Requests:** ❌ not found (ID `{FEATURE_REQUEST_FORUM_ID}`)")

    await ctx.send("\n\n".join(output))


@bot.command(name="bugstatus")
@commands.has_permissions(manage_channels=True)
async def bugstatus(ctx: commands.Context):
    """Print the bot's current config summary."""
    req_tag_lines = ", ".join(REQUEST_STATUS_TAG_NAMES.values())
    await ctx.send(
        f"**Bug report forum:** `{BUG_REPORT_FORUM_ID}`\n\n"
        f"**Feature request forum:** `{FEATURE_REQUEST_FORUM_ID}`\n\n"
        f"**Mod role:** <@&{MOD_ROLE_ID}>\n\n"
        f"**AI recommendation (modal):** `{ENABLE_AI_RECOMMENDATION}`\n"
        f"**AI log analysis (/submit-log):** `{ENABLE_AI_LOG_ANALYSIS}`\n"
        f"**AI feature refinement:** `{ENABLE_AI_FEATURE_REFINEMENT}`\n\n"
        f"**Feature request status tags:** {req_tag_lines}"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set in your .env file.")
    bot.run(TOKEN)
