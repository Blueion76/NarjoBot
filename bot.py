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

# Per-app forum channel IDs + per-app status tag IDs
APPS = {
    "Navidrome": {
        "forum_id":      int(os.getenv("FORUM_NAVIDROME_ID", 0)),
        "color":         discord.Color.from_str("#FF8200"),
        "tags": {
            "unresolved": int(os.getenv("NAVIDROME_TAG_UNRESOLVED", 0)),
            "needs_info": int(os.getenv("NAVIDROME_TAG_NEEDS_INFO", 0)),
            "fixed":      int(os.getenv("NAVIDROME_TAG_FIXED", 0)),
            "wont_fix":   int(os.getenv("NAVIDROME_TAG_WONT_FIX", 0)),
            "other":      int(os.getenv("NAVIDROME_TAG_OTHER", 0)),
        },
    },
    "Plex": {
        "forum_id":      int(os.getenv("FORUM_PLEX_ID", 0)),
        "color":         discord.Color.from_str("#E5A00D"),
        "tags": {
            "unresolved": int(os.getenv("PLEX_TAG_UNRESOLVED", 0)),
            "needs_info": int(os.getenv("PLEX_TAG_NEEDS_INFO", 0)),
            "fixed":      int(os.getenv("PLEX_TAG_FIXED", 0)),
            "wont_fix":   int(os.getenv("PLEX_TAG_WONT_FIX", 0)),
            "other":      int(os.getenv("PLEX_TAG_OTHER", 0)),
        },
    },
    "Jellyfin": {
        "forum_id":      int(os.getenv("FORUM_JELLYFIN_ID", 0)),
        "color":         discord.Color.from_str("#00A4DC"),
        "tags": {
            "unresolved": int(os.getenv("JELLYFIN_TAG_UNRESOLVED", 0)),
            "needs_info": int(os.getenv("JELLYFIN_TAG_NEEDS_INFO", 0)),
            "fixed":      int(os.getenv("JELLYFIN_TAG_FIXED", 0)),
            "wont_fix":   int(os.getenv("JELLYFIN_TAG_WONT_FIX", 0)),
            "other":      int(os.getenv("JELLYFIN_TAG_OTHER", 0)),
        },
    },
    "Emby": {
        "forum_id":      int(os.getenv("FORUM_EMBY_ID", 0)),
        "color":         discord.Color.from_str("#52B54B"),
        "tags": {
            "unresolved": int(os.getenv("EMBY_TAG_UNRESOLVED", 0)),
            "needs_info": int(os.getenv("EMBY_TAG_NEEDS_INFO", 0)),
            "fixed":      int(os.getenv("EMBY_TAG_FIXED", 0)),
            "wont_fix":   int(os.getenv("EMBY_TAG_WONT_FIX", 0)),
            "other":      int(os.getenv("EMBY_TAG_OTHER", 0)),
        },
    },
}

# Reverse lookup: forum_channel_id → app name
FORUM_TO_APP = {cfg["forum_id"]: name for name, cfg in APPS.items() if cfg["forum_id"]}

# All forum IDs the bot should watch
ALL_FORUM_IDS = set(FORUM_TO_APP.keys())

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── Helpers ───────────────────────────────────────────────────────────────────
STATUS_KEYS = {"unresolved", "needs_info", "fixed", "wont_fix"}
PINNED_THREAD_PREFIX = "📌 How to Submit a "

OP_MESSAGES = {
    "fixed":      "Your bug report has been marked as **Fixed**. 🎉 Thanks for the report!",
    "needs_info": "Your bug report needs more information. A maintainer has questions — please reply with additional details.",
    "wont_fix":   "Your bug report has been marked as **Won't Fix**. This issue won't be addressed at this time.",
    "unresolved": "Your bug report has been **reopened** and marked as Unresolved.",
}

STATUS_LABELS = {
    "fixed": "Fixed",
    "needs_info": "Needs Info",
    "wont_fix": "Won't Fix",
    "unresolved": "Unresolved",
}

def status_color(status_key: str) -> discord.Color:
    return {
        "fixed":      discord.Color.green(),
        "needs_info": discord.Color.yellow(),
        "wont_fix":   discord.Color.red(),
        "unresolved": discord.Color.light_grey(),
    }.get(status_key, discord.Color.blurple())

def status_emoji(status_key: str) -> str:
    return {
        "fixed":      "🟢",
        "needs_info": "🟡",
        "wont_fix":   "⛔",
        "unresolved": "🔴",
    }.get(status_key, "❓")

def get_app_cfg_for_thread(thread: discord.Thread) -> dict | None:
    if not thread or not thread.parent_id:
        return None
    app_name = FORUM_TO_APP.get(thread.parent_id)
    if not app_name:
        return None
    return APPS.get(app_name)

def get_status_tag_ids_for_thread(thread: discord.Thread) -> set[int]:
    cfg = get_app_cfg_for_thread(thread)
    if not cfg:
        return set()
    return {cfg["tags"][k] for k in STATUS_KEYS if cfg["tags"].get(k)}

def build_status_embed(label: str, status_key: str, actor: discord.Member, op: discord.Member | None) -> discord.Embed:
    embed = discord.Embed(
        title="🐛 Bug Report Status",
        description=f"Status updated to **{label}** by {actor.mention}",
        color=status_color(status_key),
    )
    embed.add_field(name="Status",       value=f"{status_emoji(status_key)} {label}", inline=True)
    embed.add_field(name="Submitted by", value=op.mention if op else "Unknown",   inline=True)
    embed.set_footer(text="Mods: Fixed / Needs Info / Won't Fix  ·  Anyone: Reopen")
    return embed

def build_initial_status_embed(op: discord.Member | None) -> discord.Embed:
    embed = discord.Embed(
        title="🐛 Bug Report Status",
        description="Moderators can use the buttons below to update the status of this report.",
        color=discord.Color.light_grey(),
    )
    embed.add_field(name="Status",       value="🔴 Unresolved",                 inline=True)
    embed.add_field(name="Submitted by", value=op.mention if op else "Unknown", inline=True)
    embed.set_footer(text="Mods: Fixed / Needs Info / Won't Fix  ·  Anyone: Reopen")
    return embed

async def get_reporter(thread: discord.Thread) -> discord.Member | None:
    # If it's a manual thread, owner is likely the OP
    if thread.owner and thread.owner.id != bot.user.id:
        return thread.owner

    # For bot-created threads, parse the starter embed footer
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

# ── Status panel view (persistent across restarts) ────────────────────────────
class StatusPanel(discord.ui.View):
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
            await interaction.response.send_message("❌ This thread isn't in a configured forum.", ephemeral=True)
            return

        forum = thread.parent
        new_tag_id = cfg["tags"].get(status_key, 0)
        new_tag_obj = discord.utils.get(forum.available_tags, id=new_tag_id) if new_tag_id else None

        status_tag_ids = get_status_tag_ids_for_thread(thread)
        kept_tags = [t for t in thread.applied_tags if t.id not in status_tag_ids]
        new_tags = kept_tags + ([new_tag_obj] if new_tag_obj else [])
        await thread.edit(applied_tags=new_tags)

        if status_key == "unresolved" and (thread.archived or thread.locked):
            await thread.edit(archived=False, locked=False)

        label = STATUS_LABELS.get(status_key, status_key.title())
        op = await get_reporter(thread)
        embed = build_status_embed(label, status_key, interaction.user, op)
        await interaction.response.edit_message(embed=embed, view=self)

        op_msg = OP_MESSAGES.get(status_key, f"Your report status changed to **{label}**.")
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


# ── Bug report modal ──────────────────────────────────────────────────────────
class BugReportModal(discord.ui.Modal):
    def __init__(self, app_name: str, forum_channel_id: int, platform_hint: str, other_tag_id: int):
        super().__init__(title=f"Report a {app_name} Bug")
        self.app_name         = app_name
        self.forum_channel_id = forum_channel_id
        self.other_tag_id     = other_tag_id

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
            report_embed.add_field(name="📄 Debug Logs", value=f"```\n{self.debug_logs.value[:900]}\n```", inline=False)
        report_embed.set_footer(text=f"Submitted via /bugreport · {self.app_name} · Reporter ID: {interaction.user.id}")

        unresolved_tag_id = cfg["tags"].get("unresolved", 0)
        unresolved_tag = discord.utils.get(forum.available_tags, id=unresolved_tag_id) if unresolved_tag_id else None
        other_tag = discord.utils.get(forum.available_tags, id=self.other_tag_id) if self.other_tag_id else None

        initial_tags = [t for t in (unresolved_tag, other_tag) if t]

        thread, _ = await forum.create_thread(
            name=self.summary.value,
            embed=report_embed,
            applied_tags=initial_tags,
        )

        await thread.send(embed=build_initial_status_embed(interaction.user), view=StatusPanel())

        await interaction.followup.send(
            f"✅ Report submitted! → {thread.mention}\n"
            "You'll be pinged in that thread if a maintainer needs more info.",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message("❌ Something went wrong. Please try again or ping a mod.", ephemeral=True)
        raise error


# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    bot.add_view(StatusPanel())
    await bot.tree.sync()
    print(f"✅ Narjo Bug Bot online as {bot.user} (ID: {bot.user.id})")
    print(f"   Watching forum IDs: {ALL_FORUM_IDS}")

@bot.event
async def on_thread_create(thread: discord.Thread):
    """Handles threads posted manually in any configured forum channel."""
    if thread.parent_id not in ALL_FORUM_IDS:
        return
    if thread.owner_id == bot.user.id:
        return  # already handled by /bugreport submission

    cfg = get_app_cfg_for_thread(thread)
    if not cfg:
        return

    forum = thread.parent
    unresolved_tag_id = cfg["tags"].get("unresolved", 0)
    unresolved_tag = discord.utils.get(forum.available_tags, id=unresolved_tag_id) if unresolved_tag_id else None
    if unresolved_tag:
        current_tags = list(thread.applied_tags)
        if unresolved_tag not in current_tags:
            await thread.edit(applied_tags=current_tags + [unresolved_tag])

    await thread.send(embed=build_initial_status_embed(thread.owner), view=StatusPanel())

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
    tag=[
        app_commands.Choice(name="Other", value="other"),
    ]
)
async def bugreport(interaction: discord.Interaction, tag: app_commands.Choice[str] | None = None):
    try:
        # Resolve which forum channel this interaction belongs to.
        # Try in order: direct match → thread parent_id attr → guild thread fetch.
        lookup_id = interaction.channel_id

        if lookup_id not in FORUM_TO_APP:
            # Might be inside a thread — try cheap attribute access first
            channel = interaction.channel
            parent_id = getattr(channel, "parent_id", None)

            if parent_id:
                lookup_id = parent_id
            else:
                # Last resort: fetch the channel object from Discord
                fetched = await interaction.guild.fetch_channel(interaction.channel_id)
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

        cfg = APPS[app_name]
        other_tag_id = cfg["tags"].get("other", 0) if tag and tag.value == "other" else 0
        await interaction.response.send_modal(
            BugReportModal(
                app_name=app_name,
                forum_channel_id=cfg["forum_id"],
                platform_hint=PLATFORM_HINT,
                other_tag_id=other_tag_id,
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


# ── Prefix utility commands ───────────────────────────────────────────────────
@bot.command(name="pinbugreport")
@commands.has_permissions(manage_channels=True)
async def pinbugreport(ctx: commands.Context):
    """Run inside any configured forum channel or a thread within one."""
    # Climb up to the parent forum if run from inside a thread
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
            f"to submit a structured report. It takes about a minute and helps maintainers "
            f"reproduce and fix issues faster."
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
            "🏷️ **Other** — miscellaneous or uncategorized bug\n\n"
            "🔁 You can **Reopen** a closed report if the bug comes back."
        ),
        inline=False,
    )
    embed.set_footer(text="Search existing posts before submitting to avoid duplicates.")

    # Create the pinned thread — name starts with 📌 so it stands out
    thread, message = await forum.create_thread(
        name=f"{PINNED_THREAD_PREFIX}{app_name} Bug Report",
        embed=embed,
    )

    # Pin it so it stays at the top
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
    await ctx.send("\n\n".join(output) + "\n\nCopy the status tag IDs into your `.env` file.")

@bot.command(name="bugstatus")
@commands.has_permissions(manage_channels=True)
async def bugstatus(ctx: commands.Context):
    forum_lines = "\n".join(f"  **{k}:** `{v['forum_id']}`" for k, v in APPS.items())
    tag_lines = "\n".join([
        f"  {app}: unresolved={cfg['tags'].get('unresolved', 0)} needs_info={cfg['tags'].get('needs_info', 0)} fixed={cfg['tags'].get('fixed', 0)} wont_fix={cfg['tags'].get('wont_fix', 0)} other={cfg['tags'].get('other', 0)}"
        for app, cfg in APPS.items()
    ])
    await ctx.send(
        f"**Forum channels:**\n{forum_lines}\n\n"
        f"**Mod role:** <@&{MOD_ROLE_ID}>\n\n"
        f"**Status tags (per app):**\n{tag_lines}"
    )


bot.run(TOKEN)
