import asyncio
import requests
from datetime import datetime
import pytz
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import *
from utils import get_settings, save_group_settings, is_check_admin, get_readable_time, save_default_settings
from database.users_chats_db import db

# Per-user pending input. Keys are (user_id, group_id).
PENDING = {}


def _cancel_button(group_id):
    return [InlineKeyboardButton("/cancel", callback_data=f"set_cancel#{group_id}")]


def _back(group_id):
    return [InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"set_back#main#{group_id}")]


async def _group_title(client, group_id):
    try:
        chat = await client.get_chat(int(group_id))
        return chat.title or str(group_id)
    except Exception:
        return str(group_id)


def _main_settings_buttons(settings, grp_id):
    def onoff(key):
        return "ON ✅" if settings.get(key) else "OFF ❌"
    return [
        [InlineKeyboardButton(f"📝 AUTO FILTER · {onoff('auto_filter')}", callback_data=f"set_page#auto_filter#{grp_id}"),
         InlineKeyboardButton(f"🔒 FILE SECURE · {onoff('file_secure')}", callback_data=f"set_page#file_secure#{grp_id}")],
        [InlineKeyboardButton(f"🎬 IMDB · {onoff('imdb')}", callback_data=f"set_page#imdb#{grp_id}"),
         InlineKeyboardButton(f"🔍 SPELL CHECK · {onoff('spell_check')}", callback_data=f"set_page#spell_check#{grp_id}")],
        [InlineKeyboardButton(f"🗑️ AUTO DELETE · {onoff('auto_delete')}", callback_data=f"set_page#auto_delete#{grp_id}"),
         InlineKeyboardButton(f"📚 RESULT MODE · {'LINKS 🖇' if settings.get('link') else 'BUTTONS 🎯'}", callback_data=f"set_page#link#{grp_id}")],
        [InlineKeyboardButton(f"📁 ꜰɪʟᴇ ᴍᴏᴅᴇ · {'ꜰɪʟᴇ 📁' if settings.get('file_mode') else 'ᴠᴇʀɪꜰʏ ♻️'}", callback_data=f"set_page#file_mode#{grp_id}"),
         InlineKeyboardButton("📝 FILES CAPTIONS", callback_data=f"set_page#caption#{grp_id}")],
        [InlineKeyboardButton("🎬 TUTORIAL LINK", callback_data=f"set_page#tutorial#{grp_id}"),
         InlineKeyboardButton("🖇️ SET SHORTLINK", callback_data=f"set_page#shortlink#{grp_id}")],
        [InlineKeyboardButton("📢 SET MOVIE REQ", callback_data=f"set_page#request_channel#{grp_id}"),
         InlineKeyboardButton("ℹ️ DETAILS", callback_data=f"set_page#details#{grp_id}")],
        [InlineKeyboardButton("📢 FORCE CHANNEL", callback_data=f"set_page#fsub#{grp_id}"),
         InlineKeyboardButton(f"🔢 SET MAX RESULTS · {settings.get('max_results', MAX_BTN)}", callback_data=f"set_page#max_results#{grp_id}")],
        [InlineKeyboardButton("↩️ BACK TO GROUP LIST", callback_data=f"set_groups#{grp_id}"), InlineKeyboardButton("‼️ CLOSE SETTINGS MENU ‼️", callback_data=f"set_close#{grp_id}")],
    ]


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

    buttons = []
    for gid, title in groups:
        buttons.append([InlineKeyboardButton(f"{title} · {gid}", callback_data=f"set_group#{gid}")])
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
    text = f"<b>⚙️ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs</b>\n\n<b>ɴᴀᴍᴇ:</b> {title}\n<b>ɪᴅ:</b> <code>{grp_id}</code>"
    markup = InlineKeyboardMarkup(_main_settings_buttons(settings, int(grp_id)))
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        return
    await target.reply_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)


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
        return f"<b>📁 ꜰɪʟᴇ ᴍᴏᴅᴇ</b>\n\nʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜰɪʟᴇs ᴍᴏᴅᴇ.\n\nꜰɪʟᴇ ᴍᴏᴅᴇ ᴄʜᴀɴɢᴇs ᴏɴʟʏ ᴛʜᴇ ғɪɴᴀʟ ғɪʟᴇ ᴍᴇssᴀɢᴇ ᴀɴᴅ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs.\nꜱʜᴏʀᴛʟɪɴᴋ/ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ɪs ᴄᴏɴᴛʀᴏʟʟᴇᴅ sᴇᴘᴀʀᴀᴛᴇʟʏ.\n\nᴄᴜʀʀᴇɴᴛ: {mode_text}"
    if key == "caption":
        return f"<b>📝 FILES CAPTIONS</b>\n\nCurrent caption:\n<code>{settings.get('caption', FILE_CAPTION)}</code>\n\nSupported placeholder: {{file_name}}"
    if key == "tutorial":
        return f"<b>🎬 TUTORIAL LINK</b>\n\n1: {settings.get('tutorial') or TUTORIAL}\n2: {settings.get('tutorial_2') or TUTORIAL_2}\n3: {settings.get('tutorial_3') or TUTORIAL_3}"
    if key == "shortlink":
        return (
            f"<b>🖇️ SET SHORTLINK</b>\n\n"
            f"Verification: {'ON ✅' if settings.get('is_verify') else 'OFF ❌'}\n"
            f"1: {settings.get('shortner')}\n"
            f"2: {settings.get('shortner_two')}\n"
            f"3: {settings.get('shortner_three')}\n\n"
            f"1st verify gap: <code>{get_readable_time(settings.get('verify_time', TWO_VERIFY_GAP))}</code>\n"
            f"3rd verify gap: <code>{get_readable_time(settings.get('third_verify_time', THREE_VERIFY_GAP))}</code>"
        )
    if key == "request_channel":
        return f"<b>📢 SET MOVIE REQ</b>\n\nCurrent request channel: <code>{settings.get('request_channel', REQUEST_CHANNEL)}</code>"
    if key == "fsub":
        channels = settings.get('fsub_channels') or [settings.get('fsub_id', AUTH_CHANNEL)]
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


def _page_buttons(key, settings, grp_id):
    b = []
    if key in {"auto_filter", "file_secure", "spell_check", "auto_delete", "link", "file_mode"}:
        if key == "link":
            b.append([InlineKeyboardButton("Set button mode" if settings.get("link") else "Set links mode", callback_data=f"set_toggle#{key}#{grp_id}")])
        else:
            b.append([InlineKeyboardButton("Turn off" if settings.get(key) else "Turn on", callback_data=f"set_toggle#{key}#{grp_id}")])
        if key == "auto_delete":
            b.append([InlineKeyboardButton("Set time", callback_data=f"set_input#delete_time#{grp_id}")])
        if key == "file_mode":
            mode = settings.get("file_mode_type", "verify")
            next_mode = "shortlink" if mode == "verify" else "verify"
            label = "📎 ꜱᴇᴛ sʜᴏʀᴛʟɪɴᴋ ᴍᴏᴅᴇ" if mode == "verify" else "♻️ sᴇᴛ ᴠᴇʀɪғʏ ᴍᴏᴅᴇ"
            b = [[InlineKeyboardButton(label, callback_data=f"set_file_mode#{next_mode}#{grp_id}")]]
    elif key == "imdb":
        b = [
            [InlineKeyboardButton("Set template", callback_data=f"set_input#template#{grp_id}")],
            [InlineKeyboardButton("Default template", callback_data=f"set_default#template#{grp_id}"), InlineKeyboardButton("Off poster", callback_data=f"set_toggle#imdb#{grp_id}")],
        ]
    elif key == "caption":
        b = [[InlineKeyboardButton("Set caption", callback_data=f"set_input#caption#{grp_id}"), InlineKeyboardButton("Default caption", callback_data=f"set_default#caption#{grp_id}")]]
    elif key == "tutorial":
        b = [[InlineKeyboardButton("Set tutorial 1", callback_data=f"set_input#tutorial#{grp_id}"), InlineKeyboardButton("Set tutorial 2", callback_data=f"set_input#tutorial_2#{grp_id}")], [InlineKeyboardButton("Set tutorial 3", callback_data=f"set_input#tutorial_3#{grp_id}")]]
    elif key == "shortlink":
        b = [
            [InlineKeyboardButton(
                "Turn verification OFF ❌" if settings.get("is_verify") else "Turn verification ON ✅",
                callback_data=f"set_toggle#is_verify#{grp_id}",
            )],
            [
                InlineKeyboardButton("Set shortlink 1", callback_data=f"set_input#shortner#{grp_id}"),
                InlineKeyboardButton("Set shortlink 2", callback_data=f"set_input#shortner_two#{grp_id}"),
            ],
            [InlineKeyboardButton("Set shortlink 3", callback_data=f"set_input#shortner_three#{grp_id}")],
            [
                InlineKeyboardButton("Set 1st verify gap", callback_data=f"set_input#verify_time#{grp_id}"),
                InlineKeyboardButton("Set 3rd verify gap", callback_data=f"set_input#third_verify_time#{grp_id}"),
            ],
        ]
    elif key == "request_channel":
        b = [[InlineKeyboardButton("Set channel", callback_data=f"set_input#request_channel#{grp_id}"), InlineKeyboardButton("Delete channel", callback_data=f"set_delete#request_channel#{grp_id}")]]
    elif key == "fsub":
        b = [[InlineKeyboardButton("Set channel", callback_data=f"set_input#fsub_add#{grp_id}"), InlineKeyboardButton("Delete channel", callback_data=f"set_input#fsub_delete#{grp_id}")]]
    elif key == "max_results":
        b = [[InlineKeyboardButton("Set max result", callback_data=f"set_input#max_results#{grp_id}"), InlineKeyboardButton("Default max result", callback_data=f"set_default#max_results#{grp_id}")]]
    elif key == "details":
        b = [[InlineKeyboardButton("Reset all", callback_data=f"set_reset#{grp_id}")]]
    b.append(_back(grp_id))
    return b


async def show_page(client, query, key, grp_id):
    settings = await get_settings(int(grp_id))
    await query.message.edit_text(_page_text(key, settings), reply_markup=InlineKeyboardMarkup(_page_buttons(key, settings, grp_id)), parse_mode=enums.ParseMode.HTML)


async def _authorize(client, query, grp_id):
    try:
        ok = await is_check_admin(client, int(grp_id), query.from_user.id)
    except Exception:
        ok = False
    if not ok:
        await query.answer("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴛʜɪs", show_alert=True)
        return False
    return True


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
        elif action in {"set_back"}:
            key = parts[1]
            gid = int(parts[2])
        else:
            gid = int(parts[1]) if len(parts) > 1 else 0
            key = ""

        if not await _authorize(client, query, gid):
            return

        if action == "set_page":
            return await show_page(client, query, key, gid)
        if action == "set_back":
            return await show_group_settings(client, query, gid)
        if action == "set_close":
            PENDING.pop((query.from_user.id, gid), None)
            return await query.message.delete()
        if action == "set_reset":
            await save_default_settings(gid)
            return await show_group_settings(client, query, gid)
        if action == "set_file_mode":
            mode = key
            if mode not in {"verify", "shortlink"}:
                mode = "verify"
            await save_group_settings(gid, "file_mode", True)
            await save_group_settings(gid, "file_mode_type", mode)
            return await show_page(client, query, "file_mode", gid)
        if action == "set_toggle":
            settings = await get_settings(gid)
            value = not bool(settings.get(key))
            await save_group_settings(gid, key, value)
            return await show_page(client, query, key, gid)
        if action == "set_default":
            defaults = db.default.copy()
            if key == "max_results":
                await save_group_settings(gid, key, int(MAX_BTN))
            else:
                await save_group_settings(gid, key, defaults.get(key, ""))
            return await show_page(client, query, key, gid)
        if action == "set_delete":
            if key == "request_channel":
                await save_group_settings(gid, key, int(REQUEST_CHANNEL))
            return await show_page(client, query, key, gid)
        if action == "set_input":
            state = {"type": key}
            PENDING[(query.from_user.id, gid)] = state
            prompt = {
                "delete_time": "Send delete time in seconds.",
                "template": "Send your IMDB template. Supported: {search}, {mention}, {group}",
                "caption": "Send your file caption. Supported: {file_name}",
                "max_results": "Send max results from 1 to 20.",
                "request_channel": "Send request channel ID.",
                "fsub_add": "Send force-subscribe channel ID.",
                "fsub_delete": "Send the force-subscribe channel ID to delete.",
                "shortner": "Send shortener 1 URL/domain.",
                "shortner_two": "Send shortener 2 URL/domain.",
                "shortner_three": "Send shortener 3 URL/domain.",
                "api": "Send shortener 1 API.",
                "api_two": "Send shortener 2 API.",
                "api_three": "Send shortener 3 API.",
                "verify_time": "Send the 1st verification gap in seconds.",
                "third_verify_time": "Send the 3rd verification gap in seconds.",
                "tutorial": "Send tutorial 1 URL.",
                "tutorial_2": "Send tutorial 2 URL.",
                "tutorial_3": "Send tutorial 3 URL.",
            }.get(key, "Send the new value.")
            return await query.message.edit_text(f"<b>{prompt}</b>\n\nSend /cancel to cancel.", reply_markup=InlineKeyboardMarkup([_cancel_button(gid)]), parse_mode=enums.ParseMode.HTML)
        if action == "set_cancel":
            gid = int(parts[1])
            PENDING.pop((query.from_user.id, gid), None)
            return await show_group_settings(client, query, gid)
    except Exception as exc:
        try:
            await query.answer("Something went wrong", show_alert=True)
        except Exception:
            pass
        print(f"settings callback error: {exc}")


@Client.on_message(filters.command("cancel"))
async def advanced_cancel(client, message):
    key_candidates = [(message.from_user.id, gid) for (uid, gid) in list(PENDING) if uid == message.from_user.id]
    if not key_candidates:
        raise ContinuePropagation
    for key in key_candidates:
        PENDING.pop(key, None)
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
    if key == "delete_time":
        try:
            value_int = int(value)
            if value_int < 1:
                raise ValueError
        except ValueError:
            return await message.reply_text("Send a valid positive number of seconds or /cancel")
        await save_group_settings(gid, "delete_time", value_int)
        PENDING.pop((uid, gid), None)
    elif key == "max_results":
        try:
            value_int = int(value)
            if not 1 <= value_int <= 20:
                raise ValueError
        except ValueError:
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
    elif key in {"shortner", "shortner_two", "shortner_three"}:
        domain = value.replace("https://", "").replace("http://", "").rstrip("/")
        api_key = {"shortner": "api", "shortner_two": "api_two", "shortner_three": "api_three"}[key]
        await save_group_settings(gid, key, domain)
        state["type"] = api_key
        PENDING[(uid, gid)] = state
        return await message.reply_text("<b>ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ sʜᴏʀᴛᴇɴᴇʀ ᴀᴘɪ</b>\n\nSend /cancel to cancel.")
    elif key in {"api", "api_two", "api_three"}:
        settings = await get_settings(gid)
        domain_key = {"api": "shortner", "api_two": "shortner_two", "api_three": "shortner_three"}[key]
        domain = settings.get(domain_key)
        if not domain:
            PENDING.pop((uid, gid), None)
            return await message.reply_text("❌ ᴘʟᴇᴀsᴇ sᴇᴛ ᴛʜᴇ sʜᴏʀᴛᴇɴᴇʀ ᴅᴏᴍᴀɪɴ ғɪʀsᴛ.")
        try:
            resp = requests.get(f"https://{domain}/api?api={value}&url=https://t.me/", timeout=10).json()
            if resp.get("status") not in {"success", True}:
                return await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ sʜᴏʀᴛᴇɴᴇʀ ᴏʀ ᴀᴘɪ. ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ /cancel")
        except Exception as exc:
            return await message.reply_text(f"❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴠᴇʀɪғʏ sʜᴏʀᴛᴇɴᴇʀ: <code>{exc}</code>")
        await save_group_settings(gid, key, value)
        PENDING.pop((uid, gid), None)
    elif key in {"verify_time", "third_verify_time"}:
        try:
            value_int = int(value)
            if value_int < 1:
                raise ValueError
        except ValueError:
            return await message.reply_text("Send a valid positive number of seconds or /cancel")
        await save_group_settings(gid, key, value_int)
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

    confirmation = await message.reply_text("<b>ᴜᴘᴅᴀᴛᴇᴅ ✅</b>")
    await asyncio.sleep(2)
    try:
        await confirmation.delete()
    except Exception:
        pass
