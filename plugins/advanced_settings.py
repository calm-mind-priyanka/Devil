import asyncio
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


# ============================================================
# PER-USER PENDING INPUT
# ============================================================

PENDING = {}  # Keys are (user_id, group_id)


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


def _cancel_text():
    return _small("/cancel - cancel this process.")


def _cancel_button(group_id):
    return [
        InlineKeyboardButton(
            "ᴄᴀɴᴄᴇʟ ❌",
            callback_data=f"set_cancel#{group_id}"
        )
    ]


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

def _main_settings_buttons(settings, grp_id):

    def onoff(key):
        return "ON ✅" if settings.get(key) else "OFF ❌"

    return [
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
                f"🎬 ɪᴍᴅʙ",
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
                f"📁 ꜰɪʟᴇ ᴍᴏᴅᴇ · {'ꜰɪʟᴇ 📁' if settings.get('file_mode') else 'ᴠᴇʀɪғʏ ♻️'}",
                callback_data=f"set_page#file_mode#{grp_id}"
            ),
            InlineKeyboardButton(
                "📝 ꜰɪʟᴇs ᴄᴀᴘᴛɪᴏɴs",
                callback_data=f"set_page#caption#{grp_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🎬 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ",
                callback_data=f"set_page#tutorial#{grp_id}"
            ),
            InlineKeyboardButton(
                "🖇️ ꜱʜᴏʀᴛʟɪɴᴋs",
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
        [
            InlineKeyboardButton(
                "📢 ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ",
                callback_data=f"set_page#fsub#{grp_id}"
            ),
            InlineKeyboardButton(
                f"🔢 SET MAX RESULTS · {settings.get('max_results', MAX_BTN)}",
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


# ============================================================
# GROUP LIST & SETTINGS
# ============================================================

async def show_group_list(client, target, direct_group_id=None):
    user_id = target.from_user.id
    groups = []

    async for chat in db.get_all_chats():
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
        text = "❌ <b>ɪ ᴄᴏᴜʟᴅ ɴᴏᴛ ғɪɴᴅ ᴀɴʏ ɢʀᴏᴜᴘs ᴡʜᴇʀᴇ ʏᴏᴜ ᴀʀᴇ ᴀɴ ᴀᴅᴍɪɴ.</b>"
        if target.chat.type == enums.ChatType.PRIVATE:
            return await target.reply_text(text)
        return await target.message.reply_text(text)

    buttons = [
        [InlineKeyboardButton(f"{title} · {gid}", callback_data=f"set_group#{gid}")]
        for gid, title in groups
    ]
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

    settings = await get_settings(int(grp_id))
    title = await _group_title(client, grp_id)

    text = (
        f"<b>⚙️ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs</b>\n\n"
        f"<b>ɴᴀᴍᴇ:</b> {title}\n"
        f"<b>ɪᴅ:</b> <code>{grp_id}</code>"
    )
    markup = InlineKeyboardMarkup(_main_settings_buttons(settings, int(grp_id)))

    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        return

    await target.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)


# ============================================================
# PAGE TEXTS & SHORTLINKS
# ============================================================

def _page_text(key, settings):
    if key == "auto_filter":
        return "<b>📝 AUTO FILTER</b>\n\nAuto Filter searches indexed files for messages sent in the group."
    if key == "file_secure":
        return "<b>🔒 FILE SECURE</b>\n\nProtect delivered files from forwarding/saving where Telegram supports protect_content."
    if key == "imdb":
        return f"<b>🎬 IMDB</b>\n\nPoster: {'ON ✅' if settings.get('imdb') else 'OFF ❌'}\n\n<code>{settings.get('template', IMDB_TEMPLATE)}</code>"
    if key == "spell_check":
        return "<b>🔍 SPELL CHECK</b>\n\nCorrect common spelling variations before searching."
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
        channels = settings.get("fsub_channels") or [settings.get("fsub_id", AUTH_CHANNEL)]
        return "<b>📢 FORCE CHANNEL</b>\n\nMultiple force-subscribe channels are supported.\n\n" + "\n".join(f"• <code>{c}</code>" for c in channels)
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
        b = [[
            InlineKeyboardButton("sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#fsub_add#{grp_id}"),
            InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#fsub_delete#{grp_id}")
        ]]
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
    settings = await get_settings(int(grp_id))

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
    try:
        ok = await is_check_admin(client, int(grp_id), query.from_user.id)
    except Exception:
        ok = False

    if not ok:
        await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
        return False
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


def _parse_duration(value):
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
            return await show_group_settings(client, query, gid)

        if action == "set_file_mode":
            mode = key if key in {"verify", "shortlink"} else "verify"
            await save_group_settings(gid, "file_mode", True)
            await save_group_settings(gid, "file_mode_type", mode)
            return await show_page(client, query, "file_mode", gid)

        if action == "set_toggle":
            settings = await get_settings(gid)
            value = not bool(settings.get(key))
            await save_group_settings(gid, key, value)
            if len(parts) > 3 and parts[3] == "shortlink":
                return await show_page(client, query, "shortlink", gid)
            return await show_page(client, query, key, gid)

        if action == "set_default":
            defaults = db.default.copy()
            await save_group_settings(gid, key, int(MAX_BTN) if key == "max_results" else defaults.get(key, ""))
            return await show_page(client, query, key, gid)

        if action == "set_delete":
            if key == "request_channel":
                await save_group_settings(gid, key, int(REQUEST_CHANNEL))
            return await show_page(client, query, key, gid)

        if action == "set_input":
            origin_page = ("shortlink_list" if key in {"shortner", "shortner_two", "shortner_three"} else ("verification_gap" if key in {"verify_time", "third_verify_time"} else ("tutorial" if key in {"tutorial", "tutorial_2", "tutorial_3"} else "main")))
            state = _prompt_state(query, gid, key, origin_page)
            prompt = {
                "delete_time": "sᴇɴᴅ ᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ ɪɴ sᴇᴄᴏɴᴅs.",
                "template": "sᴇɴᴅ ʏᴏᴜʀ ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ. sᴜᴘᴘᴏʀᴛᴇᴅ: {search}, {mention}, {group}",
                "caption": "sᴇɴᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ. sᴜᴘᴘᴏʀᴛᴇᴅ: {file_name}",
                "max_results": "sᴇɴᴅ ᴍᴀx ʀᴇsᴜʟᴛs ꜰʀᴏᴍ 1 ᴛᴏ 20.",
                "request_channel": "sᴇɴᴅ ʀᴇǫᴜᴇsᴛ ᴄʜᴀɴɴᴇʟ ɪᴅ.",
                "fsub_add": "sᴇɴᴅ ꜰᴏʀᴄᴇ-sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ.",
                "fsub_delete": "sᴇɴᴅ ᴛʜᴇ ꜰᴏʀᴄᴇ-sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ.",
                "tutorial": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 1 ᴜʀʟ.",
                "tutorial_2": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 2 ᴜʀʟ.",
                "tutorial_3": "sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ 3 ᴜʀʟ.",
            }.get(key, "sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴠᴀʟᴜᴇ.")

            return await _edit_prompt(
                client, state,
                f"<b>{prompt}</b>\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
                InlineKeyboardMarkup([_cancel_button(gid)])
            )

        if action == "set_cancel":
            PENDING.pop((query.from_user.id, gid), None)
            return await show_group_settings(client, query, gid)

        if action == "set_shortner":
            return await show_page(client, query, "shortener", gid, int(key))

        if action == "set_shortner_action":
            mode = parts[1]
            number = int(parts[2])
            if mode == "set":
                state = _prompt_state(query, gid, f"shortner_{number}_domain", "shortlink_list", number=number)
                return await _edit_prompt(
                    client, state,
                    "<b>ꜱᴇɴᴅ ᴍᴇ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴡɪᴛʜᴏᴜᴛ https ꜰᴏʀᴍᴀᴛ -</b>\n\n<code>https://tnshort.net</code> ❌\n<code>tnshort.net</code> ✅\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
                    InlineKeyboardMarkup([_cancel_button(gid)])
                )

            domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
            await save_group_settings(gid, domain_key, "")
            await save_group_settings(gid, api_key, "")
            return await show_page(client, query, "shortener", gid, number)

        if action == "set_delete_shortner":
            if key == "menu":
                return await show_page(client, query, "delete_menu", gid)
            if key == "all":
                for domain_key, api_key in (("shortner", "api"), ("shortner_two", "api_two"), ("shortner_three", "api_three")):
                    await save_group_settings(gid, domain_key, "")
                    await save_group_settings(gid, api_key, "")
                return await query.message.edit_text(
                    "<b>ᴅᴇʟᴇᴛᴇ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅</b>",
                    reply_markup=InlineKeyboardMarkup([_back(gid, "shortlink_list")]),
                    parse_mode=enums.ParseMode.HTML
                )

            number = int(key)
            domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
            settings = await get_settings(gid)

            if not settings.get(domain_key) or not settings.get(api_key):
                return await query.message.edit_text(
                    "<b>💔 ꜰɪʀꜱᴛ ᴀᴅᴅ ᴛʜɪs ꜱʜᴏʀᴛᴇɴᴇʀ ꜰᴏʀ ᴅᴇʟᴇᴛɪᴏɴ.</b>",
                    reply_markup=InlineKeyboardMarkup([_back(gid, "delete_menu")]),
                    parse_mode=enums.ParseMode.HTML
                )

            await save_group_settings(gid, domain_key, "")
            await save_group_settings(gid, api_key, "")
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
                "<b>ꜱᴇɴᴅ ᴍᴇ ᴀ ᴛɪᴍᴇ ɪɴ ʟɪᴋᴇ ᴛʜɪs -</b> <code>1h</code> ᴏʀ <code>15m</code>\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
                InlineKeyboardMarkup([_cancel_button(gid)])
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

    try:
        await message.delete()
    except Exception:
        pass

    try:
        if page == "shortlink_list":
            settings = await get_settings(gid)
            await client.edit_message_text(
                state["prompt_chat_id"], state["prompt_message_id"],
                _shortlink_list_text(settings),
                reply_markup=InlineKeyboardMarkup(_shortlink_list_buttons(gid)),
                parse_mode=enums.ParseMode.HTML
            )
        elif page == "verification_gap":
            settings = await get_settings(gid)
            await client.edit_message_text(
                state["prompt_chat_id"], state["prompt_message_id"],
                _verification_gap_text(settings),
                reply_markup=InlineKeyboardMarkup(_verification_gap_buttons(gid)),
                parse_mode=enums.ParseMode.HTML
            )
        elif page != "main":
            await client.edit_message_text(
                state["prompt_chat_id"], state["prompt_message_id"],
                _page_text(page, await get_settings(gid)),
                reply_markup=InlineKeyboardMarkup(_page_buttons(page, await get_settings(gid), gid)),
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await show_group_settings(client, message, gid)
    except Exception:
        await message.reply_text("<b>ᴄᴀɴᴄᴇʟʟᴇᴅ ✅</b>")


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

    if not await is_check_admin(client, gid, uid):
        PENDING.pop((user_id, gid), None)
        raise ContinuePropagation

    value = message.text.strip()
    if not value:
        return await message.reply_text("ᴠᴀʟᴜᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ")

    key = state["type"]

    if key.startswith("shortner_") and key.endswith("_domain"):
        number = state["number"]
        domain = value.replace("https://", "").replace("http://", "").strip().rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d+)?", domain):
            return await _edit_prompt(
                client, state,
                "<b>❌ ɪɴᴠᴀʟɪᴅ ꜱʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ.</b>\n\nꜱᴇɴᴅ ᴏɴʟʏ ᴛʜᴇ ᴅᴏᴍᴀɪɴ, ᴇxᴀᴍᴘʟᴇ: <code>tnshort.net</code>\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
                InlineKeyboardMarkup([_cancel_button(gid)])
            )
        state["type"] = f"shortner_{number}_api"
        state["domain"] = domain
        PENDING[(uid, gid)] = state
        return await _edit_prompt(
            client, state,
            "<b>sᴇɴᴅ ᴍᴇ ᴀ sʜᴏʀᴛʟɪɴᴋ ᴀᴘɪ...</b>\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
            InlineKeyboardMarkup([_cancel_button(gid)])
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
        await save_group_settings(gid, api_key, value)
        PENDING.pop((uid, gid), None)
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
                "<b>❌ ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴛɪᴍᴇ ʟɪᴋᴇ <code>1h</code> ᴏʀ <code>15m</code>.</b>\n\n<b>/ᴄᴀɴᴄᴇʟ</b> - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.",
                InlineKeyboardMarkup([_cancel_button(gid)])
            )
        setting_key = "verify_time" if number == 1 else "third_verify_time"
        await save_group_settings(gid, setting_key, seconds)
        PENDING.pop((uid, gid), None)
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
        PENDING.pop((uid, gid), None)

    elif key == "max_results":
        try:
            value_int = int(value)
            assert 1 <= value_int <= 20
        except Exception:
            return await message.reply_text("Max results must be between 1 and 20.")
        await save_group_settings(gid, "max_results", value_int)
        PENDING.pop((uid, gid), None)

    elif key == "template":
        if any(x not in value for x in ("{search}", "{mention}", "{group}")):
            return await message.reply_text("Template must support {search}, {mention}, and {group}, or use /cancel.")
        await save_group_settings(gid, "template", value)
        PENDING.pop((uid, gid), None)

    elif key == "caption":
        if "{file_name}" not in value:
            return await message.reply_text("Caption must contain {file_name}, or use /cancel.")
        await save_group_settings(gid, "caption", value)
        PENDING.pop((uid, gid), None)

    elif key.startswith("tutorial"):
        if not (value.startswith("http://") or value.startswith("https://")):
            return await message.reply_text("Send a valid http/https URL or /cancel")
        await save_group_settings(gid, key, value)
        PENDING.pop((uid, gid), None)

    elif key in {"shortner", "shortner_two", "shortner_three", "api", "api_two", "api_three", "verify_time", "third_verify_time"}:
        await save_group_settings(gid, key, value)
        PENDING.pop((uid, gid), None)

    elif key == "request_channel":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        await save_group_settings(gid, key, value_int)
        PENDING.pop((uid, gid), None)

    elif key == "fsub_add":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        settings = await get_settings(gid)
        channels = list(settings.get("fsub_channels") or [])
        if value_int not in channels:
            channels.append(value_int)
        await save_group_settings(gid, "fsub_channels", channels)
        PENDING.pop((uid, gid), None)

    elif key == "fsub_delete":
        try:
            value_int = int(value)
        except ValueError:
            return await message.reply_text("Send a valid channel ID or /cancel")
        settings = await get_settings(gid)
        channels = [int(c) for c in (settings.get("fsub_channels") or []) if int(c) != value_int]
        if not channels:
            channels = [AUTH_CHANNEL]
        await save_group_settings(gid, "fsub_channels", channels)
        PENDING.pop((uid, gid), None)

    else:
        await save_group_settings(gid, key, value)
        PENDING.pop((uid, gid), None)

    page = state.get("origin_page", "main")
    try:
        settings = await get_settings(gid)
        if page == "main":
            title = await _group_title(client, gid)
            text = (
                f"<b>⚙️ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs</b>\n\n"
                f"<b>ɴᴀᴍᴇ:</b> {title}\n"
                f"<b>ɪᴅ:</b> <code>{gid}</code>"
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
