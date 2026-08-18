import asyncio
import requests
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import *
from utils import get_settings, save_group_settings, is_check_admin, get_readable_time
from database.users_chats_db import db

# Temporary per-admin conversation state. The actual values are stored in MongoDB.
PENDING = {}


def _cancel_button():
    return [InlineKeyboardButton("/cancel", callback_data="adv_cancel")]


def _back(callback):
    return [InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=callback)]


def _main_settings_buttons(settings, grp_id):
    return [
        [
            InlineKeyboardButton("ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ", callback_data=f"setgs#auto_filter#{settings['auto_filter']}#{grp_id}"),
            InlineKeyboardButton("ᴏɴ ✓" if settings["auto_filter"] else "ᴏғғ ✗", callback_data=f"setgs#auto_filter#{settings['auto_filter']}#{grp_id}"),
        ],
        [
            InlineKeyboardButton("ɪᴍᴅʙ", callback_data=f"setgs#imdb#{settings['imdb']}#{grp_id}"),
            InlineKeyboardButton("ᴏɴ ✓" if settings["imdb"] else "ᴏғғ ✗", callback_data=f"setgs#imdb#{settings['imdb']}#{grp_id}"),
        ],
        [
            InlineKeyboardButton("sᴘᴇʟʟ ᴄʜᴇᴄᴋ", callback_data=f"setgs#spell_check#{settings['spell_check']}#{grp_id}"),
            InlineKeyboardButton("ᴏɴ ✓" if settings["spell_check"] else "ᴏғғ ✗", callback_data=f"setgs#spell_check#{settings['spell_check']}#{grp_id}"),
        ],
        [
            InlineKeyboardButton("ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ", callback_data=f"setgs#auto_delete#{settings['auto_delete']}#{grp_id}"),
            InlineKeyboardButton(get_readable_time(DELETE_TIME) if settings["auto_delete"] else "ᴏғғ ✗", callback_data=f"setgs#auto_delete#{settings['auto_delete']}#{grp_id}"),
        ],
        [
            InlineKeyboardButton("ʀᴇsᴜʟᴛ ᴍᴏᴅᴇ", callback_data=f"setgs#link#{settings['link']}#{grp_id}"),
            InlineKeyboardButton("⛓ ʟɪɴᴋ" if settings["link"] else "🧲 ʙᴜᴛᴛᴏɴ", callback_data=f"setgs#link#{settings['link']}#{grp_id}"),
        ],
        [InlineKeyboardButton("🔗 sʜᴏʀᴛʟɪɴᴋ", callback_data="advanced_settings")],
        [InlineKeyboardButton("❌ ᴄʟᴏsᴇ ❌", callback_data="close_data")],
    ]


async def show_main_settings(query, grp_id):
    settings = await get_settings(grp_id)
    title = query.message.chat.title or "Group"
    await query.message.edit_text(
        f"ᴄʜᴀɴɢᴇ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ <b>'{title}'</b> ᴀs ʏᴏᴜʀ ᴡɪsʜ ✨",
        reply_markup=InlineKeyboardMarkup(_main_settings_buttons(settings, grp_id)),
        parse_mode=enums.ParseMode.HTML,
    )


async def show_advanced(query, grp_id):
    settings = await get_settings(grp_id)
    status = "ᴏɴ" if settings.get("is_verify") else "ᴏꜰꜰ"
    text = (
        "<b>⚙️ ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ</b>\n"
        "ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜱʜᴏʀᴛʟɪɴᴋꜱ ᴀɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴇᴛᴛɪɴɢꜱ ꜰʀᴏᴍ ʜᴇʀᴇ.\n\n"
        "<b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ 👇</b>\n"
        f"<b>✅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ : {status}</b>"
    )
    buttons = [
        [InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ" if settings.get("is_verify") else "ᴛᴜʀɴ ᴏɴ", callback_data="adv_toggle_verify")],
        [InlineKeyboardButton("🔗 sʜᴏʀᴛʟɪɴᴋ", callback_data="adv_shortlinks")],
        [InlineKeyboardButton("⏱ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ɢᴀᴘ", callback_data="adv_gaps")],
        [InlineKeyboardButton("📹 ᴛᴜᴛᴏʀɪᴀʟ", callback_data="adv_tutorials")],
        _back("adv_back_settings"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_shortlinks(query, grp_id):
    settings = await get_settings(grp_id)
    lines = [
        "<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴠᴇʀɪꜰʏ ᴍᴏᴅᴇ</b>",
        "<b>ꜱᴇᴛ ʏᴏᴜʀ 1ꜱᴛ, 2ɴᴅ ᴀɴᴅ 3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ...</b>",
    ]
    for label, domain, api in (
        ("1ꜱᴛ", settings.get("shortner"), settings.get("api")),
        ("2ɴᴅ", settings.get("shortner_two"), settings.get("api_two")),
        ("3ʀᴅ", settings.get("shortner_three"), settings.get("api_three")),
    ):
        if domain or api:
            lines.append(f"<b>ꜱʜᴏʀᴛʟɪɴᴋ {label}</b> - <code>{domain or ''}</code> <code>{api or ''}</code>")
    buttons = [
        [InlineKeyboardButton("1sᴛ sʜᴏʀᴛʟɪɴᴋ", callback_data="adv_short#1"), InlineKeyboardButton("2ɴᴅ sʜᴏʀᴛʟɪɴᴋ", callback_data="adv_short#2")],
        [InlineKeyboardButton("3ʀᴅ sʜᴏʀᴛʟɪɴᴋ", callback_data="adv_short#3")],
        _back("adv_back_advanced"),
    ]
    await query.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_short_detail(query, grp_id, slot):
    settings = await get_settings(grp_id)
    key_domain = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[slot]
    key_api = {1: "api", 2: "api_two", 3: "api_three"}[slot]
    domain, api = settings.get(key_domain), settings.get(key_api)
    text = f"<b>ꜱʜᴏʀᴛᴇɴᴇʀ {slot} ꜱᴇᴛᴛɪɴɢꜱ:</b>"
    if domain or api:
        text += f"\n🌐 ᴅᴏᴍᴀɪɴ: <code>{domain or ''}</code>\n🔗 ᴀᴘɪ: <code>{api or ''}</code>"
    buttons = [
        [InlineKeyboardButton("sᴇᴛ", callback_data=f"adv_setshort#{slot}"), InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"adv_remshort#{slot}")],
        _back("adv_shortlinks"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_gaps(query, grp_id):
    settings = await get_settings(grp_id)
    text = "<b>ᴄʜᴏᴏꜱᴇ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ ᴛᴏ ᴍᴀɴᴀɢᴇ:</b>"
    buttons = [
        [InlineKeyboardButton(f"ᴛɪᴍᴇ 1 · {settings.get('verify_time')}", callback_data="adv_gap#1"), InlineKeyboardButton(f"ᴛɪᴍᴇ 2 · {settings.get('third_verify_time')}", callback_data="adv_gap#2")],
        _back("adv_back_advanced"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_tutorials(query, grp_id):
    text = "<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴛᴜᴛᴏʀɪᴀʟꜱ</b>\n\n<b>ꜱᴇʟᴇᴄᴛ ʏᴏᴜʀ 1ꜱᴛ, 2ɴᴅ ᴀɴᴅ 3ʀᴅ ᴛᴜᴛᴏʀɪᴀʟ...</b>"
    buttons = [
        [InlineKeyboardButton("1sᴛ ᴛᴜᴛᴏʀɪᴀʟ", callback_data="adv_tut#1"), InlineKeyboardButton("2ɴᴅ ᴛᴜᴛᴏʀɪᴀʟ", callback_data="adv_tut#2")],
        [InlineKeyboardButton("3ʀᴅ ᴛᴜᴛᴏʀɪᴀʟ", callback_data="adv_tut#3")],
        _back("adv_back_advanced"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_tutorial_detail(query, grp_id, slot):
    settings = await get_settings(grp_id)
    key = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
    value = settings.get(key)
    text = f"<b>📹 Tutorial {slot} Settings:</b>"
    if value:
        text += f"\n🔗 ᴠᴀʟᴜᴇ: <code>{value}</code>"
    buttons = [
        [InlineKeyboardButton("sᴇᴛ", callback_data=f"adv_settut#{slot}"), InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"adv_remtut#{slot}")],
        _back("adv_tutorials"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^advanced_settings$|^adv_"))
async def advanced_callback(client, query):
    data = query.data
    grp_id = query.message.chat.id
    if query.message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await query.answer("ᴜsᴇ ᴛʜɪꜱ ɪɴ ᴀ ɢʀᴏᴜᴘ", show_alert=True)
    if not await is_check_admin(client, grp_id, query.from_user.id):
        return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ", show_alert=True)

    if data == "advanced_settings":
        await query.answer()
        return await show_advanced(query, grp_id)
    if data == "adv_back_settings":
        await query.answer()
        return await show_main_settings(query, grp_id)
    if data == "adv_back_advanced":
        await query.answer()
        return await show_advanced(query, grp_id)
    if data == "adv_shortlinks":
        await query.answer()
        return await show_shortlinks(query, grp_id)
    if data == "adv_gaps":
        await query.answer()
        return await show_gaps(query, grp_id)
    if data == "adv_tutorials":
        await query.answer()
        return await show_tutorials(query, grp_id)
    if data == "adv_toggle_verify":
        settings = await get_settings(grp_id)
        new_value = not bool(settings.get("is_verify"))
        await save_group_settings(grp_id, "is_verify", new_value)
        await query.answer("ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴏɴ ✅" if new_value else "ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴏꜰꜰ ❌")
        return await show_advanced(query, grp_id)
    if data == "adv_cancel":
        PENDING.pop((grp_id, query.from_user.id), None)
        await query.answer("ᴄᴀɴᴄᴇʟʟᴇᴅ")
        return await show_advanced(query, grp_id)
    if data.startswith("adv_short#"):
        await query.answer()
        return await show_short_detail(query, grp_id, int(data.split("#")[1]))
    if data.startswith("adv_setshort#"):
        slot = int(data.split("#")[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "short", "slot": slot, "stage": "domain"}
        await query.answer()
        return await query.message.edit_text(
            "<b>ꜱᴇɴᴅ ɴᴇᴡ ꜱʜᴏʀᴛɴᴇʀ ᴡᴇʙꜱɪᴛᴇ</b>\n\nᴜꜱᴇ the /cancel button below to cancel.",
            reply_markup=InlineKeyboardMarkup([_cancel_button()]),
            parse_mode=enums.ParseMode.HTML,
        )
    if data.startswith("adv_remshort#"):
        slot = int(data.split("#")[1])
        keys = {1: ("shortner", "api"), 2: ("shortner_two", "api_two"), 3: ("shortner_three", "api_three")}[slot]
        await save_group_settings(grp_id, keys[0], "")
        await save_group_settings(grp_id, keys[1], "")
        await query.answer(f"sʜᴏʀᴛᴇɴᴇʀ {slot} ʀᴇᴍᴏᴠᴇᴅ")
        return await show_short_detail(query, grp_id, slot)
    if data.startswith("adv_gap#"):
        slot = int(data.split("#")[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "gap", "slot": slot, "stage": "value"}
        await query.answer()
        return await query.message.edit_text(
            f"<b>ꜱᴇɴᴅ ᴛɪᴍᴇ {slot} ᴠᴀʟᴜᴇ ɪɴ ꜱᴇᴄᴏɴᴅꜱ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.",
            reply_markup=InlineKeyboardMarkup([_cancel_button()]),
            parse_mode=enums.ParseMode.HTML,
        )
    if data.startswith("adv_tut#"):
        await query.answer()
        return await show_tutorial_detail(query, grp_id, int(data.split("#")[1]))
    if data.startswith("adv_settut#"):
        slot = int(data.split("#")[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "tutorial", "slot": slot, "stage": "value"}
        await query.answer()
        return await query.message.edit_text(
            f"<b>📹 sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ {slot} ᴜʀʟ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.",
            reply_markup=InlineKeyboardMarkup([_cancel_button()]),
            parse_mode=enums.ParseMode.HTML,
        )
    if data.startswith("adv_remtut#"):
        slot = int(data.split("#")[1])
        key = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
        await save_group_settings(grp_id, key, "")
        await query.answer(f"ᴛᴜᴛᴏʀɪᴀʟ {slot} ʀᴇᴍᴏᴠᴇᴅ")
        return await show_tutorial_detail(query, grp_id, slot)


@Client.on_message(filters.command("cancel") & filters.group)
async def advanced_cancel(client, message):
    key = (message.chat.id, message.from_user.id)
    if key not in PENDING:
        return raise_continue()
    PENDING.pop(key, None)
    await message.reply_text("<b>ᴘʀᴏᴄᴇꜱꜱ ᴄᴀɴᴄᴇʟʟᴇᴅ ✅</b>")


def raise_continue():
    raise ContinuePropagation


@Client.on_message(filters.text & filters.group)
async def advanced_input(client, message):
    key = (message.chat.id, message.from_user.id)
    state = PENDING.get(key)
    if not state:
        raise ContinuePropagation
    if not await is_check_admin(client, message.chat.id, message.from_user.id):
        PENDING.pop(key, None)
        raise ContinuePropagation
    value = message.text.strip()
    if not value:
        return await message.reply_text("ᴠᴀʟᴜᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ")

    if state["type"] == "short" and state["stage"] == "domain":
        state["domain"] = value.replace("https://", "").replace("http://", "").rstrip("/")
        state["stage"] = "api"
        return await message.reply_text(
            "<b>ɴᴏᴡ ꜱᴇɴᴅ ꜱʜᴏʀᴛɴᴇʀ ᴀᴘɪ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.",
            reply_markup=InlineKeyboardMarkup([_cancel_button()]),
            parse_mode=enums.ParseMode.HTML,
        )

    if state["type"] == "short" and state["stage"] == "api":
        api = value
        domain = state["domain"]
        slot = state["slot"]
        try:
            resp = requests.get(f"https://{domain}/api?api={api}&url=https://t.me/", timeout=10).json()
            if resp.get("status") != "success":
                return await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ꜱʜᴏʀᴛᴇɴᴇʀ ᴏʀ ᴀᴘɪ. ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ /cancel")
        except Exception as exc:
            return await message.reply_text(f"❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴠᴇʀɪꜰʏ ꜱʜᴏʀᴛᴇɴᴇʀ: <code>{exc}</code>")
        keys = {1: ("shortner", "api"), 2: ("shortner_two", "api_two"), 3: ("shortner_three", "api_three")} [slot]
        await save_group_settings(message.chat.id, keys[0], domain)
        await save_group_settings(message.chat.id, keys[1], api)
        PENDING.pop(key, None)
        return await message.reply_text(
            f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴜᴘᴅᴀᴛᴇᴅ ꜱʜᴏʀᴛᴇɴᴇʀ {slot} ᴠᴀʟᴜᴇꜱ ✅</b>\nᴡᴇʙꜱɪᴛᴇ: <code>{domain}</code>\nᴀᴘɪ: <code>{api}</code>",
            reply_markup=InlineKeyboardMarkup([_back("adv_shortlinks")]),
            parse_mode=enums.ParseMode.HTML,
        )

    if state["type"] == "gap":
        try:
            seconds = int(value)
            if seconds < 0:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ᴏꜰ ꜱᴇᴄᴏɴᴅꜱ ᴏʀ /cancel")
        slot = state["slot"]
        key_name = "verify_time" if slot == 1 else "third_verify_time"
        await save_group_settings(message.chat.id, key_name, seconds)
        PENDING.pop(key, None)
        return await message.reply_text(
            f"<b>ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ {slot} ᴜᴘᴅᴀᴛᴇᴅ ✅</b>\nᴛɪᴍᴇ: <code>{seconds}</code>",
            reply_markup=InlineKeyboardMarkup([_back("adv_gaps")]),
            parse_mode=enums.ParseMode.HTML,
        )

    if state["type"] == "tutorial":
        if not (value.startswith("http://") or value.startswith("https://")):
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ʜᴛᴛᴘ/ʜᴛᴛᴘs ᴜʀʟ ᴏʀ /cancel")
        slot = state["slot"]
        key_name = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
        await save_group_settings(message.chat.id, key_name, value)
        PENDING.pop(key, None)
        return await message.reply_text(
            f"<b>ᴛᴜᴛᴏʀɪᴀʟ {slot} ᴜᴘᴅᴀᴛᴇᴅ ✅</b>\nᴠᴀʟᴜᴇ: <code>{value}</code>",
            reply_markup=InlineKeyboardMarkup([_back("adv_tutorials")]),
            parse_mode=enums.ParseMode.HTML,
        )
