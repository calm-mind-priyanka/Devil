import asyncio
import re
import aiohttp
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
    return "/cancel"


def _cancel_prompt(text):
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

def _main_settings_buttons(settings, grp_id):
    return [
        [
            InlineKeyboardButton("📝 ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ", callback_data=f"set_page#auto_filter#{grp_id}"),
            InlineKeyboardButton("🔒 ꜰɪʟᴇ sᴇᴄᴜʀᴇ", callback_data=f"set_page#file_secure#{grp_id}")
        ],
        [
            InlineKeyboardButton("🈵 ɪᴍᴅʙ", callback_data=f"set_page#imdb#{grp_id}"),
            InlineKeyboardButton("🔍 sᴘᴇʟʟ ᴄʜᴇᴄᴋ", callback_data=f"set_page#spell_check#{grp_id}")
        ],
        [
            InlineKeyboardButton("🗑️ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ", callback_data=f"set_page#auto_delete#{grp_id}"),
            InlineKeyboardButton("📚 ʀᴇsᴜʟᴛ ᴍᴏᴅᴇ", callback_data=f"set_page#link#{grp_id}")
        ],
        [
            InlineKeyboardButton(f"📁 ꜰɪʟᴇ ᴍᴏᴅᴇ · {'ꜰɪʟᴇ 📁' if settings.get('file_mode') else 'ᴠᴇʀɪғʏ ♻️'}", callback_data=f"set_page#file_mode#{grp_id}"),
            InlineKeyboardButton("📑 ꜰɪʟᴇs ᴄᴀᴘᴛɪᴏɴs", callback_data=f"set_page#caption#{grp_id}")
        ],
        [
            InlineKeyboardButton("🥁 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ", callback_data=f"set_page#tutorial#{grp_id}"),
            InlineKeyboardButton("🖇️ sᴇᴛ sʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_page#shortlink#{grp_id}")
        ],
        [
            InlineKeyboardButton("📢 sᴇᴛ ᴍᴏᴠɪᴇ ʀᴇǫ", callback_data=f"set_page#request_channel#{grp_id}"),
            InlineKeyboardButton("ℹ️ ᴅᴇᴛᴀɪʟs", callback_data=f"set_page#details#{grp_id}")
        ],
        [
            InlineKeyboardButton("📢 ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_page#fsub#{grp_id}"),
            InlineKeyboardButton(f"ℹ️ ꜱᴇᴛ ᴍᴀx ʀᴇꜱᴜʟꜱ · {settings.get('max_results', MAX_BTN)}", callback_data=f"set_page#max_results#{grp_id}")
        ],
        [
            InlineKeyboardButton("‼️ ᴄʟᴏsᴇ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ ‼️", callback_data=f"set_close#{grp_id}")
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
        return await (target.reply_text(text) if target.chat.type == enums.ChatType.PRIVATE else target.message.reply_text(text))

    buttons = [[InlineKeyboardButton(f"{title} · {gid}", callback_data=f"set_group#{gid}")] for gid, title in groups]
    markup = InlineKeyboardMarkup(buttons)
    text = "⚙️ <b>ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ɢʀᴏᴜᴘ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴍᴀɴᴀɢᴇ:</b>"

    return await (target.reply_text(text, reply_markup=markup) if target.chat.type == enums.ChatType.PRIVATE else target.message.reply_text(text, reply_markup=markup))


async def show_group_settings(client, target, grp_id):
    user_id = target.from_user.id

    if not await is_check_admin(client, int(grp_id), user_id):
        if hasattr(target, "answer"):
            return await target.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
        return await target.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.</b>")

    settings = await get_settings(int(grp_id))
    title = await _group_title(client, grp_id)

    text = (
        f"🚸 <b>ɢʀᴏᴜᴘ - {title}</b>\n"
        f"🆔️ <b>ɪᴅ - <code>{grp_id}</code></b>\n\n"
        "sᴇʟᴇᴄᴛ ᴏɴᴇ ᴏꜰ ᴛʜᴇ sᴇᴛᴛɪɴɢs ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ "
        "ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ..."
    )
    markup = InlineKeyboardMarkup(_main_settings_buttons(settings, int(grp_id)))

    if hasattr(target, "message"):
        return await target.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
    return await target.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)


# ============================================================
# PAGE TEXTS & SHORTLINKS
# ============================================================

def _page_text(key, settings):
    if key == "auto_filter":
        state = "ᴏɴ ✅" if settings.get("auto_filter") else "ᴏꜰꜰ ❌"
        return f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ ᴍᴏᴅᴇ ᴍᴇᴀɴs ʙᴏᴛ sᴇɴᴅ ʀᴇsᴜʟᴛ ɪɴ ɢʀᴏᴜᴘ ᴏʀ ɴᴏᴛ...ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ - {state}</b>"
    if key == "file_secure":
        state = "ᴏɴ ✅" if settings.get("file_secure") else "ᴏꜰꜰ ❌"
        return f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇs ᴘʀᴏᴛᴇᴄᴛɪᴏɴ, ᴍᴇᴀɴs ᴡʜᴇᴛʜᴇʀ ᴜsᴇʀs ᴄᴀɴ ꜰᴏʀᴡᴀʀᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴏʀ ɴᴏᴛ...ᴘʀᴏᴛᴇᴄᴛ - {state}</b>"
    if key == "imdb":
        return f"<b>🎬 IMDB</b>\n\nPoster: {'ON ✅' if settings.get('imdb') else 'OFF ❌'}\n\n<code>{settings.get('template', IMDB_TEMPLATE)}</code>"
    if key == "spell_check":
        state = "ᴏɴ ✅" if settings.get("spell_check") else "ᴏꜰꜰ ❌"
        return f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʙᴏᴛ sᴘᴇʟʟɪɴɢ ᴄʜᴇᴄᴋ ᴍᴇssᴀɢᴇ sᴘᴇʟʟ ᴄʜᴇᴄᴋ - {state}</b>"
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
            f"Max results: <code>{settings.get('max_results', MAX_BTN)}</code>"
        )
    return "<b>Settings</b>"


def _shortlink_master_text(settings):
    state = "ᴏɴ ✅" if settings.get("is_verify") else "ᴏꜰꜰ ❌"
    return f"⚙️ <b>ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ</b>\nʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜱʜᴏʀᴛʟɪɴᴋꜱ ᴀɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴇᴛᴛɪɴɢꜱ ꜰʀᴏᴍ ʜᴇʀᴇ.\n<b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ 👇</b>\n✅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ : {state}"


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
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 1ꜱᴛ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner')}</code>\n<code>{val('api')}</code>\n"
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 2ɴᴅ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner_two')}</code>\n<code>{val('api_two')}</code>\n"
        f"<b>[ᴅᴇꜰᴀᴜʟᴛ] 3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ</b> - <code>{val('shortner_three')}</code>\n<code>{val('api_three')}</code>"
    )


def _shortlink_list_buttons(grp_id):
    return [
        [InlineKeyboardButton("1ꜱᴛ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#1#{grp_id}"), InlineKeyboardButton("2ɴᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#2#{grp_id}")],
        [InlineKeyboardButton("3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_shortner#3#{grp_id}")],
        [InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"set_delete_shortner#menu#{grp_id}")],
        _back(grp_id, "shortlink"),
    ]


def _verification_gap_text(settings):
    verify_on = "ᴏɴ ✅" if settings.get("is_verify") else "ᴏꜰꜰ ❌"
    return f"<b>ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴘʀᴏᴄᴇss sᴇᴛᴛɪɴɢs.</b>\n\n2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ - {verify_on}\nᴛɪᴍᴇ - <code>{get_readable_time(settings.get('verify_time', TWO_VERIFY_GAP))}</code>"


def _verification_gap_buttons(grp_id):
    return [
        [InlineKeyboardButton("ᴛɪᴍᴇ 1", callback_data=f"set_gap#1#{grp_id}"), InlineKeyboardButton("ᴛɪᴍᴇ 2", callback_data=f"set_gap#2#{grp_id}")],
        _back(grp_id, "shortlink"),
    ]


def _shortener_settings_text(settings, number):
    domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
    api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
    return f"<b>ꜱʜᴏʀᴛᴇɴᴇʀ {number} ꜱᴇᴛᴛɪɴɢꜱ:</b>\n\n🌐 ᴅᴏᴍᴀɪɴ: <code>{settings.get(domain_key) or 'ɴᴏᴛ ꜱᴇᴛ'}</code>\n🔗 ᴀᴘɪ: <code>{settings.get(api_key) or 'ɴᴏᴛ ꜱᴇᴛ'}</code>"


def _shortener_settings_buttons(grp_id, number):
    return [
        [InlineKeyboardButton("ꜱᴇᴛ", callback_data=f"set_shortner_action#set#{number}#{grp_id}"), InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"set_shortner_action#remove#{number}#{grp_id}")],
        _back(grp_id, "shortlink_list"),
    ]


def _delete_menu_text(settings):
    return "<b>ᴡʜɪᴄʜ ꜱʜᴏʀᴛᴇɴᴇʀ ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ?</b>"


def _delete_menu_buttons(settings, grp_id):
    return [
        [InlineKeyboardButton("ꜰɪʀꜱᴛ", callback_data=f"set_delete_shortner#1#{grp_id}"), InlineKeyboardButton("ꜱᴇᴄᴏɴᴅ", callback_data=f"set_delete_shortner#2#{grp_id}"), InlineKeyboardButton("ᴛʜɪʀᴅ", callback_data=f"set_delete_shortner#3#{grp_id}")],
        [InlineKeyboardButton("ᴀʟʟ", callback_data=f"set_delete_shortner#all#{grp_id}")],
        _back(grp_id, "shortlink_list")
    ]


def _time_page_text(settings, number):
    gap = settings.get("verify_time" if number == 1 else "third_verify_time", TWO_VERIFY_GAP)
    return f"<b>ᴍᴀɴᴀɢᴇ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ {number}.</b>\n\nᴛɪᴍᴇ - <code>{get_readable_time(gap)}</code>"


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
            b.append([InlineKeyboardButton("⏱️ sᴇᴛ ᴛִᴍᴇ", callback_data=f"set_input#delete_time#{grp_id}")])

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
        b = [[InlineKeyboardButton("sᴇᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data=f"set_input#template#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ", callback_data=f"set_default#template#{grp_id}")],
             [InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ ᴘᴏsᴛᴇʀ", callback_data=f"set_toggle#imdb#{grp_id}")]
        ]
    elif key == "caption":
        b = [[InlineKeyboardButton("sᴇᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"set_input#caption#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ", callback_data=f"set_default#caption#{grp_id}")]]
    elif key == "tutorial":
        b = [[InlineKeyboardButton("sᴇᴛ 1", callback_data=f"set_input#tutorial#{grp_id}"), InlineKeyboardButton("sᴇᴛ 2", callback_data=f"set_input#tutorial_2#{grp_id}")]]
    elif key == "request_channel":
        b = [[InlineKeyboardButton("sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#request_channel#{grp_id}"), InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ", callback_data=f"set_delete#request_channel#{grp_id}")]]
    elif key == "fsub":
        b = [[InlineKeyboardButton("sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"set_input#fsub_add#{grp_id}"), InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ", callback_data=f"set_input#fsub_delete#{grp_id}")]]
    elif key == "max_results":
        b = [[InlineKeyboardButton("sᴇᴛ ᴍᴀx", callback_data=f"set_input#max_results#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ", callback_data=f"set_default#max_results#{grp_id}")]]
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
        return await is_check_admin(client, int(grp_id), query.from_user.id)
    except Exception:
        return False


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
            state["prompt_chat_id"], state["prompt_message_id"],
            text, reply_markup=markup, parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        return None


def _parse_duration(value):
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", value.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] if n > 0 else None


# ============================================================
# CALLBACK & MESSAGE HANDLERS
# ============================================================

@Client.on_callback_query(filters.regex(r"^(set_|advanced_settings)"))
async def settings_callback(client, query):
    # INSTANT RESPONSIVENESS: Clear the loading animation immediately
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    try:
        if data.startswith("set_group#"):
            gid = int(data.split("#", 1)[1])
            if not await _authorize(client, query, gid):
                return await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
            return await show_group_settings(client, query, gid)

        if data.startswith("advanced_settings"):
            gid = int(data.split("#")[1]) if "#" in data else None
            if not gid:
                return await show_group_list(client, query)
            if not await _authorize(client, query, gid):
                return await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
            return await show_group_settings(client, query, gid)

        parts = data.split("#")
        action = parts[0]

        if action in {"set_page", "set_toggle", "set_input", "set_default", "set_delete", "set_file_mode", "set_back"}:
            key = parts[1]
            gid = int(parts[2])
        elif action in {"set_shortner", "set_shortner_action", "set_delete_shortner", "set_gap", "set_gap_input"}:
            key = parts[1]
            gid = int(parts[-1])
        elif action == "set_close":
            gid = int(parts[1])
            PENDING.pop((query.from_user.id, gid), None)
            return await query.message.delete()
        else:
            gid = int(parts[1]) if len(parts) > 1 else 0
            key = parts[1] if len(parts) > 1 else ""

        if not await _authorize(client, query, gid):
            return await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)

        if action == "set_page":
            return await show_page(client, query, key, gid)

        if action == "set_back":
            PENDING.pop((query.from_user.id, gid), None)
            if key == "main":
                return await show_group_settings(client, query, gid)
            return await show_page(client, query, key, gid)

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
            await save_group_settings(gid, key, not bool(settings.get(key)))
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
            origin_page_map = {
                "delete_time": "auto_delete", "template": "imdb", "caption": "caption",
                "max_results": "max_results", "request_channel": "request_channel",
                "fsub_add": "fsub", "fsub_delete": "fsub"
            }
            origin_page = (
                "shortlink_list" if key in {"shortner", "shortner_two", "shortner_three"}
                else "verification_gap" if key in {"verify_time", "third_verify_time"}
                else "tutorial" if key in {"tutorial", "tutorial_2", "tutorial_3"}
                else origin_page_map.get(key, "main")
            )
            state = _prompt_state(query, gid, key, origin_page)
            prompt = "sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴠᴀʟᴜᴇ."
            return await _edit_prompt(client, state, _cancel_prompt(f"<b>{prompt}</b>"))

        if action == "set_shortner":
            return await show_page(client, query, "shortener", gid, int(key))

        if action == "set_shortner_action":
            mode, number = parts[1], int(parts[2])
            if mode == "set":
                state = _prompt_state(query, gid, f"shortner_{number}_domain", "shortlink_list", number=number)
                return await _edit_prompt(client, state, _cancel_prompt("<b>ꜱᴇɴᴅ ᴍᴇ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴡɪᴛʜᴏᴜᴛ https:</b>\n\n<code>tnshort.net</code> ✅"))

            domain_key = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            api_key = {1: "api", 2: "api_two", 3: "api_three"}[number]
            await save_group_settings(gid, domain_key, "")
            await save_group_settings(gid, api_key, "")
            return await show_page(client, query, "shortener", gid, number)

        if action == "set_delete_shortner":
            if key == "menu":
                return await show_page(client, query, "delete_menu", gid)
            if key == "all":
                for dk, ak in (("shortner", "api"), ("shortner_two", "api_two"), ("shortner_three", "api_three")):
                    await save_group_settings(gid, dk, "")
                    await save_group_settings(gid, ak, "")
                return await query.message.edit_text("<b>ᴅᴇʟᴇᴛᴇ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅</b>", reply_markup=InlineKeyboardMarkup([_back(gid, "shortlink_list")]), parse_mode=enums.ParseMode.HTML)

            number = int(key)
            dk = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
            ak = {1: "api", 2: "api_two", 3: "api_three"}[number]
            await save_group_settings(gid, dk, "")
            await save_group_settings(gid, ak, "")
            return await show_page(client, query, "delete_menu", gid)

        if action == "set_gap":
            return await show_page(client, query, "time_page", gid, int(key))

        if action == "set_gap_input":
            number = int(key)
            state = _prompt_state(query, gid, f"gap_{number}", "verification_gap", number=number)
            return await _edit_prompt(client, state, _cancel_prompt("<b>ꜱᴇɴᴅ ᴍᴇ ᴀ ᴛɪᴍᴇ ʟɪᴋᴇ <code>1h</code> ᴏʀ <code>15m</code></b>"))

    except Exception as exc:
        print(f"settings callback error: {exc}")


@Client.on_message(filters.text & ~filters.command(["cancel"]))
async def advanced_input(client, message):
    uid = message.from_user.id if message.from_user else None
    if not uid:
        raise ContinuePropagation

    candidates = [(k, v) for k, v in PENDING.items() if k[0] == uid]
    if not candidates:
        raise ContinuePropagation

    (user_id, gid), state = candidates[-1]
    if not await is_check_admin(client, gid, uid):
        PENDING.pop((user_id, gid), None)
        raise ContinuePropagation

    value = message.text.strip()
    if not value:
        return

    key = state["type"]

    async def _delete_input_message():
        try:
            await message.delete()
        except Exception:
            pass

    # OPTIMIZED: Fully asynchronous non-blocking HTTP request using aiohttp
    if key.startswith("shortner_") and key.endswith("_domain"):
        number = state["number"]
        domain = value.replace("https://", "").replace("http://", "").strip().rstrip("/")
        state["type"] = f"shortner_{number}_api"
        state["domain"] = domain
        PENDING[(uid, gid)] = state
        await _delete_input_message()
        return await _edit_prompt(client, state, _cancel_prompt("<b>sᴇɴᴅ ᴍᴇ ᴀ sʜᴏʀᴛʟɪɴᴋ ᴀᴘɪ...</b>"))

    if key.startswith("shortner_") and key.endswith("_api"):
        number = state["number"]
        domain = state["domain"]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://{domain}/api?api={value}&url=https://t.me/", timeout=10) as resp:
                    payload = await resp.json()
                    if payload.get("status") not in {"success", True}:
                        raise RuntimeError("Invalid API Key")
        except Exception as exc:
            return await _edit_prompt(client, state, f"<b>💔 sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ...</b>\n<code>{exc}</code>", InlineKeyboardMarkup([_back(gid, "shortlink_list")]))

        dk = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[number]
        ak = {1: "api", 2: "api_two", 3: "api_three"}[number]
        await save_group_settings(gid, dk, domain)
        await save_group_settings(gid, ak, value)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()
        return await _edit_prompt(client, state, f"<b>ꜱʜᴏʀᴛʟɪɴᴋ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅</b>", InlineKeyboardMarkup([_back(gid, "shortlink_list")]))

    if key.startswith("gap_"):
        seconds = _parse_duration(value)
        if seconds is None:
            return await _edit_prompt(client, state, _cancel_prompt("<b>❌ ᴠᴀʟɪᴅ ᴛɪᴍᴇ ʟɪᴋᴇ <code>1h</code> ᴏʀ <code>15m</code>.</b>"))
        await save_group_settings(gid, "verify_time" if state["number"] == 1 else "third_verify_time", seconds)
        PENDING.pop((uid, gid), None)
        await _delete_input_message()
        return await _edit_prompt(client, state, f"<b>ᴛɪᴍᴇ sᴇᴛ sᴜᴄᴄᴇssꜰᴜʟʟʏ ✅</b>", InlineKeyboardMarkup([_back(gid, "verification_gap")]))

    # Default general saving mechanism
    await save_group_settings(gid, key, int(value) if value.isdigit() else value)
    PENDING.pop((uid, gid), None)
    await _delete_input_message()

    page = state.get("origin_page", "main")
    try:
        settings = await get_settings(gid)
        text = _page_text(page, settings) if page != "main" else f"🚸 <b>ɢʀᴏᴜᴘ - {await _group_title(client, gid)}</b>"
        buttons = _page_buttons(page, settings, gid) if page != "main" else _main_settings_buttons(settings, gid)
        await client.edit_message_text(state["prompt_chat_id"], state["prompt_message_id"], text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
