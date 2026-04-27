import discord
from discord import app_commands
from discord.ext import commands
import os
import re
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN       = os.getenv("DISCORD_TOKEN")
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))

# Universal platform hint for all apps
PLATFORM_HINT = os.getenv("PLATFORM_HINT", "Narjo 1.3(70) - iOS 26.4")

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

# Feature requests reuse the same category tags as bug reports
REQUEST_CATEGORY_TAG_NAMES = CATEGORY_TAG_NAMES

# ── Per-app bug forum channel IDs ─────────────────────────────────────────────
APPS = {
    "Navidrome": {
        "forum_id": int(os.getenv("FORUM_NAVIDROME_ID", 0)),
        "color":    discord.Color.from_str("#FF8200"),
    },
    "Plex": {
        "forum_id": int(os.getenv("FORUM_PLEX_ID", 0)),
        "color":    discord.Color.from_str("#E5A00D"),
    },
    "Jellyfin": {
        "forum_id": int(os.getenv("FORUM_JELLYFIN_ID", 0)),
        "color":    discord.Color.from_str("#00A4DC"),
    },
    "Emby": {
        "forum_id": int(os.getenv("FORUM_EMBY_ID", 0)),
        "color":    discord.Color.from_str("#52B54B"),
    },
}

# ── Shared feature request forum ──────────────────────────────────────────────
FEATURE_REQUEST_FORUM_ID = int(os.getenv("FORUM_FEATURE_REQUEST_ID", 0))
FEATURE_REQUEST_COLOR    = discord.Color.from_str("#5865F2")  # Discord blurple

# ── Lookups ───────────────────────────────────────────────────────────────────
FORUM_TO_APP    = {cfg["forum_id"]: name for name, cfg in APPS.items() if cfg["forum_id"]}
ALL_FORUM_IDS   = set(FORUM_TO_APP.keys())
ALL_WATCHED_IDS = ALL_FORUM_IDS | ({FEATURE_REQUEST_FORUM_ID} if FEATURE_REQUEST_FORUM_ID else set())

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── Shared helpers ────────────────────────────────────────────────────────────
PINNED_THREAD_PREFIX = "📌 How to Submit a "

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

def get_app_cfg_for_thread(thread: discord.Thread) -> dict | None:
    if not thread or not thread.parent_id:
        return None
    app_name = FORUM_TO_APP.get(thread.parent_id)
    if not app_name:
        return None
    return APPS.get(app_name)

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

# ═══════════════════════════════════════════════════════════════════════════════
# BUG REPORT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

BUG_STATUS_KEYS    = {"unresolved", "needs_info", "fixed", "wont_fix"}

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

        cfg = get_app_cfg_for_thread(thread)
        if not cfg:
            await interaction.response.send_message("❌ This thread isn't in a configured bug-report forum.", ephemeral=True)
            return

        forum = thread.parent
        tag_name    = STATUS_TAG_NAMES.get(status_key, status_key.title())
        new_tag_obj = find_tag_by_name(forum, tag_name)

        status_tag_ids = get_status_tag_ids_for_forum(forum, STATUS_TAG_NAMES)
        kept_tags = [t for t in thread.applied_tags if t.id not in status_tag_ids]
        new_tags  = kept_tags + ([new_tag_obj] if new_tag_obj else [])
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
    def __init__(self, app_name: str, forum_channel_id: int, platform_hint: str, category_tag_key: str | None):
        super().__init__(title=f"Report a {app_name} Bug")
        self.app_name         = app_name
        self.forum_channel_id = forum_channel_id
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
            placeholder=platform_hint,
            max_length=100,
            required=True,
        )
        self.debug_logs = discord.ui.TextInput(
            label="Logs (optional)",
            style=discord.TextStyle.paragraph,
            placeholder="Paste logs here. Find them at Settings → More → Diagnostics",
            max_length=1000,
            required=False,
        )

        self.add_item(self.summary)
        self.add_item(self.steps)
        self.add_item(self.expected_vs_actual)
        self.add_item(self.version_platform)
        self.add_item(self.debug_logs)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        forum = interaction.guild.get_channel(self.forum_channel_id)
        if not isinstance(forum, discord.ForumChannel):
            await interaction.followup.send("❌ Bug report forum not found. Please contact a moderator.", ephemeral=True)
            return

        cfg = APPS[self.app_name]

        report_embed = discord.Embed(title=f"🐛 {self.summary.value}", color=cfg["color"])
        report_embed.add_field(name="📋 Steps to Reproduce",  value=self.steps.value,              inline=False)
        report_embed.add_field(name="🔄 Expected vs Actual",  value=self.expected_vs_actual.value, inline=False)
        report_embed.add_field(name="📱 Version & Platform",  value=self.version_platform.value,   inline=True)
        report_embed.add_field(name="👤 Reported by",         value=interaction.user.mention,      inline=True)
        if self.debug_logs.value:
            report_embed.add_field(
                name="📄 Debug Logs",
                value=f"```\n{self.debug_logs.value[:900]}\n```",
                inline=False,
            )
        report_embed.set_footer(text=f"Submitted via /bugreport · {self.app_name} · Reporter ID: {interaction.user.id}")

        unresolved_tag  = find_tag_by_name(forum, STATUS_TAG_NAMES["unresolved"])
        category_tag_name = CATEGORY_TAG_NAMES.get(self.category_tag_key) if self.category_tag_key else None
        category_tag    = find_tag_by_name(forum, category_tag_name) if category_tag_name else None
        initial_tags    = [t for t in (unresolved_tag, category_tag) if t]

        thread, _ = await forum.create_thread(
            name=self.summary.value,
            embed=report_embed,
            applied_tags=initial_tags,
        )

        await thread.send(embed=build_initial_bug_status_embed(interaction.user), view=StatusPanel())

        await interaction.followup.send(
            f"✅ Report submitted! → {thread.mention}\n"
            "You'll be pinged in that thread if a maintainer needs more info.",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message("❌ Something went wrong. Please try again or ping a mod.", ephemeral=True)
        raise error


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE REQUEST SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

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
    embed.add_field(name="Status",        value=f"{req_status_emoji(status_key)} {label}", inline=True)
    embed.add_field(name="Requested by",  value=op.mention if op else "Unknown",            inline=True)
    embed.set_footer(text="Mods: Planned / In Progress / Completed / Declined  ·  Anyone: Reopen")
    return embed

def build_initial_req_status_embed(op: discord.Member | None) -> discord.Embed:
    embed = discord.Embed(
        title="💡 Feature Request Status",
        description="Moderators can use the buttons below to update the status of this request.",
        color=discord.Color.light_grey(),
    )
    embed.add_field(name="Status",       value="📬 Open",                          inline=True)
    embed.add_field(name="Requested by", value=op.mention if op else "Unknown",    inline=True)
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

        forum       = thread.parent
        tag_name    = REQUEST_STATUS_TAG_NAMES.get(status_key, status_key.title())
        new_tag_obj = find_tag_by_name(forum, tag_name)

        status_tag_ids = get_status_tag_ids_for_forum(forum, REQUEST_STATUS_TAG_NAMES)
        kept_tags = [t for t in thread.applied_tags if t.id not in status_tag_ids]
        new_tags  = kept_tags + ([new_tag_obj] if new_tag_obj else [])
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

        report_embed = discord.Embed(
            title=f"💡 {self.summary.value}",
            color=FEATURE_REQUEST_COLOR,
        )
        report_embed.add_field(name="🔍 Problem / Use Case",  value=self.problem.value,  inline=False)
        report_embed.add_field(name="✨ Proposed Feature",     value=self.proposed.value, inline=False)
        report_embed.add_field(name="🎯 Why Would This Help", value=self.benefit.value,  inline=False)
        report_embed.add_field(name="👤 Requested by",        value=interaction.user.mention, inline=True)
        if self.extra.value:
            report_embed.add_field(name="📎 Extra Context", value=self.extra.value, inline=False)
        report_embed.set_footer(text=f"Submitted via /request · Reporter ID: {interaction.user.id}")

        open_tag      = find_tag_by_name(forum, REQUEST_STATUS_TAG_NAMES["open"])
        cat_tag_name  = REQUEST_CATEGORY_TAG_NAMES.get(self.category_tag_key) if self.category_tag_key else None
        category_tag  = find_tag_by_name(forum, cat_tag_name) if cat_tag_name else None
        initial_tags  = [t for t in (open_tag, category_tag) if t]

        thread, _ = await forum.create_thread(
            name=self.summary.value,
            embed=report_embed,
            applied_tags=initial_tags,
        )

        await thread.send(
            embed=build_initial_req_status_embed(interaction.user),
            view=FeatureRequestStatusPanel(),
        )

        await interaction.followup.send(
            f"✅ Feature request submitted! → {thread.mention}\n"
            "You'll be pinged in that thread if there's an update.",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            "❌ Something went wrong. Please try again or ping a mod.",
            ephemeral=True,
        )
        raise error


# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    bot.add_view(StatusPanel())
    bot.add_view(FeatureRequestStatusPanel())
    await bot.tree.sync()
    print(f"✅ Narjo Bot online as {bot.user} (ID: {bot.user.id})")
    print(f"   Watching bug forums: {ALL_FORUM_IDS}")
    print(f"   Feature request forum: {FEATURE_REQUEST_FORUM_ID}")

@bot.event
async def on_thread_create(thread: discord.Thread):
    """Auto-tag and post the status panel for manually-created threads."""
    if thread.owner_id == bot.user.id:
        return  # already handled by modal submission

    # Bug report forums
    if thread.parent_id in ALL_FORUM_IDS:
        forum = thread.parent
        unresolved_tag = find_tag_by_name(forum, STATUS_TAG_NAMES["unresolved"])
        if unresolved_tag:
            current_tags = list(thread.applied_tags)
            if unresolved_tag not in current_tags:
                await thread.edit(applied_tags=current_tags + [unresolved_tag])
        await thread.send(
            embed=build_initial_bug_status_embed(thread.owner),
            view=StatusPanel(),
        )
        return

    # Feature request forum
    if FEATURE_REQUEST_FORUM_ID and thread.parent_id == FEATURE_REQUEST_FORUM_ID:
        forum    = thread.parent
        open_tag = find_tag_by_name(forum, REQUEST_STATUS_TAG_NAMES["open"])
        if open_tag:
            current_tags = list(thread.applied_tags)
            if open_tag not in current_tags:
                await thread.edit(applied_tags=current_tags + [open_tag])
        await thread.send(
            embed=build_initial_req_status_embed(thread.owner),
            view=FeatureRequestStatusPanel(),
        )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel = message.channel
    if isinstance(channel, discord.Thread) and isinstance(channel.parent, discord.ForumChannel):
        if channel.owner_id == bot.user.id and channel.name.startswith(PINNED_THREAD_PREFIX):
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    await bot.process_commands(message)


# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="bugreport", description="Submit a bug report for this channel's app")
@app_commands.choices(
    category=[
        app_commands.Choice(name="Other",          value="other"),
        app_commands.Choice(name="UI",              value="ui"),
        app_commands.Choice(name="Sync / Library",  value="sync"),
        app_commands.Choice(name="Performance",     value="performance"),
        app_commands.Choice(name="Auth",            value="auth"),
    ]
)
async def bugreport(interaction: discord.Interaction, category: app_commands.Choice[str] | None = None):
    try:
        lookup_id = interaction.channel_id

        if lookup_id not in FORUM_TO_APP:
            channel   = interaction.channel
            parent_id = getattr(channel, "parent_id", None)
            if parent_id:
                lookup_id = parent_id
            else:
                fetched   = await interaction.guild.fetch_channel(interaction.channel_id)
                parent_id = getattr(fetched, "parent_id", None)
                lookup_id = parent_id if parent_id else interaction.channel_id

        app_name = FORUM_TO_APP.get(lookup_id)
        if not app_name:
            forum_mentions = ", ".join(
                f"<#{cfg['forum_id']}>" for cfg in APPS.values() if cfg["forum_id"]
            )
            await interaction.response.send_message(
                f"❌ Please use `/bugreport` inside one of the bug report forum channels:\n{forum_mentions}",
                ephemeral=True,
            )
            return

        cfg          = APPS[app_name]
        category_key = category.value if category else None
        await interaction.response.send_modal(
            BugReportModal(
                app_name=app_name,
                forum_channel_id=cfg["forum_id"],
                platform_hint=PLATFORM_HINT,
                category_tag_key=category_key,
            )
        )
    except Exception as e:
        import traceback
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
        app_commands.Choice(name="UI",              value="ui"),
        app_commands.Choice(name="Sync / Library",  value="sync"),
        app_commands.Choice(name="Performance",     value="performance"),
        app_commands.Choice(name="Auth",            value="auth"),
    ]
)
async def request(interaction: discord.Interaction, category: app_commands.Choice[str] | None = None):
    try:
        # Resolve the channel/thread we're in
        lookup_id = interaction.channel_id
        channel   = interaction.channel
        parent_id = getattr(channel, "parent_id", None)
        if parent_id:
            lookup_id = parent_id

        if lookup_id != FEATURE_REQUEST_FORUM_ID:
            # Try fetching in case we got a thread inside a different channel
            if not parent_id:
                try:
                    fetched   = await interaction.guild.fetch_channel(interaction.channel_id)
                    parent_id = getattr(fetched, "parent_id", None)
                    lookup_id = parent_id if parent_id else interaction.channel_id
                except Exception:
                    pass

        if lookup_id != FEATURE_REQUEST_FORUM_ID:
            channel_mention = f"<#{FEATURE_REQUEST_FORUM_ID}>" if FEATURE_REQUEST_FORUM_ID else "the #feature-request channel"
            await interaction.response.send_message(
                f"❌ Please use `/request` inside {channel_mention}.",
                ephemeral=True,
            )
            return

        category_key = category.value if category else None
        modal        = FeatureRequestModal(category_tag_key=category_key)
        await interaction.response.send_modal(modal)

    except Exception as e:
        import traceback
        print(f"[request error] {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            await interaction.response.send_message(
                f"❌ Something went wrong (`{type(e).__name__}: {e}`). Please screenshot this and ping a mod.",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            pass


# ── Prefix utility commands ───────────────────────────────────────────────────
@bot.command(name="pinbugreport")
@commands.has_permissions(manage_channels=True)
async def pinbugreport(ctx: commands.Context):
    """Run inside any configured bug-report forum channel or a thread within one."""
    if isinstance(ctx.channel, discord.Thread) and isinstance(ctx.channel.parent, discord.ForumChannel):
        forum = ctx.channel.parent
    elif isinstance(ctx.channel, discord.ForumChannel):
        forum = ctx.channel
    else:
        await ctx.send("❌ Run this command inside a forum channel or one of its threads.")
        return

    app_name = FORUM_TO_APP.get(forum.id)
    if not app_name:
        await ctx.send("❌ This forum channel isn't configured in the bot. Check your `.env`.")
        return

    cfg = APPS[app_name]

    embed = discord.Embed(
        title=f"📌 How to Submit a {app_name} Bug Report",
        description=(
            f"Found a bug in {app_name}? Use the `/bugreport` command right here in this channel "
            "to submit a structured report. It takes about a minute and helps maintainers "
            "reproduce and fix issues faster."
        ),
        color=cfg["color"],
    )
    embed.add_field(
        name="How to submit",
        value=(
            "1. Type `/bugreport` in this channel\n"
            "2. Fill out the form that appears\n"
            "3. Hit Submit — a thread will be created automatically"
        ),
        inline=False,
    )
    embed.add_field(
        name="What to include",
        value=(
            "• **Steps to reproduce** — exactly what you did\n"
            "• **Expected vs actual behavior** — what should happen vs what did\n"
            f"• **Version & platform** — e.g. `{PLATFORM_HINT}`\n"
            "• **Debug logs** (optional) — Settings → More → Diagnostics"
        ),
        inline=False,
    )
    embed.add_field(
        name="Status tags",
        value=(
            "🔴 **Unresolved** — open, being looked at\n"
            "🟡 **Needs Info** — maintainer has questions, check your thread\n"
            "🟢 **Fixed** — resolved in a recent update\n"
            "⛔ **Won't Fix** — out of scope or can't reproduce\n"
            "🏷️ **Other** — miscellaneous or uncategorized bug\n"
            "🧭 **UI** — interface or layout issues\n"
            "🔁 **Sync / Library** — sync, metadata, or library scans\n"
            "⚡ **Performance** — slowdowns, stalls, high resource usage\n"
            "🔐 **Auth** — login, permissions, or token issues\n\n"
            "🔁 You can **Reopen** a closed report if the bug comes back."
        ),
        inline=False,
    )
    embed.set_footer(text="Search existing posts before submitting to avoid duplicates.")

    thread, _ = await forum.create_thread(
        name=f"{PINNED_THREAD_PREFIX}{app_name} Bug Report",
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
    output = []
    for app_name, cfg in APPS.items():
        forum = bot.get_channel(cfg["forum_id"])
        if not isinstance(forum, discord.ForumChannel):
            output.append(f"**{app_name}:** ❌ not found (ID `{cfg['forum_id']}`)")
            continue
        tags = [f"  `{t.id}` — {t.emoji or ''} {t.name}" for t in forum.available_tags]
        output.append(f"**{app_name}** (#{forum.name}):\n" + ("\n".join(tags) if tags else "  (no tags)"))

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
    forum_lines = "\n".join(f"  **{k}:** `{v['forum_id']}`" for k, v in APPS.items())
    tag_lines   = "\n".join([
        f"  {app}: status={', '.join(STATUS_TAG_NAMES.values())} categories={', '.join(CATEGORY_TAG_NAMES.values())}"
        for app in APPS.keys()
    ])
    req_tag_lines = ", ".join(REQUEST_STATUS_TAG_NAMES.values())
    await ctx.send(
        f"**Bug report forums:**\n{forum_lines}\n\n"
        f"**Feature request forum:** `{FEATURE_REQUEST_FORUM_ID}`\n\n"
        f"**Mod role:** <@&{MOD_ROLE_ID}>\n\n"
        f"**Bug status tags:** {tag_lines}\n\n"
        f"**Feature request status tags:** {req_tag_lines}"
    )


bot.run(TOKEN)
