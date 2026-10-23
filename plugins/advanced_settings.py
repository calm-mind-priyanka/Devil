import asyncio
import html
import re
import requests
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import *
from utils import (
    get_settings,
    save_group_settings,
    is_check_admin,
    get_readable_time,
    save_default_settings,
)
from database.users_chats_db import db
from database.config_db import mdb


# ============================================================
# PER-USER PENDING INPUT
# ============================================================

PENDING = {}  # Keys are (user_id, group_id)

# Fast in-process caches for settings navigation. Changes invalidate the cache.
_AUTH_CACHE = {}
_SETTINGS_CACHE = {}
_AUTH_TTL = 15.0
_SETTINGS_TTL = 1.5


def _is_bot_owner(user_id):
    """Global Premium-plan owner check; separate from group-admin permissions."""
    try:
        return int(user_id) == int(OWNER_ID)
    except (TypeError, ValueError, NameError):
        return False


def _invalidate_settings_cache(gid):
    _SETTINGS_CACHE.pop(int(gid), None)

async def _fast_settings(gid):
    gid = int(gid)
    now = asyncio.get_running_loop().time()
    item = _SETTINGS_CACHE.get(gid)
    if item and now - item[0] < _SETTINGS_TTL:
        return item[1]
    value = await get_settings(gid)
    _SETTINGS_CACHE[gid] = (now, value)
    return value



# ============================================================
# UI HELPERS
# ============================================================

def _small(text):
    """Return the UI text in the small-cap style used by the advanced menu."""
    table = str.maketrans({
        "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ",
        "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ",
        "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ",
        "S": "s", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
        "Y": "ʏ", "Z": "ᴢ",
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
        "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
        "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
        "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
        "y": "ʏ", "z": "ᴢ",
    })
    return str(text).translate(table)


def _cancel_link():
    """Return /cancel as a native Telegram bot-command link."""
    # Keep this as plain /cancel text. Telegram automatically makes a
    # registered bot command clickable and tapping it sends /cancel.
    return "/cancel"


def _cancel_prompt(text):
    """Append the clickable /cancel command to an input prompt."""
    return f"{text}\n\n{_cancel_link()} - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss."


def _back(group_id, page="main"):
    return [
        InlineKeyboardButton(
            "≪ ʙᴀᴄᴋ",
            callback_data=f"set_back#{page}#{group_id}"
        )
    ]


def _back_markup(group_id, page):
    return InlineKeyboardMarkup([
        _back(group_id, page)
    ])


async def _group_title(client, group_id):
    try:
        chat = await client.get_chat(int(group_id))
        return chat.title or str(group_id)
    except Exception:
        return str(group_id)


# ============================================================
# MAIN SETTINGS MENU
# ============================================================

def _main_settings_buttons(settings, grp_id, include_premium=False):

    def onoff(key):
        return "ON ✅" if settings.get(key) else "OFF ❌"

    buttons = [
        [
            InlineKeyboardButton(
                f"📝 ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ",
                callback_data=f"set_page#auto_filter#{grp_id}"
            ),
            InlineKeyboardButton(
                f"🔒 ꜰɪʟᴇ sᴇᴄᴜʀᴇ",
                callback_data=f"set_page#file_secure#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"🈵 ɪᴍᴅʙ",
                callback_data=f"set_page#imdb#{grp_id}"
            ),
            InlineKeyboardButton(
                f"🔍 sᴘᴇʟʟ ᴄʜᴇᴄᴋ",
                callback_data=f"set_page#spell_check#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"🗑️ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ",
                callback_data=f"set_page#auto_delete#{grp_id}"
            ),
            InlineKeyboardButton(
                f"📚 ʀᴇsᴜʟᴛ ᴍᴏᴅᴇ",
                callback_data=f"set_page#link#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"🗂 ꜰɪʟᴇ ᴍᴏᴅᴇ · {'ꜰɪʟᴇ 🗂 ' if settings.get('file_mode') else 'ᴠᴇʀɪғʏ ♻️'}",
                callback_data=f"set_page#file_mode#{grp_id}"
            ),
            InlineKeyboardButton(
                "📑 ꜰɪʟᴇs ᴄᴀᴘᴛɪᴏɴs",
                callback_data=f"set_page#caption#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🥁 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ",
                callback_data=f"set_page#tutorial#{grp_id}"
            ),
            InlineKeyboardButton(
                "🖇️ sᴇᴛ sʜᴏʀᴛʟɪɴᴋ",
                callback_data=f"set_page#shortlink#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 sᴇᴛ ᴍᴏᴠɪᴇ ʀᴇǫ",
                callback_data=f"set_page#request_channel#{grp_id}"
            ),
            InlineKeyboardButton(
                "ℹ️ ᴅᴇᴛᴀɪʟs",
                callback_data=f"set_page#details#{grp_id}"
            )
        ],
        [InlineKeyboardButton(
            f"📣 ɢʀᴏᴜᴘ ꜰsᴜʙ: {'ON ✅' if settings.get('fsub_enabled') else 'OFF ❌'}",
            callback_data=f"set_toggle#fsub_enabled#{grp_id}"
        )],
        [InlineKeyboardButton("⚙️ NEW 3-STEP SETTINGS", callback_data=f"set_page#new_shortener#{grp_id}")],
        [
            InlineKeyboardButton(
                "👥 ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ",
                callback_data=f"set_page#fsub#{grp_id}"
            ),
            InlineKeyboardButton(
                f"ℹ️ ꜱᴇᴛ ᴍᴀx ʀᴇꜱᴜʟᴛꜱ · {settings.get('max_results', MAX_BTN)}",
                callback_data=f"set_page#max_results#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "‼️ ᴄʟᴏsᴇ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ ‼️",
                callback_data=f"set_close#{grp_id}"
            )
        ],
    ]
    if include_premium:
        buttons.insert(0, [InlineKeyboardButton("💎 ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ sᴇᴛᴛɪɴɢs", callback_data=f"premium_settings#{grp_id}")])
    return buttons


# ============================================================
# GROUP LIST & SETTINGS
# ============================================================

async def _global_payment_mode_button(group_id=None):
    from plugins.premium_payments import get_auto_payment_enabled
    enabled = await get_auto_payment_enabled()
    state = "ON ✅" if enabled else "OFF ❌"
    callback = "global_payment_mode#toggle"
    if group_id is not None:
        callback += f"#{int(group_id)}"
    return InlineKeyboardButton(f"💳 GLOBAL AUTO PAYMENT: {state}", callback_data=callback)


async def show_group_list(client, target, direct_group_id=None):
    user_id = target.from_user.id
    groups = []

    async for chat in await db.get_all_chats():
        gid = chat.get("id")
        if not gid:
            continue

        try:
            member = await client.get_chat_member(int(gid), user_id)
            if member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
                title = chat.get("title") or str(gid)
                groups.append((int(gid), title))
        except Exception:
            continue

    if direct_group_id is not None:
        try:
            gid = int(direct_group_id)
            if any(g[0] == gid for g in groups):
                return await show_group_settings(client, target, gid)
        except Exception:
            pass

    if not groups:
        if _is_bot_owner(user_id):
            payment_button = await _global_payment_mode_button()
            markup = InlineKeyboardMarkup([
                [payment_button],
                [InlineKeyboardButton("💎 ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ sᴇᴛᴛɪɴɢs", callback_data="premium_settings#0")],
            ])
            text = "❌ <b>ɴᴏ ɢʀᴏᴜᴘs ᴀᴠᴀɪʟᴀʙʟᴇ.</b>\n\nᴍᴀɴᴀɢᴇ ɢʟᴏʙᴀʟ ᴀᴜᴛᴏ-ᴘᴀʏᴍᴇɴᴛ ᴀɴᴅ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs ʙᴇʟᴏᴡ."
            if target.chat.type == enums.ChatType.PRIVATE:
                return await target.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
            return await target.message.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        text = "❌ <b>ɪ ᴄᴏᴜʟᴅ ɴᴏᴛ ғɪɴᴅ ᴀɴʏ ɢʀᴏᴜᴘs ᴡʜᴇʀᴇ ʏᴏᴜ ᴀʀᴇ ᴀɴ ᴀᴅᴍɪɴ.</b>"
        if target.chat.type == enums.ChatType.PRIVATE:
            return await target.reply_text(text)
        return await target.message.reply_text(text)

    buttons = [
        [InlineKeyboardButton(f"{title} · {gid}", callback_data=f"set_group#{gid}")]
        for gid, title in groups
    ]
    if _is_bot_owner(user_id):
        buttons.insert(0, [InlineKeyboardButton("💎 ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ sᴇᴛᴛɪɴɢs", callback_data="premium_settings#0")])
        buttons.insert(0, [await _global_payment_mode_button()])
    markup = InlineKeyboardMarkup(buttons)
    text = "⚙️ <b>ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ɢʀᴏᴜᴘ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴍᴀɴᴀɢᴇ:</b>"

    if target.chat.type == enums.ChatType.PRIVATE:
        return await target.reply_text(text, reply_markup=markup)
    return await target.message.reply_text(text, reply_markup=markup)


async def show_group_settings(client, target, grp_id):
    user_id = target.from_user.id

    if not await is_check_admin(client, int(grp_id), user_id):
        if hasattr(target, "answer"):
            return await target.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
        return await target.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.</b>")

    settings = await _fast_settings(int(grp_id))
    title = await _group_title(client, grp_id)

    text = (
        f"🚸 <b>ɢʀᴏᴜᴘ - {title}</b>\n"
        f"🆔️ <b>ɪᴅ - <code>{grp_id}</code></b>\n\n"
        "sᴇʟᴇᴄᴛ ᴏɴᴇ ᴏꜰ ᴛʜᴇ sᴇᴛᴛɪɴɢs ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ "
        "ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ..."
    )
    setting_buttons = _main_settings_buttons(settings, int(grp_id), include_premium=_is_bot_owner(user_id))
    if _is_bot_owner(user_id):
        setting_buttons.insert(0, [await _global_payment_mode_button(int(grp_id))])
    markup = InlineKeyboardMarkup(setting_buttons)

    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        return

    await target.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)


# ============================================================
# PAGE TEXTS & SHORTLINKS
# ============================================================

def _page_text(key, settings):
    if key == "auto_filter":
        state = "ᴏɴ ✅" if settings.get("auto_filter") else "ᴏꜰꜰ ❌"
        return (
            f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ ᴍᴏᴅᴇ ᴍᴇᴀɴs "
            f"ʙᴏᴛ sᴇɴᴅ ʀᴇsᴜʟᴛ ɪɴ ɢʀᴏᴜᴘ ᴏʀ ɴᴏᴛ...ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ - {state}</b>"
        )
    if key == "file_secure":
        state = "ᴏɴ ✅" if settings.get("file_secure") else "ᴏꜰꜰ ❌"
        return (
            f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇs ᴘʀᴏᴛᴇᴄᴛɪᴏɴ, "
            f"ᴍᴇᴀɴs ᴡʜᴇᴛʜᴇʀ ᴜsᴇʀs ᴄᴀɴ ꜰᴏʀᴡᴀʀᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴏʀ ɴᴏᴛ...ᴘʀᴏᴛᴇᴄᴛ - {state}</b>"
        )
    if key == "imdb":
        return f"<b>🎬 IMDB</b>\n\nPoster: {'ON ✅' if settings.get('imdb') else 'OFF ❌'}\n\n<code>{settings.get('template', IMDB_TEMPLATE)}</code>"
    if key == "spell_check":
        state = "ᴏɴ ✅" if settings.get("spell_check") else "ᴏꜰꜰ ❌"
        return (
            f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʙᴏᴛ sᴘᴇʟʟɪɴɢ ᴄʜᴇᴄᴋ ᴍᴇssᴀɢᴇ"
            f"sᴘᴇʟʟ ᴄʜᴇᴄᴋ - {state}</b>"
        )
    if key == "auto_delete":
        return f"<b>🗑️ AUTO DELETE</b>\n\nEnabled: {'ON ✅' if settings.get('auto_delete') else 'OFF ❌'}\nDelete time: <code>{get_readable_time(settings.get('delete_time', DELETE_TIME))}</code>"
    if key == "link":
        return f"<b>📚 RESULT MODE</b>\n\nCurrent: {'LINKS 🖇' if settings.get('link') else 'BUTTONS 🎯'}"
    if key == "file_mode":
        mode = settings.get("file_mode_type", "verify")
        mode_text = "♻️ ᴠᴇʀɪғʏ" if mode == "verify" else "📎 ꜱʜᴏʀᴛʟɪɴᴋ"
        return f"<b>📁 ꜰɪʟᴇ ᴍᴏᴅᴇ</b>\n\nʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜰɪʟᴇs ᴍᴏᴅᴇ.\n\nᴄᴜʀʀᴇɴᴛ: {mode_text}"
    if key == "caption":
        return f"<b>📝 FILES CAPTIONS</b>\n\nCurrent caption:\n<code>{settings.get('caption', FILE_CAPTION)}</code>\n\nSupported placeholder: {{file_name}}"
    if key == "tutorial":
        return f"<b>🎬 TUTORIAL LINK</b>\n\n1: {settings.get('tutorial') or TUTORIAL}\n2: {settings.get('tutorial_2') or TUTORIAL_2}\n3: {settings.get('tutorial_3') or TUTORIAL_3}"
    if key == "shortlink":
        return _shortlink_master_text(settings)
    if key == "shortlink_list":
        return _shortlink_list_text(settings)
    if key == "verification_gap":
        return _verification_gap_text(settings)
    if key == "request_channel":
        return f"<b>📢 SET MOVIE REQ</b>\n\nCurrent request channel: <code>{settings.get('request_channel', REQUEST_CHANNEL)}</code>"
    if key == "fsub":
        channels = settings.get("fsub_channels") or []
        details = settings.get("fsub_channel_details") or {}
        channel_lines = []
        for channel_id in channels:
            detail = details.get(str(channel_id), {}) if isinstance(details, dict) else {}
            title = html.escape(str(detail.get("title") or "Channel title unavailable"))
            username = html.escape(str(detail.get("username") or "").strip())
            link = f" (@{username})" if username else ""
            channel_lines.append(
                f"• <b>{title}</b>{link}\n  ID: <code>{channel_id}</code>"
            )
        return ("<b>📢 GROUP FORCE SUBSCRIPTION</b>\n\n"
                + "Group-specific FSUB: " + ("ON ✅" if settings.get("fsub_enabled") else "OFF ❌")
                + "\nGlobal AUTH_CHANNEL/AUTH_REQ_CHANNEL remains enforced for compatibility.\n\n"
                + ("\n".join(channel_lines) or "No group-specific channels configured."))
    if key == "new_shortener":
        return ("<b>🔗 ɴᴇᴡ 3-sᴛᴇᴘ ꜱʜᴏʀᴛᴇɴᴇʀ</b>\n\n"
                f"Status: <b>{'ᴏɴ ✅' if settings.get('new_shortener_enabled') else 'ᴏꜰꜰ ❌'}</b>\n\n"
                "Select a section below to configure its URL, API key, tutorial, or timing.")
    if key in {"new_shortener_step1", "new_shortener_step2", "new_shortener_step3"}:
        number = int(key[-1])
        def shown(k):
            return html.escape(str(settings.get(k) or "ɴᴏᴛ ꜱᴇᴛ"))
        suffix = {1: "sᴛ", 2: "ɴᴅ", 3: "ʀᴅ"}[number]
        return (f"<b>🔗 {number}{suffix} ꜱʜᴏʀᴛʟɪɴᴋ ꜱᴇᴛᴛɪɴɢs</b>\n\n"
                f"🌐 ᴡᴇʙsɪᴛᴇ: <code>{shown(f'new_shortener_step{number}_url')}</code>\n"
                f"🔑 ᴀᴘɪ ᴋᴇʏ: <code>{shown(f'new_shortener_api{number}')}</code>\n"
                f"📚 ᴛᴜᴛᴏʀɪᴀʟ: {shown(f'new_shortener_tutorial{number}')}")
    if key == "new_shortener_tutorials":
        return "<b>📚 ɴᴇᴡ 3-sᴛᴇᴘ ᴛᴜᴛᴏʀɪᴀʟs</b>\n\nConfigure a separate tutorial for each step."
    if key == "new_shortener_gaps":
        return ("<b>⏱️ ɴᴇᴡ 3-sᴛᴇᴘ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ɢᴀᴘs</b>\n\n"
                f"Step 1 gap: <code>{settings.get('new_shortener_gap1', THREE_VERIFY_GAP)}</code> sec\n"
                f"Step 2 gap: <code>{settings.get('new_shortener_gap2', THREE_VERIFY_GAP)}</code> sec")
    if key == "max_results":
        return f"<b>🔢 SET MAX RESULTS</b>\n\nCurrent: <code>{settings.get('max_results', MAX_BTN)}</code>\nAllowed: 1–20"
    if key == "details":
        return (
            "<b>ℹ️ DETAILS</b>\n\n"
            f"Shortener 1: <code>{settings.get('shortner')}</code>\n"
            f"Shortener 2: <code>{settings.get('shortner_two')}</code>\n"
            f"Shortener 3: <code>{settings.get('shortner_three')}</code>\n"
            f"Verify gap: <code>{settings.get('verify_time')}</code>\n"
            f"Third verify gap: <code>{settings.get('third_verify_time')}</code>\n"
            f"Force channels: <code>{settings.get('fsub_channels', [settings.get('fsub_id', AUTH_CHANNEL)])}</code>\n"
            f"Log channel: <code>{settings.get('log')}</code>\n"
            f"Tutorial 1: {settings.get('tutorial')}\n"
            f"Tutorial 2: {settings.get('tutorial_2')}\n"
            f"Tutorial 3: {settings.get('tutorial_3')}\n"
            f"IMDB template: <code>{settings.get('template')}</code>\n"
            f"Caption: <code>{settings.get('caption')}</code>\n"
            f"Max results: <code>{settings.get('max_results', MAX_BTN)}</code>\n"
            f"Movie request: <code>{settings.get('request_channel', REQUEST_CHANNEL)}</code>"
        )
    return "<b>Settings</b>"


def _shortlink_master_text(settings):
    state = "ᴏɴ ✅" if settings.get("is_verify") else "ᴏꜰꜰ ❌"
    return (
        "⚙️ <b>ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ</b>\n"
        "ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜱʜᴏʀᴛʟɪɴᴋꜱ ᴀɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴇᴛᴛɪɴɢꜱ ꜰʀᴏᴍ ʜᴇʀᴇ.\n"
        "<b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ 👇</b>\n"
        f"✅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ : {state}"
    )


def _shortlink_master_buttons(settings, grp_id):
    toggle = "ᴛᴜʀɴ ᴏꜰꜰ ❌" if settings.get("is_verify") else "ᴛᴜʀɴ ᴏɴ ✅"
    return [
        [InlineKeyboardButton(toggle, callback_data=f"set_toggle#is_verify#{grp_id}#shortlink")],
        [InlineKeyboardButton("🖇️ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_page#shortlink_list#{grp_id}")],
        [InlineKeyboardButton("⏱️ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ɢᴀᴘ", callback_data=f"set_page#verification_gap#{grp_id}")],
        _back(grp_id, "main"),
    ]


def _shortlink_list_text(settings):
    def val(k):
        v = settings.get(k)
        return v if v else "ɴᴏᴛ ꜱᴇᴛ"

    return (
        "<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴠᴇʀɪꜰʏ ᴍᴏᴅᴇ</b>\n"
        "<b>ꜱᴇᴛ ʏᴏᴜʀ 1ꜱᴛ, 2ɴᴅ ᴀɴᴅ 3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ...</b>\n\n"
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 1ꜱᴛ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner')}</code>\n<code>{val('api')}</code>\n"
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 2ɴᴅ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner_two')}</code>\n<code>{val('api_two')}</code>\n"
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner_three')}</code>\n<code>{val('api_three')}</code>"
    )


def _shortlink_list_buttons(grp_id):
    return [
        [
            InlineKeyboardButton("1ꜱᴛ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#1#{grp_id}"),
            InlineKeyboardButton("2ɴᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#2#{grp_id}")
        ],
        [InlineKeyboardButton("3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#3#{grp_id}")],
        [InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_delete_shortner#menu#{grp_id}")],
        _back(grp_id, "shortlink"),
    ]


def _verification_gap_text(settings):
    verify_on = "ᴏɴ ✅" if settings.get("is_verify") else "ᴏꜰꜰ ❌"
    return (
        "<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴘʀᴏᴄᴇss, ᴍᴇᴀɴs ʏᴏᴜ ᴄᴀɴ ᴛᴜʀɴ ᴏɴ/ᴏꜰꜰ & ꜱᴇᴛ ᴛɪᴍᴇ ꜰᴏʀ 1ꜱᴛ ᴀɴᴅ 2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴘʀᴏᴄᴇss ᴀɴᴅ ᴀʟꜱᴏ ʏᴏᴜ ᴄᴀɴ ꜱᴇᴛ ʟᴏɢ ᴄʜᴀɴɴᴇʟ.</b>\n\n"
        f"2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ - {verify_on}\n"
        f"ᴛɪᴍᴇ - <code>{get_readable_time(settings.get('verify_time', TWO_VERIFY_GAP))}</code>\n"
        f"ʟᴏɢ ᴄʜᴀɴɴᴇʟ - <code>{settings.get('log', LOG_VR_CHANNEL)}</code>"
    )


def _verification_gap_buttons(grp_id):
    return [
        [
            InlineKeyboardButton("ᴛɪᴍᴇ 1", callback_data=f"set_gap#1#{grp_id}"),
            InlineKeyboardButton("ᴛɪᴍᴇ 2", callback_data=f"set_gap#2#{grp_id}")
        ],
        _back(grp_id, "shortlink"),
    ]


def _shortener_settings_text(settings, number):
    domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
    api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
    domain = settings.get(domain_key) or "ɴᴏᴛ ꜱᴇᴛ"
    api = settings.get(api_key) or "ɴᴏᴛ ꜱᴇᴛ"
    return f"<b>ꜱʜᴏʀᴛᴇɴᴇʀ {number} ꜱᴇᴛᴛɪɴɢꜱ:</b>\n\n🌐 ᴅᴏᴍᴀɪɴ: <code>{domain}</code>\n🔗 ᴀᴘɪ: <code>{api}</code>"


def _shortener_settings_buttons(grp_id, number):
    return [
        [
            InlineKeyboardButton("ꜱᴇᴛ", callback_data=f"set_shortner_action#set#{number}#{grp_id}"),
            InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"set_shortner_action#remove#{number}#{grp_id}")
        ],
        _back(grp_id, "shortlink_list"),
    ]


def _delete_menu_text(settings):
    rows = []
    for number, domain_key, api_key in ((1, "shortner", "api"), (2, "shortner_two", "api_two"), (3, "shortner_three", "api_three")):
        if settings.get(domain_key) and settings.get(api_key):
            rows.append(f"3ʀᴅ" if number == 3 else f"1ꜱᴛ" if number == 1 else f"2ɴᴅ")
    body = "\n".join(rows) if rows else "ɴᴏ ꜱʜᴏʀᴛᴇɴᴇʀ ɪꜱ ᴄᴜʀʀᴇɴᴛʟʏ ꜱᴇᴛ."
    return f"<b>ᴡʜɪᴄʜ ꜱʜᴏʀᴛᴇɴᴇʀ ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ?</b>\n\n{body}"


def _delete_menu_buttons(settings, grp_id):
    rows = [
        [
            InlineKeyboardButton("ꜰɪʀꜱᴛ", callback_data=f"set_delete_shortner#1#{grp_id}"),
            InlineKeyboardButton("ꜱᴇᴄᴏɴᴅ", callback_data=f"set_delete_shortner#2#{grp_id}"),
            InlineKeyboardButton("ᴛʜɪʀᴅ", callback_data=f"set_delete_shortner#3#{grp_id}")
        ],
        [InlineKeyboardButton("ᴀʟʟ", callback_data=f"set_delete_shortner#all#{grp_id}")],
        _back(grp_id, "shortlink_list")
    ]
    return rows


def _time_page_text(settings, number):
    if number == 1:
        gap = settings.get("verify_time", TWO_VERIFY_GAP)
        return f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ 1ꜱᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ, ᴍᴇᴀɴs ᴡʜᴇɴ ꜱʜᴏᴜʟᴅ ꜱᴇᴄᴏɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴄᴏᴍᴇ...</b>\n\n2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - <code>{get_readable_time(gap)}</code>"
    gap = settings.get("third_verify_time", THREE_VERIFY_GAP)
    return f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ 2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ, ᴍᴇᴀɴs ᴡʜᴇɴ ꜱʜᴏᴜʟᴅ ᴛʜɪʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴄᴏᴍᴇ...</b>\n\n3ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - <code>{get_readable_time(gap)}</code>"


def _time_page_buttons(grp_id, number):
    return [
        [InlineKeyboardButton("ꜱᴇᴛ ᴛɪᴍᴇ", callback_data=f"set_gap_input#{number}#{grp_id}")],
        _back(grp_id, "verification_gap"),
    ]


def _page_buttons(key, settings, grp_id):
    b = []
    if key in {"auto_filter", "file_secure", "spell_check", "auto_delete", "link", "file_mode"}:
        if key == "link":
            label = "sᴇᴛ ʙᴜᴛᴛᴏɴ ᴍᴏᴅᴇ" if settings.get("link") else "sᴇᴛ ʟɪɴᴋs ᴍᴏᴅᴇ"
            b.append([InlineKeyboardButton(label, callback_data=f"set_toggle#{key}#{grp_id}")])
        elif key == "file_mode":
            mode = settings.get("file_mode_type", "verify")
            next_mode = "shortlink" if mode == "verify" else "verify"
            label = "📎 sᴇᴛ sʜᴏʀᴛʟɪɴᴋ ᴍᴏᴅᴇ" if mode == "verify" else "♻️ sᴇᴛ ᴠᴇʀɪғʏ ᴍᴏᴅᴇ"
            b.append([InlineKeyboardButton(label, callback_data=f"set_file_mode#{next_mode}#{grp_id}")])
        else:
            label = "ᴛᴜʀɴ ᴏꜰꜰ ❌" if settings.get(key) else "ᴛᴜʀɴ ᴏɴ ✅"
            b.append([InlineKeyboardButton(label, callback_data=f"set_toggle#{key}#{grp_id}")])

        if key == "auto_delete":
            b.append([InlineKeyboardButton("⏱️ sᴇᴛ ᴛɪᴍᴇ", callback_data=f"set_input#delete_time#{grp_id}")])

    elif key == "shortlink":
        return _shortlink_master_buttons(settings, grp_id)
    elif key == "shortlink_list":
        return _shortlink_list_buttons(grp_id)
    elif key == "verification_gap":
        return _verification_gap_buttons(grp_id)
    elif key == "shortener":
        return _shortener_settings_buttons(grp_id, settings.get("_shortener_number", 1))
    elif key == "delete_menu":
        return _delete_menu_buttons(settings, grp_id)
    elif key == "time_page":
        return _time_page_buttons(grp_id, settings.get("_time_number", 1))
    elif key == "imdb":
        b = [
            [
                InlineKeyboardButton("sᴇᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data=f"set_input#template#{grp_id}"),
                InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data=f"set_default#template#{grp_id}")
            ],
            [InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ ᴘᴏsᴛᴇʀ", callback_data=f"set_toggle#imdb#{grp_id}")]
        ]
    elif key == "caption":
        b = [[
            InlineKeyboardButton("sᴇᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"set_input#caption#{grp_id}"),
            InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"set_default#caption#{grp_id}")
        ]]
    elif key == "tutorial":
        b = [
            [
                InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 1", callback_data=f"set_input#tutorial#{grp_id}"),
                InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 2", callback_data=f"set_input#tutorial_2#{grp_id}")
            ],
            [InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 3", callback_data=f"set_input#tutorial_3#{grp_id}")]
        ]
    elif key == "request_channel":
        b = [[
            InlineKeyboardButton("sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#request_channel#{grp_id}"),
            InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_delete#request_channel#{grp_id}")
        ]]
    elif key == "fsub":
        b = [
            [InlineKeyboardButton("sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#fsub_add#{grp_id}"),
             InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#fsub_delete#{grp_id}")],
            [InlineKeyboardButton("ᴄᴜsᴛᴏᴍ ᴊᴏɪɴ ʙᴜᴛᴛᴏɴ ʟᴀʙᴇʟ", callback_data=f"set_input#fsub_label#{grp_id}"),
             InlineKeyboardButton("ʀᴇsᴇᴛ ʟᴀʙᴇʟ", callback_data=f"set_input#fsub_label_reset#{grp_id}")],
        ]
    elif key == "new_shortener":
        toggle_label = "🔴 ᴛᴜʀɴ ᴏꜰꜰ ɴᴇᴡ 3-sᴛᴇᴘ" if settings.get("new_shortener_enabled") else "🟢 ᴛᴜʀɴ ᴏɴ ɴᴇᴡ 3-sᴛᴇᴘ"
        b = [
            [InlineKeyboardButton(toggle_label, callback_data=f"set_toggle#new_shortener_enabled#{grp_id}#new_shortener")],
            [InlineKeyboardButton("1ꜱᴛ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_page#new_shortener_step1#{grp_id}"), InlineKeyboardButton("2ɴᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_page#new_shortener_step2#{grp_id}")],
            [InlineKeyboardButton("3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_page#new_shortener_step3#{grp_id}")],
            [InlineKeyboardButton("📚 ᴛᴜᴛᴏʀɪᴀʟ sᴇᴛᴛɪɴɢs", callback_data=f"set_page#new_shortener_tutorials#{grp_id}"), InlineKeyboardButton("⏱️ ɢᴀᴘ sᴇᴛᴛɪɴɢs", callback_data=f"set_page#new_shortener_gaps#{grp_id}")],
        ]
    elif key in {"new_shortener_step1", "new_shortener_step2", "new_shortener_step3"}:
        number = int(key[-1])
        b = [
            [InlineKeyboardButton("🌐 ꜱᴇᴛ ᴡᴇʙsɪᴛᴇ ᴜʀʟ", callback_data=f"set_input#new_shortener_step{number}_url#{grp_id}")],
            [InlineKeyboardButton("🔑 ꜱᴇᴛ ᴀᴘɪ ᴋᴇʏ", callback_data=f"set_input#new_shortener_api{number}#{grp_id}")],
            [InlineKeyboardButton("📚 ꜱᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"set_input#new_shortener_tutorial{number}#{grp_id}")],
            _back(grp_id, "new_shortener"),
        ]
    elif key == "new_shortener_tutorials":
        b = [[InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 1", callback_data=f"set_input#new_shortener_tutorial1#{grp_id}"), InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 2", callback_data=f"set_input#new_shortener_tutorial2#{grp_id}")], [InlineKeyboardButton("sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ 3", callback_data=f"set_input#new_shortener_tutorial3#{grp_id}"),], _back(grp_id, "new_shortener")]
    elif key == "new_shortener_gaps":
        b = [[InlineKeyboardButton("sᴇᴛ ɢᴀᴘ 1", callback_data=f"set_input#new_shortener_gap1#{grp_id}"), InlineKeyboardButton("sᴇᴛ ɢᴀᴘ 2", callback_data=f"set_input#new_shortener_gap2#{grp_id}")], _back(grp_id, "new_shortener")]
    elif key == "max_results":
        b = [[
            InlineKeyboardButton("sᴇᴛ ᴍᴀx ʀᴇsᴜʟᴛ", callback_data=f"set_input#max_results#{grp_id}"),
            InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴍᴀx ʀᴇsᴜʟᴛ", callback_data=f"set_default#max_results#{grp_id}")
        ]]
    elif key == "details":
        b = [[InlineKeyboardButton("ʀᴇsᴇᴛ ᴀʟʟ", callback_data=f"set_reset#{grp_id}")]]

    b.append(_back(grp_id, "main"))
    return b

async def show_page(client, query, key, grp_id, extra=None):
    settings = await _fast_settings(int(grp_id))

    if key == "shortener":
        settings = dict(settings)
        settings["_shortener_number"] = int(extra or 1)
        text = _shortener_settings_text(settings, int(extra or 1))
        buttons = _shortener_settings_buttons(grp_id, int(extra or 1))
    elif key == "delete_menu":
        text = _delete_menu_text(settings)
        buttons = _delete_menu_buttons(settings, grp_id)
    elif key == "time_page":
        settings = dict(settings)
        settings["_time_number"] = int(extra or 1)
        text = _time_page_text(settings, int(extra or 1))
        buttons = _time_page_buttons(grp_id, int(extra or 1))
    else:
        text = _page_text(key, settings)
        buttons = _page_buttons(key, settings, grp_id)

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


# ============================================================
# AUTHORIZE & UTILS
# ============================================================

async def _authorize(client, query, grp_id):
    cache_key = (query.from_user.id, int(grp_id))
    now = asyncio.get_running_loop().time()
    if now - _AUTH_CACHE.get(cache_key, 0) < _AUTH_TTL:
        return True
    try:
        ok = await is_check_admin(client, int(grp_id), query.from_user.id)
    except Exception:
        ok = False
    if not ok:
        await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
        return False
    _AUTH_CACHE[cache_key] = now
    return True


def _prompt_state(query, gid, kind, origin_page, **extra):
    state = {
        "type": kind,
        "origin_page": origin_page,
        "prompt_chat_id": query.message.chat.id,
        "prompt_message_id": query.message.id,
    }
    state.update(extra)
    PENDING[(query.from_user.id, gid)] = state
    return state


async def _edit_prompt(client, state, text, markup=None):
    try:
        return await client.edit_message_text(
            state["prompt_chat_id"],
            state["prompt_message_id"],
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        return None


def _parse_premium_duration(value):
    """Parse Premium duration in days, weeks, months, years, or lifetime.

    Premium expiry is stored canonically as ``days`` because the payment
    system calculates expiry from that field.  The human-facing ``duration``
    keeps the unit the owner entered, so both formats remain supported.

    Supported examples: 7d, 30 days, 1w, 2 weeks, 1mo, 3 months,
    1y, 2 years, lifetime.  Month = 30 days; year = 365 days.
    """
    normalized = re.sub(r"\s+", " ", str(value).strip().lower())
    if normalized in {"lifetime", "life time", "life", "forever"}:
        return None, "Lifetime"

    m = re.fullmatch(
        r"(\d+)\s*(d|day|days|w|week|weeks|mo|mon|month|months|y|yr|year|years)",
        normalized,
    )
    if not m:
        return False, None

    n = int(m.group(1))
    if n <= 0:
        return False, None

    unit = m.group(2)
    if unit in {"d", "day", "days"}:
        days = n
        label = f"{n} day" + ("s" if n != 1 else "")
    elif unit in {"w", "week", "weeks"}:
        days = n * 7
        label = f"{n} week" + ("s" if n != 1 else "")
    elif unit in {"mo", "mon", "month", "months"}:
        days = n * 30
        label = f"{n} month" + ("s" if n != 1 else "")
    else:
        days = n * 365
        label = f"{n} year" + ("s" if n != 1 else "")

    return days, label


def _parse_duration(value):
    # Keep the existing helper used by non-Premium settings unchanged.
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", value.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        return None
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


# ============================================================
# CALLBACK & MESSAGE HANDLERS
# ============================================================

def _premium_admin_text():
    rows = []
    for key, plan in PREMIUM_PLANS.items():
        rows.append(f"<b>{plan['name']}</b> · <code>{plan['duration']}</code> · <code>{plan['price']}</code>")
    return "💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ sᴇᴛᴛɪɴɢs</b>\n\n" + "\n".join(rows) + "\n\nꜱᴇʟᴇᴄᴛ ᴀ ᴘʟᴀɴ ᴛᴏ ᴄʜᴀɴɢᴇ ɪᴛ."


def _premium_admin_buttons(group_id=None):
    rows = []
    for key, plan in PREMIUM_PLANS.items():
        rows.append([InlineKeyboardButton(f"{plan['name']} · {plan['price']}", callback_data=f"premium_plan#{key}#{group_id or 0}")])
    if group_id:
        rows.append([InlineKeyboardButton("≪ ʙᴀᴄᴋ ᴛᴏ sᴇᴛᴛɪɴɢs", callback_data=f"premium_back#{group_id}")])
    return rows


def _premium_plan_buttons(key, group_id=None):
    rows = [
        [InlineKeyboardButton("💰 sᴇᴛ ᴘʀɪᴄᴇ", callback_data=f"premium_edit#{key}#price#{group_id or 0}")],
        [InlineKeyboardButton("⏳ sᴇᴛ ᴅᴜʀᴀᴛɪᴏɴ", callback_data=f"premium_edit#{key}#duration#{group_id or 0}")],
        [InlineKeyboardButton("≪ ʙᴀᴄᴋ", callback_data=f"premium_settings#{group_id or 0}")],
    ]
    return rows


def _premium_input_markup(key, field, group_id=None):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✕ ᴄᴀɴᴄᴇʟ", callback_data=f"premium_cancel#{key}#{field}#{group_id or 0}")],
        [InlineKeyboardButton("≪ ʙᴀᴄᴋ", callback_data=f"premium_plan#{key}#{group_id or 0}")],
    ])


def _premium_plan_text(key):
    plan = PREMIUM_PLANS[key]
    return f"💎 <b>{plan['name']}</b>\n\n💰 Price: <code>{plan['price']}</code>\n⏳ Duration: <code>{plan['duration']}</code>\n\nChoose what you want to change."


@Client.on_callback_query(filters.regex(r"^premium_(settings|plan#|edit#|cancel#|back#|close)"))
async def premium_settings_callback(client, query):
    if not _is_bot_owner(query.from_user.id):
        return await query.answer("ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs.", show_alert=True)

    data = query.data
    parts = data.split("#")
    group_id = 0
    if len(parts) > 1 and parts[-1].lstrip("-").isdigit():
        group_id = int(parts[-1])

    try:
        if data.startswith("premium_settings"):
            PENDING.pop((query.from_user.id, 0), None)
            await query.answer()
            return await query.message.edit_text(
                _premium_admin_text(),
                reply_markup=InlineKeyboardMarkup(_premium_admin_buttons(group_id)),
                parse_mode=enums.ParseMode.HTML,
            )

        if data.startswith("premium_back#"):
            PENDING.pop((query.from_user.id, 0), None)
            await query.answer()
            if group_id:
                return await show_group_settings(client, query, group_id)
            return await query.message.edit_text(
                _premium_admin_text(),
                reply_markup=InlineKeyboardMarkup(_premium_admin_buttons()),
                parse_mode=enums.ParseMode.HTML,
            )

        if data == "premium_close":
            PENDING.pop((query.from_user.id, 0), None)
            await query.answer("Closed")
            return await query.message.delete()

        if data.startswith("premium_cancel#"):
            await query.answer("Cancelled")
            key = parts[1]
            if key not in PREMIUM_PLANS:
                return
            PENDING.pop((query.from_user.id, 0), None)
            return await query.message.edit_text(
                _premium_plan_text(key),
                reply_markup=InlineKeyboardMarkup(_premium_plan_buttons(key, group_id)),
                parse_mode=enums.ParseMode.HTML,
            )

        if data.startswith("premium_plan#"):
            PENDING.pop((query.from_user.id, 0), None)
            await query.answer()
            key = parts[1]
            if len(parts) > 2 and parts[2].lstrip("-").isdigit():
                group_id = int(parts[2])
            if key not in PREMIUM_PLANS:
                return await query.answer("Invalid plan.", show_alert=True)
            return await query.message.edit_text(
                _premium_plan_text(key),
                reply_markup=InlineKeyboardMarkup(_premium_plan_buttons(key, group_id)),
                parse_mode=enums.ParseMode.HTML,
            )

        if data.startswith("premium_edit#"):
            await query.answer()
            if len(parts) < 3:
                return await query.answer("Invalid setting.", show_alert=True)
            key, field = parts[1], parts[2]
            if len(parts) > 3 and parts[3].lstrip("-").isdigit():
                group_id = int(parts[3])
            if key not in PREMIUM_PLANS or field not in {"price", "duration"}:
                return await query.answer("Invalid setting.", show_alert=True)

            PENDING[(query.from_user.id, 0)] = {
                "type": f"premium_{field}",
                "plan": key,
                "origin_page": "premium_settings",
                "group_id": group_id,
                "prompt_chat_id": query.message.chat.id,
                "prompt_message_id": query.message.id,
            }
            if field == "price":
                prompt = "sᴇɴᴅ ᴛʜᴇ ᴘʀɪᴄᴇ ᴏɴʟʏ, ᴇ.ɢ. <code>23</code>"
                current = PREMIUM_PLANS[key]["price"]
            else:
                prompt = (
                    "sᴇɴᴅ ᴅᴜʀᴀᴛɪᴏɴ: <code>7d</code>, <code>1week</code>, "
                    "<code>30days</code>, <code>1month</code>, <code>3months</code>, "
                    "<code>1year</code> ᴏʀ <code>lifetime</code>"
                )
                current = PREMIUM_PLANS[key]["duration"]
            return await query.message.edit_text(
                f"<b>{prompt}</b>\n\nCurrent: <code>{current}</code>\n\nᴜsᴇ ᴛʜᴇ ᴄᴀɴᴄᴇʟ ʙᴜᴛᴛᴏɴ ᴏʀ sᴇɴᴅ /cancel.",
                reply_markup=_premium_input_markup(key, field, group_id),
                parse_mode=enums.ParseMode.HTML,
            )
    except Exception as exc:
        print(f"premium settings callback error: {exc}")
        try:
            return await query.answer("💔 sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ...", show_alert=True)
        except Exception:
            return

@Client.on_callback_query(filters.regex(r"^global_payment_mode#toggle(?:#-?\d+)?$"))
async def global_payment_mode_callback(client, query):
    if not _is_bot_owner(query.from_user.id):
        return await query.answer("Only the bot owner can change global auto-payment mode.", show_alert=True)
    try:
        from plugins.premium_payments import get_auto_payment_enabled, set_auto_payment_enabled
        current = await get_auto_payment_enabled()
        updated = await set_auto_payment_enabled(not current)
        state = "ON ✅ — users will see the payment-bot button only." if updated else "OFF ❌ — users will see the owner button only."
        await query.answer(f"Auto-payment is now {'ON' if updated else 'OFF'}.", show_alert=True)
        parts = query.data.split("#")
        group_id = int(parts[2]) if len(parts) > 2 else None
        if group_id is not None and group_id != 0:
            return await show_group_settings(client, query, group_id)
        try:
            await query.message.edit_text(
                f"💳 <b>GLOBAL AUTO-PAYMENT SETTING</b>\n\n{state}\n\nThis setting applies globally to every group.",
                reply_markup=InlineKeyboardMarkup([
                    [await _global_payment_mode_button()],
                    [InlineKeyboardButton("↩️ BACK TO SETTINGS", callback_data="advanced_settings")],
                ]),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass
    except Exception as exc:
        print(f"global auto-payment setting error: {type(exc).__name__}: {exc}")
        return await query.answer("Could not save global auto-payment setting. Check MongoDB logs.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^(set_|advanced_settings)"))
async def settings_callback(client, query):
    data = query.data
    await query.answer()

    try:
        if data.startswith("set_group#"):
            gid = int(data.split("#", 1)[1])
            if not await _authorize(client, query, gid):
                return
            return await show_group_settings(client, query, gid)

        if data.startswith("set_groups#"):
            gid = int(data.split("#", 1)[1])
            if not await _authorize(client, query, gid):
                return
            return await show_group_list(client, query)

        if data.startswith("advanced_settings"):
            gid = int(data.split("#")[1]) if "#" in data else None
            if gid is None:
                return await show_group_list(client, query)
            if not await _authorize(client, query, gid):
                return
            return await show_group_settings(client, query, gid)

        parts = data.split("#")
        action = parts[0]

        if action in {"set_page", "set_toggle", "set_input", "set_default", "set_delete", "set_file_mode"}:
            key = parts[1]
            gid = int(parts[2])
        elif action == "set_back":
            key = parts[1]
            gid = int(parts[2])
        elif action in {"set_shortner", "set_shortner_action", "set_delete_shortner", "set_gap", "set_gap_input"}:
            key = parts[1]
            gid = int(parts[-1])
        elif action == "set_cancel":
            gid = int(parts[1])
            key = "cancel"
        else:
            gid = int(parts[1]) if len(parts) > 1 else 0
            key = parts[1] if len(parts) > 1 else ""

        if not await _authorize(client, query, gid):
            return

        if action == "set_page":
            return await show_page(client, query, key, gid)

        if action == "set_back":
            PENDING.pop((query.from_user.id, gid), None)
            if key == "main":
                return await show_group_settings(client, query, gid)
            return await show_page(client, query, key, gid)

        if action == "set_close":
            PENDING.pop((query.from_user.id, gid), None)
            return await query.message.delete()

        if action == "set_reset":
            await save_default_settings(gid)
            _invalidate_settings_cache(gid)
            return await show_group_settings(client, query, gid)

        if action == "set_file_mode":
            mode = key if key in {"verify", "shortlink"} else "verify"
            await save_group_settings(gid, "file_mode", True)
            _invalidate_settings_cache(gid)
            await save_group_settings(gid, "file_mode_type", mode)
            _invalidate_settings_cache(gid)
            return await show_page(client, query, "file_mode", gid)

        if action == "set_toggle":
            settings = await _fast_settings(gid)
            value = not bool(settings.get(key))
            await save_group_settings(gid, key, value)
            _invalidate_settings_cache(gid)
            if len(parts) > 3 and parts[3] in {"shortlink", "new_shortener"}:
                return await show_page(client, query, parts[3], gid)
            return await show_page(client, query, key, gid)

        if action == "set_default":
            defaults = db.default.copy()
            await save_group_settings(gid, key, int(MAX_BTN) if key == "max_results" else defaults.get(key, ""))
            _invalidate_settings_cache(gid)
            return await show_page(client, query, key, gid)

        if action == "set_delete":
            if key == "request_channel":
                await save_group_settings(gid, key, int(REQUEST_CHANNEL))
                _invalidate_settings_cache(gid)
            return await show_page(client, query, key, gid)

        if action == "set_input":
            origin_page_map = {
                "delete_time": "auto_delete",
                "template": "imdb",
                "caption": "caption",
                "max_results": "max_results",
                "request_channel": "request_channel",
                "fsub_add": "fsub",
                "fsub_delete": "fsub",
                "fsub_label": "fsub",
                "fsub_label_reset": "fsub",
            }
            new_shortener_keys = {
                "new_shortener_step1_url", "new_shortener_step2_url", "new_shortener_step3_url",
                "new_shortener_api1", "new_shortener_api2", "new_shortener_api3",
                "new_shortener_tutorial1", "new_shortener_tutorial2", "new_shortener_tutorial3",
                "new_shortener_gap1", "new_shortener_gap2",
            }
            origin_page = (
                ("new_shortener_step" + key[-1] if key.startswith("new_shortener_api") else
                 "new_shortener_step" + key[len("new_shortener_step")] if key.startswith("new_shortener_step") and key.endswith("_url") else
                 "new_shortener_tutorials" if key.startswith("new_shortener_tutorial") else
                 "new_shortener_gaps" if key.startswith("new_shortener_gap") else "new_shortener") if key in new_shortener_keys
                else "shortlink_list" if key in {"shortner", "shortner_two", "shortner_three"}
                else "verification_gap" if key in {"verify_time", "third_verify_time"}
                else "tutorial" if key in {"tutorial", "tutorial_2", "tutorial_3"}
                else origin_page_map.get(key, "main")
            )
            state = _prompt_state(query, gid, key, origin_page)
            prompt = {
                "delete_time": "sᴇɴᴅ ᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ ɪɴ sᴇᴄᴏɴᴅs.",
                "template": "sᴇɴᴅ ʏᴏᴜʀ ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ. sᴜᴘᴘᴏʀᴛᴇᴅ: {search}, {mention}, {group}",
                "caption": "sᴇɴᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ. sᴜᴘᴘᴏʀᴛᴇᴅ: {file_name}",
                "max_results": "sᴇɴᴅ ᴍᴀx ʀᴇsᴜʟᴛs ꜰʀᴏᴍ 1 ᴛᴏ 20.",
                "request_channel": "sᴇɴᴅ ʀᴇǫᴜᴇsᴛ ᴄʜᴀɴɴᴇʟ ɪᴅ.",
                "fsub_add": "sᴇɴᴅ ꜰᴏʀᴄᴇ-sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ.",
                "fsub_delete": "sᴇɴᴅ ᴛʜᴇ ꜰᴏʀᴄᴇ-sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ.",
                "fsub_label": "Send channel ID and button text separated by | (example: -1001234567890 | Join Movie Channel).",
                "fsub_label_reset": "Send the channel ID whose custom join-button text should be reset.",
                "new_shortener_step1_url": "Send Step 1 shortener domain/URL (http/https URL or domain).",
                "new_shortener_step2_url": "Send Step 2 shortener domain/URL (http/https URL or domain).",
                "new_shortener_step3_url": "Send Step 3 shortener domain/URL (http/https URL or domain).",
                "new_shortener_api1": "Send Step 1 shortener API key.",
                "new_shortener_api2": "Send Step 2 shortener API key.",
                "new_shortener_api3": "Send Step 3 shortener API key.",
                "new_shortener_tutorial1": "Send Step 1 tutorial URL.",
                "new_shortener_tutorial2": "Send Step 2 tutorial URL.",
                "new_shortener_tutorial3": "Send Step 3 tutorial URL.",
                "new_shortener_gap1": "Send the Step 1 verification gap in seconds.",
                "new_shortener_gap2": "Send the Step 2 verification gap in seconds.",
                "tutorial": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 1 ᴜʀʟ.",
                "tutorial_2": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 2 ᴜʀʟ.",
                "tutorial_3": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 3 ᴜʀʟ.",
            }.get(key, "sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴠᴀʟᴜᴇ.")

            return await _edit_prompt(
                client, state,
                _cancel_prompt(f"<b>{prompt}</b>")
            )

        if action == "set_cancel":
            # Compatibility for old/stale keyboards only. New prompts use clickable /cancel text.
            PENDING.pop((query.from_user.id, gid), None)
            return await _edit_prompt(
                client,
                {
                    "prompt_chat_id": query.message.chat.id,
                    "prompt_message_id": query.message.id,
                },
                "ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...",
                InlineKeyboardMarkup([_back(gid, "main")])
            )

        if action == "set_shortner":
            return await show_page(client, query, "shortener", gid, int(key))

        if action == "set_shortner_action":
            mode = parts[1]
            number = int(parts[2])
            if mode == "set":
                state = _prompt_state(query, gid, f"shortner_{number}_domain", "shortlink_list", number=number)
                return await _edit_prompt(
                    client, state,
                    _cancel_prompt("<b>ꜱᴇɴᴅ ᴍᴇ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴡɪᴛʜᴏᴜᴛ https ꜰᴏʀᴍᴀᴛ -</b>\n\n<code>https://tnshort.net</code> ❌\n<code>tnshort.net</code> ✅")
                )

            domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
            await save_group_settings(gid, domain_key, "")
            _invalidate_settings_cache(gid)
            await save_group_settings(gid, api_key, "")
            _invalidate_settings_cache(gid)
            if _is_bot_owner(query.from_user.id):
                await db.set_owner_shortener(number, "", "")
            return await show_page(client, query, "shortener", gid, number)

        if action == "set_delete_shortner":
            if key == "menu":
                return await show_page(client, query, "delete_menu", gid)
            if key == "all":
                for domain_key, api_key in (("shortner", "api"), ("shortner_two", "api_two"), ("shortner_three", "api_three")):
                    await save_group_settings(gid, domain_key, "")
                    _invalidate_settings_cache(gid)
                    await save_group_settings(gid, api_key, "")
                    _invalidate_settings_cache(gid)
                if _is_bot_owner(query.from_user.id):
                    for slot in (1, 2, 3):
                        await db.set_owner_shortener(slot, "", "")
                return await query.message.edit_text(
                    "<b>ᴅᴇʟᴇᴛᴇ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅</b>",
                    reply_markup=InlineKeyboardMarkup([_back(gid, "shortlink_list")]),
                    parse_mode=enums.ParseMode.HTML
                )

            number = int(key)
            domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
            settings = await _fast_settings(gid)

            if not settings.get(domain_key) or not settings.get(api_key):
                return await query.message.edit_text(
                    "<b>💔 ꜰɪʀꜱᴛ ᴀᴅᴅ ᴛʜɪs ꜱʜᴏʀᴛᴇɴᴇʀ ꜰᴏʀ ᴅᴇʟᴇᴛɪᴏɴ.</b>",
                    reply_markup=InlineKeyboardMarkup([_back(gid, "delete_menu")]),
                    parse_mode=enums.ParseMode.HTML
                )

            await save_group_settings(gid, domain_key, "")
            _invalidate_settings_cache(gid)
            await save_group_settings(gid, api_key, "")
            _invalidate_settings_cache(gid)
            return await query.message.edit_text(
                f"<b>ᴅᴇʟᴇᴛᴇ {number} ꜱʜᴏʀᴛʟɪɴᴋ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅</b>",
                reply_markup=InlineKeyboardMarkup([_back(gid, "delete_menu")]),
                parse_mode=enums.ParseMode.HTML
            )

        if action == "set_gap":
            return await show_page(client, query, "time_page", gid, int(key))

        if action == "set_gap_input":
            number = int(key)
            state = _prompt_state(query, gid, f"gap_{number}", "verification_gap", number=number)
            return await _edit_prompt(
                client, state,
                _cancel_prompt("<b>ꜱᴇɴᴅ ᴍᴇ ᴀ ᴛɪᴍᴇ ɪɴ ʟɪᴋᴇ ᴛʜɪs -</b> <code>1h</code> ᴏʀ <code>15m</code>")
            )

    except Exception as exc:
        try:
            await query.answer("💔 ꜱᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ...", show_alert=True)
        except Exception:
            pass
        print(f"settings callback error: {exc}")


@Client.on_message(filters.command("cancel"))
async def advanced_cancel(client, message):
    candidates = [(k, v) for k, v in PENDING.items() if k[0] == message.from_user.id]
    if not candidates:
        raise ContinuePropagation

    (uid, gid), state = candidates[-1]
    PENDING.pop((uid, gid), None)
    page = state.get("origin_page", "main")
    if page == "premium_settings" and _is_bot_owner(uid):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            group_id = int(state.get("group_id") or 0)
            await client.edit_message_text(
                state["prompt_chat_id"],
                state["prompt_message_id"],
                _premium_plan_text(state["plan"]),
                reply_markup=InlineKeyboardMarkup(_premium_plan_buttons(state["plan"], group_id)),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass
        return

    # Delete the user's /cancel command immediately.
    try:
        await message.delete()
    except Exception:
        pass

    # Replace the active prompt with the cancelled state and a Back button
    # that returns to the exact settings page where the input was started.
    try:
        await client.edit_message_text(
            state["prompt_chat_id"],
            state["prompt_message_id"],
            "ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...",
            reply_markup=InlineKeyboardMarkup([_back(gid, page)]),
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass


@Client.on_message(filters.text)
async def advanced_input(client, message):
    uid = message.from_user.id if message.from_user else None
    if not uid:
        raise ContinuePropagation

    candidates = [(k, v) for k, v in PENDING.items() if k[0] == uid]
    if not candidates:
        raise ContinuePropagation

    (user_id, gid), state = candidates[-1]
    if message.text.startswith("/"):
        raise ContinuePropagation

    # Premium plan input is global and restricted to bot ADMINS; it does not
    # belong to a Telegram group, so do not run the group-admin check for it.
    if state.get("type") not in {"premium_price", "premium_duration"}:
        if not await is_check_admin(client, gid, uid):
            PENDING.pop((user_id, gid), None)
            raise ContinuePropagation

    value = message.text.strip()
    if not value:
        return await message.reply_text("ᴠᴀʟᴜᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ")

    key = state["type"]

    if key in {"premium_price", "premium_duration"}:
        if not _is_bot_owner(uid):
            PENDING.pop((uid, 0), None)
            raise ContinuePropagation
        plan_key = state["plan"]
        if plan_key not in PREMIUM_PLANS:
            PENDING.pop((uid, 0), None)
            return await message.reply_text("ᴘʟᴀɴ ɴᴏᴛ ғᴏᴜɴᴅ")
        if key == "premium_price":
            raw = value.replace("₹", "").replace(",", "").strip()
            if not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw) or float(raw) <= 0:
                return await message.reply_text("sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴘʀɪᴄᴇ, ᴇ.ɢ. <code>23</code>", parse_mode=enums.ParseMode.HTML)
            PREMIUM_PLANS[plan_key]["price"] = f"₹{raw.rstrip('0').rstrip('.') if '.' in raw else raw}"
        else:
            days, duration_label = _parse_premium_duration(value)
            if days is False:
                return await message.reply_text(
                    "sᴇɴᴅ a valid duration like <code>7d</code>, <code>1week</code>, "
                    "<code>30days</code>, <code>1month</code>, <code>3months</code>, "
                    "<code>1year</code> or <code>lifetime</code>.",
                    parse_mode=enums.ParseMode.HTML,
                )
            PREMIUM_PLANS[plan_key]["days"] = days
            PREMIUM_PLANS[plan_key]["duration"] = duration_label

            # Keep the public Premium-plan button label synchronized with the
            # duration the owner just selected.  The payment UI uses
            # PREMIUM_PLANS[...]["name"], so changing only `duration` would
            # leave the old WEEK/MONTH/YEAR label visible to users.
            if duration_label == "Lifetime":
                PREMIUM_PLANS[plan_key]["name"] = "LIFE TIME"
            else:
                dm = re.fullmatch(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)", duration_label, re.I)
                if dm:
                    amount = int(dm.group(1))
                    unit = dm.group(2).upper()
                    if amount == 1:
                        unit = unit.rstrip("S")
                    else:
                        unit = unit.rstrip("S") + "S"
                    PREMIUM_PLANS[plan_key]["name"] = f"{amount:02d} {unit}"
        try:
            await mdb.save_premium_plans(PREMIUM_PLANS)
        except Exception as exc:
            print(f"premium plan save error: {exc}")
            return await _edit_prompt(
                client,
                state,
                f"<b>💔 ᴄᴏᴜʟᴅ ɴᴏᴛ sᴀᴠᴇ ᴛʜɪs ᴘʟᴀɴ.</b>\n<code>{exc}</code>",
                _premium_input_markup(plan_key, "price" if key == "premium_price" else "duration", state.get("group_id")),
            )
        PENDING.pop((uid, 0), None)
        try: await message.delete()
        except Exception: pass
        group_id = int(state.get("group_id") or 0)
        return await client.edit_message_text(
            state["prompt_chat_id"],
            state["prompt_message_id"],
            _premium_plan_text(plan_key),
            reply_markup=InlineKeyboardMarkup(_premium_plan_buttons(plan_key, group_id)),
            parse_mode=enums.ParseMode.HTML,
        )

    async def _delete_input_message():
        try:
            await message.delete()
        except Exception:
            pass

    if key.startswith("shortner_") and key.endswith("_domain"):
        number = state["number"]
        domain = value.replace("https://", "").replace("http://", "").strip().rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d+)?", domain):
            return await _edit_prompt(
                client, state,
                _cancel_prompt("<b>❌ ɪɴᴠᴀʟɪᴅ ꜱʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ.</b>\n\nꜱᴇɴᴅ ᴏɴʟʏ ᴛʜᴇ ᴅᴏᴍᴀɪɴ, ᴇxᴀᴍᴘʟᴇ: <code>tnshort.net</code>")
            )
        # The domain was accepted. Remove the user's input so the settings
        # conversation stays clean; the prompt message remains for the API step.
        try:
            await message.delete()
        except Exception:
            pass

        state["type"] = f"shortner_{number}_api"
        state["domain"] = domain
        PENDING[(uid, gid)] = state
        return await _edit_prompt(
            client, state,
            _cancel_prompt("<b>sᴇɴᴅ ᴍᴇ ᴀ sʜᴏʀᴛʟɪɴᴋ ᴀᴘɪ...</b>")
        )

    if key.startswith("shortner_") and key.endswith("_api"):
        number = state["number"]
        domain = state["domain"]
        try:
            response = requests.get(f"https://{domain}/api?api={value}&url=https://t.me/", timeout=10)
            payload = response.json()
            if payload.get("status") not in {"success", True}:
                raise RuntimeError(payload.get("message") or "ɪɴᴠᴀʟɪᴅ ꜱʜᴏʀᴛᴇɴᴇʀ ᴏʀ ᴀᴘɪ")
        except Exception as exc:
            return await _edit_prompt(
                client, state,
                f"<b>💔 sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ...</b>\n<code>{exc}</code>",
                InlineKeyboardMarkup([_back(gid, "shortlink_list")])
            )

        domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
        api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
        await save_group_settings(gid, domain_key, domain)
        _invalidate_settings_cache(gid)
        await save_group_settings(gid, api_key, value)
        _invalidate_settings_cache(gid)

        # The bot owner can change the master shortener from any group
        # through /settings -> Shortlink. This updates the owner's global
        # tracking identity, while other group admins remain free to keep
        # their own group shortener without changing what counts as ours.
        if _is_bot_owner(uid):
            await db.set_owner_shortener(number, domain, value)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()
        ordinal = "1ꜱᴛ" if number == 1 else "2ɴᴅ" if number == 2 else "3ʀᴅ"
        return await _edit_prompt(
            client, state,
            f"<b>ᴛʜᴇ {ordinal} ꜱʜᴏʀᴛʟɪɴᴋ ᴡᴀꜱ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇssꜰᴜʟʟʏ ✅</b>",
            InlineKeyboardMarkup([_back(gid, "shortlink_list")])
        )

    if key.startswith("gap_"):
        number = state["number"]
        seconds = _parse_duration(value)
        if seconds is None:
            return await _edit_prompt(
                client, state,
                _cancel_prompt("<b>❌ ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴛɪᴍᴇ ʟɪᴋᴇ <code>1h</code> ᴏʀ <code>15m</code>.</b>")
            )
        setting_key = "verify_time" if number == 1 else "third_verify_time"
        await save_group_settings(gid, setting_key, seconds)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()
        return await _edit_prompt(
            client, state,
            f"<b>ᴛɪᴍᴇ {number} sᴇᴛ ꜱᴜᴄᴄᴇssꜰᴜʟʟʏ ✅</b>",
            InlineKeyboardMarkup([_back(gid, "verification_gap")])
        )

    if key == "delete_time":
        try:
            value_int = int(value)
            assert value_int > 0
        except Exception:
            return await message.reply_text("Send a valid positive number of seconds or /cancel")
        await save_group_settings(gid, "delete_time", value_int)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "max_results":
        try:
            value_int = int(value)
            assert 1 <= value_int <= 20
        except Exception:
            return await message.reply_text("Max results must be between 1 and 20.")
        await save_group_settings(gid, "max_results", value_int)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "template":
        if any(x not in value for x in ("{search}", "{mention}", "{group}")):
            return await message.reply_text("Template must support {search}, {mention}, and {group}, or use /cancel.")
        await save_group_settings(gid, "template", value)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "caption":
        if "{file_name}" not in value:
            return await message.reply_text("Caption must contain {file_name}, or use /cancel.")
        await save_group_settings(gid, "caption", value)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key.startswith("tutorial") or key.startswith("new_shortener_tutorial"):
        if not (value.startswith("http://") or value.startswith("https://")):
            return await message.reply_text("Send a valid http/https URL or /cancel")
        await save_group_settings(gid, key, value)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key in {"shortner", "shortner_two", "shortner_three", "api", "api_two", "api_three", "verify_time", "third_verify_time",
                 "new_shortener_step1_url", "new_shortener_step2_url", "new_shortener_step3_url",
                 "new_shortener_api1", "new_shortener_api2", "new_shortener_api3"}:
        if key.endswith("_url") and value and not (value.startswith("http://") or value.startswith("https://") or "." in value):
            return await message.reply_text("Send a valid URL/domain or /cancel")
        await save_group_settings(gid, key, value)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "request_channel":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        await save_group_settings(gid, key, value_int)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "fsub_label":
        try:
            channel_text, label = value.split("|", 1)
            channel_id = int(channel_text.strip())
            label = label.strip()
            if not label or len(label) > 64:
                raise ValueError
        except (ValueError, TypeError):
            return await message.reply_text("Use: CHANNEL_ID | Button text (1–64 characters).")
        settings = await get_settings(gid)
        channels = {str(k): str(v) for k, v in (settings.get("fsub_button_labels") or {}).items()}
        if channel_id not in [int(c) for c in (settings.get("fsub_channels") or [])]:
            return await message.reply_text("That channel is not configured for this group yet.")
        channels[str(channel_id)] = label
        await save_group_settings(gid, "fsub_button_labels", channels)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "fsub_label_reset":
        try:
            channel_id = int(value.strip())
        except (ValueError, TypeError):
            return await message.reply_text("Send a valid channel ID or /cancel")
        settings = await get_settings(gid)
        channels = {str(k): str(v) for k, v in (settings.get("fsub_button_labels") or {}).items()}
        channels.pop(str(channel_id), None)
        await save_group_settings(gid, "fsub_button_labels", channels)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key.startswith("new_shortener_gap"):
        try:
            gap = int(value)
            if gap < 0 or gap > 86400:
                raise ValueError
        except (ValueError, TypeError):
            return await message.reply_text("Send a number of seconds from 0 to 86400.")
        await save_group_settings(gid, key, gap)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    elif key == "fsub_add":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        settings = await get_settings(gid)
        channels = [int(c) for c in (settings.get("fsub_channels") or [])]
        already_added = value_int in channels
        if not already_added:
            channels.append(value_int)
        details = dict(settings.get("fsub_channel_details") or {})
        channel_title = "Channel title unavailable"
        channel_username = ""
        try:
            chat = await client.get_chat(value_int)
            channel_title = str(getattr(chat, "title", None) or getattr(chat, "first_name", None) or channel_title)
            channel_username = str(getattr(chat, "username", None) or "")
        except Exception:
            # IDs can still be saved when Telegram cannot resolve a private
            # channel; the settings page will clearly show that the title is
            # unavailable rather than pretending the channel was not added.
            pass
        details[str(value_int)] = {"title": channel_title, "username": channel_username}
        await save_group_settings(gid, "fsub_channels", channels)
        await save_group_settings(gid, "fsub_channel_details", details)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()
        status = "already configured" if already_added else "added successfully"
        safe_channel_title = html.escape(channel_title)
        safe_channel_username = html.escape(channel_username)
        await message.reply_text(
            f"✅ <b>Force-subscription channel {status}.</b>\n\n"
            f"Channel: <b>{safe_channel_title}</b>\nID: <code>{value_int}</code>"
            + (f"\nUsername: @{safe_channel_username}" if channel_username else "\nUsername: unavailable/private"),
            parse_mode=enums.ParseMode.HTML,
        )

    elif key == "fsub_delete":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        settings = await get_settings(gid)
        channels = [int(c) for c in (settings.get("fsub_channels") or []) if int(c) != value_int]
        await save_group_settings(gid, "fsub_channels", channels)
        labels = {str(k): v for k, v in (settings.get("fsub_button_labels") or {}).items() if str(k) != str(value_int)}
        details = {str(k): v for k, v in (settings.get("fsub_channel_details") or {}).items() if str(k) != str(value_int)}
        await save_group_settings(gid, "fsub_button_labels", labels)
        await save_group_settings(gid, "fsub_channel_details", details)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    else:
        await save_group_settings(gid, key, value)
        _invalidate_settings_cache(gid)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()

    page = state.get("origin_page", "main")
    try:
        settings = await get_settings(gid)
        if page == "main":
            title = await _group_title(client, gid)
            text = (
                f"🚸 <b>ɢʀᴏᴜᴘ - {title}</b>\n"
                f"🆔️ <b>ɪᴅ - <code>{gid}</code></b>\n\n"
                "sᴇʟᴇᴄᴛ ᴏɴᴇ ᴏꜰ ᴛʜᴇ sᴇᴛᴛɪɴɢs ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ "
                "ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ..."
            )
            buttons = _main_settings_buttons(settings, gid)
        else:
            text = _page_text(page, settings)
            buttons = _page_buttons(page, settings, gid)
        await client.edit_message_text(
            state["prompt_chat_id"],
            state["prompt_message_id"],
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass
