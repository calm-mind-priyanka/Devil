import requests
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
import re

from info import *
from utils import get_settings, save_group_settings, is_check_admin, get_readable_time

PENDING = {}
GROUP_SETTING_PENDING = {}


def _cancel_button(grp_id):
    return [InlineKeyboardButton("/cancel", callback_data=f"adv_cancel#{grp_id}")]


def _back(callback):
    return [InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=callback)]


def _main_settings_buttons(settings, grp_id, private=True):
    # Kept for compatibility with old imports; canonical menu is in commands.py.
    return []


async def _group_title(client, grp_id):
    try:
        chat = await client.get_chat(grp_id)
        return chat.title or "Group"
    except Exception:
        return "Group"


async def show_main_settings(client, query, grp_id, private=None):
    settings = await get_settings(grp_id)
    title = await _group_title(client, grp_id)
    if private is None:
        private = query.message.chat.type == enums.ChatType.PRIVATE
    await query.message.edit_text(
        f"🛡️ <b>ɢʀᴏᴜᴘ - {title}</b>\n🆔 <code>{grp_id}</code>\n\n"
        "<b>ꜱᴇʟᴇᴄᴛ ᴏɴᴇ ᴏꜰ ᴛʜᴇ sᴇᴛᴛɪɴɢꜱ ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ...</b>",
        reply_markup=InlineKeyboardMarkup(_settings_buttons(settings, grp_id, private)),
        parse_mode=enums.ParseMode.HTML,
    )


def _settings_buttons(settings, grp_id, private=True):
    """Main 2-column settings grid. Each item opens its own real settings page."""
    buttons = [
        [InlineKeyboardButton("📝 ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ", callback_data=f"grp_setting#auto_filter#{grp_id}"),
         InlineKeyboardButton("🔒 ꜰɪʟᴇ ꜱᴇᴄᴜʀᴇ", callback_data=f"grp_setting#file_secure#{grp_id}")],
        [InlineKeyboardButton("🎬 ɪᴍᴅʙ", callback_data=f"grp_setting#imdb#{grp_id}"),
         InlineKeyboardButton("🔍 ꜱᴘᴇʟʟ ᴄʜᴇᴄᴋ", callback_data=f"grp_setting#spell_check#{grp_id}")],
        [InlineKeyboardButton("🗑️ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ", callback_data=f"grp_setting#auto_delete#{grp_id}"),
         InlineKeyboardButton("📚 ʀᴇꜱᴜʟᴛ ᴍᴏᴅᴇ", callback_data=f"grp_setting#result_mode#{grp_id}")],
        [InlineKeyboardButton("📁 ꜰɪʟᴇ ᴍᴏᴅᴇ", callback_data=f"grp_setting#files_mode#{grp_id}"),
         InlineKeyboardButton("📝 ꜰɪʟᴇꜱ ᴄᴀᴘᴛɪᴏɴꜱ", callback_data=f"grp_setting#caption#{grp_id}")],
        [InlineKeyboardButton("🎬 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ", callback_data=f"adv_tutorials#{grp_id}"),
         InlineKeyboardButton("🖇️ ꜱᴇᴛ ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"adv_shortlinks#{grp_id}")],
        [InlineKeyboardButton("📢 ꜱᴇᴛ ᴍᴏᴠɪᴇ ʀᴇQ", callback_data=f"grp_setting#movie_req#{grp_id}"),
         InlineKeyboardButton("ℹ️ ᴅᴇᴛᴀɪʟꜱ", callback_data=f"grp_setting#details#{grp_id}")],
        [InlineKeyboardButton("📢 ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"grp_setting#force_channel#{grp_id}"),
         InlineKeyboardButton("🔢 ꜱᴇᴛ ᴍᴀx ʀᴇꜱᴜʟᴛꜱ", callback_data=f"grp_setting#max_results#{grp_id}")],
    ]
    buttons.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ ᴛᴏ ɢʀᴏᴜᴘ ʟɪꜱᴛ", callback_data="settings_groups")] if private else
                    [InlineKeyboardButton("‼️ ᴄʟᴏꜱᴇ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ ‼️", callback_data="close_data")])
    return buttons


def _back_settings(grp_id):
    return InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"settings_group#{grp_id}")


def _setting_page_buttons(grp_id, rows):
    rows.append([_back_settings(grp_id)])
    return InlineKeyboardMarkup(rows)


async def _edit_setting_page(query, text, buttons):
    await query.message.edit_text(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)


async def _show_settings_group_list(client, message, user_id):
    groups = await db.get_user_groups(user_id, client)
    if not groups:
        return await message.edit_text(
            "<b>ɴᴏ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ ꜰᴏᴜɴᴅ.</b>\n\nᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ꜰɪʀꜱᴛ ᴀɴᴅ ᴍᴀᴋᴇ ᴍᴇ ᴀᴅᴍɪɴ.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{temp.U_NAME}?startgroup=start")]]),
        )
    buttons = []
    for chat in groups:
        group_id = int(chat["id"])
        title = chat.get("title") or str(group_id)
        try:
            title = (await client.get_chat(group_id)).title or title
        except Exception:
            pass
        buttons.append([InlineKeyboardButton(f"🛡️ ɢʀᴏᴜᴘ - {title[:40]}\n🆔 ɪᴅ - {group_id}", callback_data=f"settings_group#{group_id}")])
    buttons.append([InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")])
    return await message.edit_text("<b>⚙️ ʜᴇʀᴇ ᴀʀᴇ ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ</b>\n\nꜱᴇʟᴇᴄᴛ ᴀ ɢʀᴏᴜᴘ ᴛᴏ ᴇᴅɪᴛ ɪᴛꜱ ꜱᴇᴛᴛɪɴɢꜱ 👇", reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def _show_main_settings(client, query, grp_id):
    settings = await get_settings(grp_id)
    try:
        title = (await client.get_chat(grp_id)).title or "Group"
    except Exception:
        title = "Group"
    private = query.message.chat.type == enums.ChatType.PRIVATE
    await query.message.edit_text(
        f"🛡️ <b>ɢʀᴏᴜᴘ - {title}</b>\n🆔 <code>{grp_id}</code>\n\n<b>ꜱᴇʟᴇᴄᴛ ᴏɴᴇ ᴏꜰ ᴛʜᴇ ꜱᴇᴛᴛɪɴɢꜱ ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ...</b>",
        reply_markup=InlineKeyboardMarkup(_settings_buttons(settings, grp_id, private)), parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^settings_group#|^settings_groups$|^grp_setting#|^file_mode#|^setting_cancel#"))
async def settings_group_callback(client, query):
    user_id = query.from_user.id
    data = query.data
    if data == "settings_groups":
        await query.answer()
        return await _show_settings_group_list(client, query.message, user_id)

    if data.startswith("settings_group#"):
        grp_id = int(data.split("#", 1)[1])
        if not await is_check_admin(client, grp_id, user_id):
            return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ᴏꜰ ᴛʜɪꜱ ɢʀᴏᴜᴘ", show_alert=True)
        await query.answer()
        return await _show_main_settings(client, query, grp_id)

    if data.startswith("setting_cancel#"):
        _, pending_action, grp_id_s = data.split("#", 2)
        grp_id = int(grp_id_s)
        if not await is_check_admin(client, grp_id, user_id):
            return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ", show_alert=True)
        GROUP_SETTING_PENDING.pop((user_id, grp_id), None)
        await query.answer("ᴄᴀɴᴄᴇʟʟᴇᴅ")
        target = {
            "set_caption": "caption", "set_template": "imdb", "delete_time": "auto_delete",
            "force_channel": "force_channel", "request_channel": "movie_req", "max_results": "max_results"
        }.get(pending_action, "details")
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#{target}#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if data.startswith("file_mode#"):
        _, mode, grp_id_s = data.split("#", 2)
        grp_id = int(grp_id_s)
        if not await is_check_admin(client, grp_id, user_id):
            return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ", show_alert=True)
        await save_group_settings(grp_id, "is_verify", mode == "verify")
        return await _show_main_settings(client, query, grp_id)

    _, action, grp_id_s = data.split("#", 2)
    grp_id = int(grp_id_s)
    if not await is_check_admin(client, grp_id, user_id):
        return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ", show_alert=True)
    settings = await get_settings(grp_id)

    if action in ("auto_filter", "file_secure", "spell_check", "auto_filter_toggle", "file_secure_toggle", "spell_check_toggle"):
        base = action.replace("_toggle", "")
        if action.endswith("_toggle"):
            value = not bool(settings.get(base, False))
            await save_group_settings(grp_id, base, value)
            settings = await get_settings(grp_id)
        else:
            value = bool(settings.get(base, False))
        if base == "auto_filter":
            text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ ᴍᴏᴅᴇ ᴍᴇᴀɴꜱ ʙᴏᴛ ꜱᴇɴᴅ ʀᴇꜱᴜʟᴛ ɪɴ ɢʀᴏᴜᴘ ᴏʀ ɴᴏᴛ...ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ - {'ᴏɴ ✅' if value else 'ᴏꜰꜰ ❌'}</b>"
        elif base == "file_secure":
            text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇꜱ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ, ᴍᴇᴀɴꜱ ᴡʜᴇᴛʜᴇʀ ᴜꜱᴇʀꜱ ᴄᴀɴ ꜰᴏʀᴡᴀʀᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴏʀ ɴᴏᴛ...ᴘʀᴏᴛᴇᴄᴛ - {'ᴏɴ ✅' if value else 'ᴏꜰꜰ ❌'}</b>"
        else:
            text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʙᴏᴛ ꜱᴘᴇʟʟɪɴɢ ᴄʜᴇᴄᴋ ᴍᴇꜱꜱᴀɢᴇꜱᴘᴇʟʟ ᴄʜᴇᴄᴋ - {'ᴏɴ ✅' if value else 'ᴏꜰꜰ ❌'}</b>"
        button_text = "ᴛᴜʀɴ ᴏꜰꜰ" if value else "ᴛᴜʀɴ ᴏɴ"
        await query.answer("ᴏɴ ✅" if value else "ᴏꜰꜰ ❌")
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, [[InlineKeyboardButton(button_text, callback_data=f"grp_setting#{base}_toggle#{grp_id}")]]))

    if action == "imdb":
        await query.answer()
        value = bool(settings.get("imdb", False))
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɪᴍᴅʙ sᴇᴛᴛɪɴɢ.\nɪᴍᴅʙ ᴘᴏsᴛᴇʀ - {'ᴏɴ ✅' if value else 'ᴏꜰꜰ ❌'}\nɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ - {settings.get('template', IMDB_TEMPLATE)}</b>"
        rows = [[InlineKeyboardButton("ᴏꜰꜰ ᴘᴏsᴛᴇʀ" if value else "ᴏɴ ᴘᴏsᴛᴇʀ", callback_data=f"grp_setting#imdb_toggle#{grp_id}")],
                [InlineKeyboardButton("ꜱᴇᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data=f"grp_setting#set_template#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data=f"grp_setting#default_template#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "imdb_toggle":
        value = not bool(settings.get("imdb", False))
        await save_group_settings(grp_id, "imdb", value)
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#imdb#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "spell_check":
        await query.answer()
        value = bool(settings.get("spell_check", False))
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʙᴏᴛ ꜱᴘᴇʟʟɪɴɢ ᴄʜᴇᴄᴋ ᴍᴇꜱꜱᴀɢᴇs.ꜱᴘᴇʟʟ ᴄʜᴇᴄᴋ - {'ᴏɴ ✅' if value else 'ᴏꜰꜰ ❌'}</b>"
        button_text = "ᴛᴜʀɴ ᴏꜰꜰ" if value else "ᴛᴜʀɴ ᴏɴ"
        rows = [[InlineKeyboardButton(button_text, callback_data=f"grp_setting#spell_check_toggle#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "spell_check_toggle":
        value = not bool(settings.get("spell_check", False))
        await save_group_settings(grp_id, "spell_check", value)
        return await settings_group_callback(
            client,
            type("Q", (), {
                "data": f"grp_setting#spell_check#{grp_id}",
                "from_user": query.from_user,
                "message": query.message,
                "answer": query.answer
            })()
        )

    if action == "auto_delete":
        await query.answer()
        enabled = bool(settings.get("auto_delete", False)); seconds = int(settings.get("delete_time", DELETE_TIME))
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɢɪᴠᴇɴ ꜰɪʟᴇs ᴅᴇʟᴇᴛᴇ sᴇᴛᴛɪɴɢ.\nᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ - {'ᴏɴ ✅' if enabled else 'ᴏꜰꜰ ❌'}\nᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ - <code>{get_readable_time(seconds)}</code></b>"
        rows = [[InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ" if enabled else "ᴛᴜʀɴ ᴏɴ", callback_data=f"grp_setting#auto_delete_toggle#{grp_id}")],
                [InlineKeyboardButton("ꜱᴇᴛ ᴛɪᴍᴇ", callback_data=f"grp_setting#delete_time#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "auto_delete_toggle":
        await save_group_settings(grp_id, "auto_delete", not bool(settings.get("auto_delete", False)))
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#auto_delete#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "result_mode":
        await query.answer()
        is_link = bool(settings.get("link", False))
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɢɪᴠᴇɴ ʀᴇꜱᴜʟᴛ ᴍᴏᴅᴇ.\nʀᴇꜱᴜʟᴛ ᴍᴏᴅᴇ - {'ʟɪɴᴋs 🖇' if is_link else 'ʙᴜᴛᴛᴏɴs 🎯'}</b>"
        rows = [[InlineKeyboardButton("ꜱᴇᴛ ʙᴜᴛᴛᴏɴ ᴍᴏᴅᴇ" if is_link else "ꜱᴇᴛ ʟɪɴᴋs ᴍᴏᴅᴇ", callback_data=f"grp_setting#result_toggle#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "result_toggle":
        await save_group_settings(grp_id, "link", not bool(settings.get("link", False)))
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#result_mode#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "files_mode":
        await query.answer()
        verify = bool(settings.get("is_verify", IS_VERIFY))
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜰɪʟᴇs ᴍᴏᴅᴇ, ʙᴏᴛ ʜᴀᴠᴇ ᴛᴡᴏ ᴍᴏᴅᴇs: ᴠᴇʀɪꜰʏ ᴍᴏᴅᴇ & ꜱʜᴏʀᴛʟɪɴᴋ ᴍᴏᴅᴇ.\nꜰɪʟᴇ ᴍᴏᴅᴇ - {'♻️ ᴠᴇʀɪꜰʏ' if verify else '📎 ꜱʜᴏʀᴛʟɪɴᴋ'}</b>"
        rows = [[InlineKeyboardButton("ꜱᴇᴛꜱʜᴏʀᴛʟɪɴᴋ ᴍᴏᴅᴇ" if verify else "ꜱᴇᴛ ᴠᴇʀɪꜰʏ ᴍᴏᴅᴇ", callback_data=f"grp_setting#file_mode_toggle#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "file_mode_toggle":
        await save_group_settings(grp_id, "is_verify", not bool(settings.get("is_verify", IS_VERIFY)))
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#files_mode#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "caption":
        await query.answer()
        caption = settings.get("caption", FILE_CAPTION)
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɢɪᴠᴇɴ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ.\nꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ - <code>{caption}</code></b>"
        rows = [[InlineKeyboardButton("ꜱᴇᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"grp_setting#set_caption#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"grp_setting#default_caption#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "default_caption":
        await save_group_settings(grp_id, "caption", FILE_CAPTION)
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#caption#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action in ("set_caption", "set_template", "delete_time", "force_channel", "request_channel", "max_results"):
        await query.answer()
        GROUP_SETTING_PENDING[(user_id, grp_id)] = action
        prompts = {
            "set_caption": "ᴜꜱᴇ ᴛʜᴇ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀ <code>{file_name}</code> ᴀꜱ ɴᴇᴇᴅᴇᴅ.\n\nꜱᴇɴᴅ ɴᴇᴡ ᴄᴀᴘᴛɪᴏɴ:",
            "set_template": "ᴜꜱᴇ {search}, {mention}, {group} ᴀɴᴅ ᴏᴛʜᴇʀ ᴇxɪꜱᴛɪɴɢ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs.\n\nꜱᴇɴᴅ ɴᴇᴡ ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ:",
            "delete_time": "ꜱᴇɴᴅ ᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ (example: <code>5</code> = 5 minutes, or <code>300s</code>):",
            "force_channel": "ꜱᴇɴᴅ ᴛʜᴇ ꜰᴏʀᴄᴇ-ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ ɪᴅs (comma separated for multiple):",
            "request_channel": "ꜱᴇɴᴅ ʀᴇǫ ᴄʜᴀɴɴᴇʟ ɪᴅ:",
            "max_results": f"ꜱᴇɴᴅ ᴍᴀx ʀᴇꜱᴜʟᴛs (1-20). ᴄᴜʀʀᴇɴᴛ: <code>{settings.get('max_results', MAX_BTN)}</code>",
        }
        rows = [[InlineKeyboardButton("ᴄᴀɴᴄᴇʟ", callback_data=f"setting_cancel#{action}#{grp_id}")]]
        return await _edit_setting_page(query, f"<b>{prompts[action]}</b>", _setting_page_buttons(grp_id, rows))

    if action == "default_template":
        await query.answer()
        await save_group_settings(grp_id, "template", IMDB_TEMPLATE)
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#imdb#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "movie_req":
        await query.answer()
        enabled = bool(settings.get("movie_req", True)); channel = settings.get("request_channel", REQUEST_CHANNEL)
        text = f"<b>📢 ᴡʜᴀᴛ ɪs ʀᴇǫ ᴄʜᴀɴɴᴇʟ ??\n\nɪꜰ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴍᴇᴍʙᴇʀꜱ ᴅᴏ ɴᴏᴛ ꜰɪɴᴅ ᴛʜᴇ ᴍᴏᴠɪᴇ ᴛʜᴇʏ ʟɪᴋᴇ, ᴛʜᴇʏ ᴄᴀɴ ꜱᴇɴᴅ ʏᴏᴜ ᴀ ʀᴇǫᴜᴇꜱᴛ...\n\nᴍᴏᴠɪᴇ ʀᴇǫ ᴄʜᴀɴɴᴇʟ - <code>{channel}</code>\nᴍᴏᴠɪᴇ ʀᴇQ - {'ᴏɴ ✅' if enabled else 'ᴏꜰꜰ ❌'}</b>"
        rows = [[InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ" if enabled else "ᴛᴜʀɴ ᴏɴ", callback_data=f"grp_setting#movie_req_toggle#{grp_id}")], [InlineKeyboardButton("ꜱᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"grp_setting#request_channel#{grp_id}"), InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"grp_setting#delete_request_channel#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "movie_req_toggle":
        await save_group_settings(grp_id, "movie_req", not bool(settings.get("movie_req", True)))
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#movie_req#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "request_channel":
        GROUP_SETTING_PENDING[(user_id, grp_id)] = "request_channel"
        return await _edit_setting_page(query, "<b>ꜱᴇɴᴅ ʀᴇǫ ᴄʜᴀɴɴᴇʟ ɪᴅ</b>", _setting_page_buttons(grp_id, []))
    if action == "delete_request_channel":
        await save_group_settings(grp_id, "request_channel", REQUEST_CHANNEL)
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#movie_req#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "details":
        await query.answer()
        try: title = (await client.get_chat(grp_id)).title or "Group"
        except Exception: title = "Group"
        force_channels = settings.get("fsub_channels") or [settings.get("fsub_id", AUTH_CHANNEL)]
        if not isinstance(force_channels, list):
            force_channels = [force_channels]
        text = (f"<b>⚙️ ʏᴏᴜʀ ᴀʟʟ sᴇᴛᴛɪɴɢs</b>\n\n🛡️ ɢʀᴏᴜᴘ - {title}\n🆔 <code>{grp_id}</code>\n\n"
                f"📝 ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ - {'ᴏɴ' if settings.get('auto_filter') else 'ᴏꜰꜰ'}\n"
                f"🔒 ꜰɪʟᴇ sᴇᴄᴜʀᴇ - {'ᴏɴ' if settings.get('file_secure') else 'ᴏꜰꜰ'}\n"
                f"🎬 ɪᴍᴅʙ - {'ᴏɴ' if settings.get('imdb') else 'ᴏꜰꜰ'}\n"
                f"🔍 sᴘᴇʟʟ ᴄʜᴇᴄᴋ - {'ᴏɴ' if settings.get('spell_check') else 'ᴏꜰꜰ'}\n"
                f"🗑️ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ - {'ᴏɴ' if settings.get('auto_delete') else 'ᴏꜰꜰ'} / {get_readable_time(int(settings.get('delete_time', DELETE_TIME)))}\n"
                f"📚 ʀᴇꜱᴜʟᴛ ᴍᴏᴅᴇ - {'ʟɪɴᴋs' if settings.get('link') else 'ʙᴜᴛᴛᴏɴs'}\n"
                f"📁 ꜰɪʟᴇ ᴍᴏᴅᴇ - {'ᴠᴇʀɪꜰʏ' if settings.get('is_verify', IS_VERIFY) else 'ꜱʜᴏʀᴛʟɪɴᴋ'}\n"
                f"🎯 ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ - <code>{settings.get('template', IMDB_TEMPLATE)}</code>\n"
                f"📂 ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ - <code>{settings.get('caption', FILE_CAPTION)}</code>\n"
                f"🤔 ᴍᴀx ʀᴇꜱᴜʟᴛs - <code>{settings.get('max_results', MAX_BTN)}</code>\n"
                f"📣 ᴍᴏᴠɪᴇ ʀᴇǫᴜᴇsᴛ ᴄʜᴀɴɴᴇʟ - <code>{settings.get('request_channel', REQUEST_CHANNEL)}</code>\n"
                f"🌀 ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟs - <code>{', '.join(map(str, force_channels))}</code>\n"
                f"🧭 2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - <code>{settings.get('verify_time', TWO_VERIFY_GAP)}</code>\n"
                f"🧭 3ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - <code>{settings.get('third_verify_time', THREE_VERIFY_GAP)}</code>\n"
                f"📝 ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ - <code>{settings.get('log', LOG_VR_CHANNEL)}</code>\n"
                f"1️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 1 - {settings.get('tutorial', TUTORIAL)}\n"
                f"2️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 2 - {settings.get('tutorial_2', TUTORIAL_2)}\n"
                f"3️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 3 - {settings.get('tutorial_3', TUTORIAL_3)}")
        rows = [[InlineKeyboardButton("ʀᴇsᴇᴛ ᴀʟʟ", callback_data=f"grp_setting#reset_all#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))

    if action == "reset_all":
        await save_default_settings(grp_id)
        await save_group_settings(grp_id, "delete_time", DELETE_TIME)
        await save_group_settings(grp_id, "request_channel", REQUEST_CHANNEL)
        await save_group_settings(grp_id, "fsub_channels", [AUTH_CHANNEL])
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#details#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "force_channel":
        await query.answer()
        current = settings.get("fsub_id", AUTH_CHANNEL)
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ, ʏᴏᴜ ᴄᴀɴ ꜱᴇᴛ ᴍᴜʟᴛɪᴘʟᴇ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟs.\n\nꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ - <code>{current}</code></b>"
        rows = [[InlineKeyboardButton("ꜱᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data=f"grp_setting#set_force_channel#{grp_id}"), InlineKeyboardButton("ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ", callback_data=f"grp_setting#delete_force_channel#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))
    if action == "set_force_channel":
        await query.answer()
        GROUP_SETTING_PENDING[(user_id, grp_id)] = "force_channel"
        return await _edit_setting_page(query, "<b>ꜱᴇɴᴅ ᴛʜᴇ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ</b>", _setting_page_buttons(grp_id, []))
    if action == "delete_force_channel":
        await save_group_settings(grp_id, "fsub_id", AUTH_CHANNEL)
        await save_group_settings(grp_id, "fsub_channels", [AUTH_CHANNEL])
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#force_channel#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    if action == "max_results":
        await query.answer()
        current = settings.get("max_results", MAX_BTN)
        text = f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʙᴏᴛ ɢɪᴠᴇɴ ᴍᴀx ꜰɪʟᴇs ɪɴ ʙᴜᴛᴛᴏɴ...ᴍᴀx ʀᴇꜱᴜʟᴛs - <code>{current}</code></b>"
        rows = [[InlineKeyboardButton("ꜱᴇᴛ ᴍᴀx ʀᴇꜱᴜʟᴛ", callback_data=f"grp_setting#set_max_results#{grp_id}"), InlineKeyboardButton("ᴅᴇꜰᴀᴜʟᴛ ᴍᴀx ʀᴇꜱᴜʟᴛ", callback_data=f"grp_setting#default_max_results#{grp_id}")]]
        return await _edit_setting_page(query, text, _setting_page_buttons(grp_id, rows))
    if action == "set_max_results":
        GROUP_SETTING_PENDING[(user_id, grp_id)] = "max_results"
        return await _edit_setting_page(query, "<b>ꜱᴇɴᴅ ᴍᴀx ʀᴇꜱᴜʟᴛs (1-20)</b>", _setting_page_buttons(grp_id, []))
    if action == "default_max_results":
        await save_group_settings(grp_id, "max_results", MAX_BTN)
        return await settings_group_callback(client, type("Q", (), {"data":f"grp_setting#max_results#{grp_id}", "from_user":query.from_user, "message":query.message, "answer":query.answer})())

    return await query.answer("ᴏᴘᴛɪᴏɴ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)


@Client.on_message(filters.command("cancel") & (filters.private | filters.group))
async def cancel_group_setting_input(client, message):
    key_candidates = [k for k in GROUP_SETTING_PENDING if k[0] == message.from_user.id]
    if not key_candidates:
        return
    key = key_candidates[-1]
    action = GROUP_SETTING_PENDING.pop(key, None)
    grp_id = key[1]
    target = {
        "set_caption": "caption", "set_template": "imdb", "delete_time": "auto_delete",
        "force_channel": "force_channel", "request_channel": "movie_req", "max_results": "max_results"
    }.get(action, "details")
    await message.reply_text(
        "ᴄᴀɴᴄᴇʟʟᴇᴅ ✅",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⋞ ʙᴀᴄᴋ ᴛᴏ ᴛʜɪs sᴇᴛᴛɪɴɢ", callback_data=f"grp_setting#{target}#{grp_id}")]]),
    )


@Client.on_message(filters.text & (filters.private | filters.group))
async def group_setting_input(client, message):
    user_id = message.from_user.id
    candidates = [k for k in GROUP_SETTING_PENDING if k[0] == user_id]
    if not candidates:
        return
    key = candidates[-1]
    grp_id = key[1]
    action = GROUP_SETTING_PENDING.get(key)
    if not action:
        return
    if not await is_check_admin(client, grp_id, user_id):
        GROUP_SETTING_PENDING.pop(key, None)
        return
    value = (message.text or "").strip()
    if value.startswith("/") and value.lower() != "/cancel":
        raise ContinuePropagation
    if not value:
        return await message.reply_text("ᴠᴀʟᴜᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ")
    if action == "max_results":
        try:
            value_int = int(value)
            if not 1 <= value_int <= 20:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ɴᴜᴍʙᴇʀ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 20")
        value = value_int
    elif action == "delete_time":
        try:
            raw = value.lower().replace(" ", "")
            if raw.endswith("h"):
                value = int(float(raw[:-1]) * 3600)
            elif raw.endswith("m"):
                value = int(float(raw[:-1]) * 60)
            elif raw.endswith("s"):
                value = int(float(raw[:-1]))
            else:
                # A plain number is treated as minutes for the settings UI.
                value = int(float(raw) * 60)
            if value < 1:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴛɪᴍᴇ ʟɪᴋᴇ <code>5</code>, <code>5m</code>, <code>300s</code> ᴏʀ <code>1h</code>")
    elif action == "force_channel":
        try:
            channels = [int(x.strip()) for x in re.split(r"[,\n ]+", value) if x.strip()]
            if not channels:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ɪᴅs, ᴇxᴀᴍᴘʟᴇ: -1001234567890,-1009876543210")
        value = channels
    elif action == "request_channel":
        try:
            value = int(value)
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ʀᴇǫ ᴄʜᴀɴɴᴇʟ ɪᴅ")
    key_name = {"force_channel": "fsub_channels", "request_channel": "request_channel", "set_caption": "caption", "set_template": "template"}.get(action, action)
    await save_group_settings(grp_id, key_name, value)
    if action == "force_channel" and value:
        await save_group_settings(grp_id, "fsub_id", value[0])
    GROUP_SETTING_PENDING.pop(key, None)
    await message.reply_text(
        "<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴜᴘᴅᴀᴛᴇᴅ ✅</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⋞ ʙᴀᴄᴋ ᴛᴏ ꜱᴇᴛᴛɪɴɢꜱ", callback_data=f"settings_group#{grp_id}")]]),
        parse_mode=enums.ParseMode.HTML,
    )

async def show_advanced(client, query, grp_id):
    settings = await get_settings(grp_id)
    status = "🔐 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ" if settings.get("is_verify", IS_VERIFY) else "🔗 ꜱʜᴏʀᴛʟɪɴᴋ"
    text = (
        "<b>⚙️ ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ</b>\n"
        "ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜱʜᴏʀᴛʟɪɴᴋꜱ ᴀɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴇᴛᴛɪɴɢꜱ ꜰʀᴏᴍ ʜᴇʀᴇ.\n\n"
        "<b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ 👇</b>\n"
        f"<b>📁 ꜰɪʟᴇ ᴍᴏᴅᴇ : {status}</b>"
    )
    buttons = [
        [InlineKeyboardButton("🔗 ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"adv_shortlinks#{grp_id}")],
        [InlineKeyboardButton("⏱ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ɢᴀᴘ", callback_data=f"adv_gaps#{grp_id}")],
        [InlineKeyboardButton("📹 ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"adv_tutorials#{grp_id}")],
        _back(f"adv_back_settings#{grp_id}"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_shortlinks(client, query, grp_id):
    settings = await get_settings(grp_id)
    lines = [
        "<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴠᴇʀɪꜰʏ ᴍᴏᴅᴇ</b>",
        "<b>ꜱᴇᴛ ʏᴏᴜʀ 1ꜱᴛ, 2ɴᴅ ᴀɴᴅ 3ʀᴅ ꜱʜᴏʀᴛʟɪɴᴋ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ...</b>",
    ]
    for label, domain, api in (("1ꜱᴛ", settings.get("shortner"), settings.get("api")), ("2ɴᴅ", settings.get("shortner_two"), settings.get("api_two")), ("3ʀᴅ", settings.get("shortner_three"), settings.get("api_three"))):
        if domain or api:
            lines.append(f"<b>ꜱʜᴏʀᴛʟɪɴᴋ {label}</b> - <code>{domain or ''}</code> <code>{api or ''}</code>")
    buttons = [
        [InlineKeyboardButton("1sᴛ sʜᴏʀᴛʟɪɴᴋ", callback_data=f"adv_short#1#{grp_id}"), InlineKeyboardButton("2ɴᴅ sʜᴏʀᴛʟɪɴᴋ", callback_data=f"adv_short#2#{grp_id}")],
        [InlineKeyboardButton("3ʀᴅ sʜᴏʀᴛʟɪɴᴋ", callback_data=f"adv_short#3#{grp_id}")],
        [InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"settings_group#{grp_id}")],
    ]
    await query.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_short_detail(client, query, grp_id, slot):
    settings = await get_settings(grp_id)
    key_domain = {1: "shortner", 2: "shortner_two", 3: "shortner_three"}[slot]
    key_api = {1: "api", 2: "api_two", 3: "api_three"}[slot]
    domain, api = settings.get(key_domain), settings.get(key_api)
    text = f"<b>ꜱʜᴏʀᴛᴇɴᴇʀ {slot} ꜱᴇᴛᴛɪɴɢꜱ:</b>"
    if domain or api:
        text += f"\n🌐 ᴅᴏᴍᴀɪɴ: <code>{domain or ''}</code>\n🔗 ᴀᴘɪ: <code>{api or ''}</code>"
    buttons = [
        [InlineKeyboardButton("sᴇᴛ", callback_data=f"adv_setshort#{slot}#{grp_id}"), InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"adv_remshort#{slot}#{grp_id}")],
        _back(f"adv_shortlinks#{grp_id}"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_gaps(client, query, grp_id):
    settings = await get_settings(grp_id)
    buttons = [
        [InlineKeyboardButton(f"ᴛɪᴍᴇ 1 · {settings.get('verify_time')}", callback_data=f"adv_gap#1#{grp_id}"), InlineKeyboardButton(f"ᴛɪᴍᴇ 2 · {settings.get('third_verify_time')}", callback_data=f"adv_gap#2#{grp_id}")],
        _back(f"adv_back_advanced#{grp_id}"),
    ]
    await query.message.edit_text("<b>ᴄʜᴏᴏsᴇ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ ᴛᴏ ᴍᴀɴᴀɢᴇ:</b>", reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_tutorials(client, query, grp_id):
    buttons = [
        [InlineKeyboardButton("1sᴛ ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"adv_tut#1#{grp_id}"), InlineKeyboardButton("2ɴᴅ ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"adv_tut#2#{grp_id}")],
        [InlineKeyboardButton("3ʀᴅ ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"adv_tut#3#{grp_id}")],
        [InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"settings_group#{grp_id}")],
    ]
    await query.message.edit_text("<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴛᴜᴛᴏʀɪᴀʟꜱ</b>\n\n<b>ꜱᴇʟᴇᴄᴛ ʏᴏᴜʀ 1ꜱᴛ, 2ɴᴅ ᴀɴᴅ 3ʀᴅ ᴛᴜᴛᴏʀɪᴀʟ...</b>", reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


async def show_tutorial_detail(client, query, grp_id, slot):
    settings = await get_settings(grp_id)
    key = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
    value = settings.get(key)
    text = f"<b>📹 Tutorial {slot} Settings:</b>"
    if value:
        text += f"\n🔗 ᴠᴀʟᴜᴇ: <code>{value}</code>"
    buttons = [
        [InlineKeyboardButton("sᴇᴛ", callback_data=f"adv_settut#{slot}#{grp_id}"), InlineKeyboardButton("ʀᴇᴍᴏᴠᴇ", callback_data=f"adv_remtut#{slot}#{grp_id}")],
        _back(f"adv_tutorials#{grp_id}"),
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^advanced_settings(?:#-?\d+)?$|^adv_"))
async def advanced_callback(client, query):
    data = query.data
    parts = data.split("#")
    try:
        grp_id = int(parts[-1])
    except (ValueError, TypeError):
        if query.message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            grp_id = query.message.chat.id
        else:
            return await query.answer("ᴇxᴘɪʀᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ", show_alert=True)

    if not await is_check_admin(client, grp_id, query.from_user.id):
        return await query.answer("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ", show_alert=True)

    if data.startswith("advanced_settings"):
        await query.answer()
        return await show_advanced(client, query, grp_id)
    if data.startswith("adv_back_settings"):
        await query.answer()
        return await show_main_settings(client, query, grp_id)
    if data.startswith("adv_back_advanced"):
        await query.answer()
        return await show_advanced(client, query, grp_id)
    if data.startswith("adv_shortlinks"):
        await query.answer()
        return await show_shortlinks(client, query, grp_id)
    if data.startswith("adv_gaps"):
        await query.answer()
        return await show_gaps(client, query, grp_id)
    if data.startswith("adv_tutorials"):
        await query.answer()
        return await show_tutorials(client, query, grp_id)
    if data.startswith("adv_toggle_verify"):
        # Legacy callback: route File Mode to the single canonical settings implementation.
        await query.answer()
        proxy = type("Q", (), {"data": f"grp_setting#files_mode#{grp_id}", "from_user": query.from_user, "message": query.message, "answer": query.answer})()
        return await settings_group_callback(client, proxy)
    if data.startswith("adv_cancel"):
        state = PENDING.pop((grp_id, query.from_user.id), None)
        await query.answer("ᴄᴀɴᴄᴇʟʟᴇᴅ")
        if state and state.get("type") == "short":
            return await show_short_detail(client, query, grp_id, int(state.get("slot", 1)))
        if state and state.get("type") == "tutorial":
            return await show_tutorial_detail(client, query, grp_id, int(state.get("slot", 1)))
        if state and state.get("type") == "gap":
            return await show_gaps(client, query, grp_id)
        return await show_advanced(client, query, grp_id)
    if data.startswith("adv_short#"):
        await query.answer()
        return await show_short_detail(client, query, grp_id, int(parts[1]))
    if data.startswith("adv_setshort#"):
        slot = int(parts[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "short", "slot": slot, "stage": "domain"}
        await query.answer()
        return await query.message.edit_text("<b>ꜱᴇɴᴅ ɴᴇᴡ ꜱʜᴏʀᴛɴᴇʀ ᴡᴇʙꜱɪᴛᴇ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.", reply_markup=InlineKeyboardMarkup([_cancel_button(grp_id)]), parse_mode=enums.ParseMode.HTML)
    if data.startswith("adv_remshort#"):
        slot = int(parts[1])
        keys = {1: ("shortner", "api"), 2: ("shortner_two", "api_two"), 3: ("shortner_three", "api_three")} [slot]
        await save_group_settings(grp_id, keys[0], "")
        await save_group_settings(grp_id, keys[1], "")
        await query.answer(f"sʜᴏʀᴛᴇɴᴇʀ {slot} ʀᴇᴍᴏᴠᴇᴅ")
        return await show_short_detail(client, query, grp_id, slot)
    if data.startswith("adv_gap#"):
        slot = int(parts[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "gap", "slot": slot, "stage": "value"}
        await query.answer()
        return await query.message.edit_text(f"<b>ꜱᴇɴᴅ ᴛɪᴍᴇ {slot} ᴠᴀʟᴜᴇ ɪɴ ꜱᴇᴄᴏɴᴅꜱ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.", reply_markup=InlineKeyboardMarkup([_cancel_button(grp_id)]), parse_mode=enums.ParseMode.HTML)
    if data.startswith("adv_tut#"):
        await query.answer()
        return await show_tutorial_detail(client, query, grp_id, int(parts[1]))
    if data.startswith("adv_settut#"):
        slot = int(parts[1])
        PENDING[(grp_id, query.from_user.id)] = {"type": "tutorial", "slot": slot, "stage": "value"}
        await query.answer()
        return await query.message.edit_text(f"<b>📹 sᴇɴᴅ ᴛᴜᴛᴏʀɪᴀʟ {slot} ᴜʀʟ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.", reply_markup=InlineKeyboardMarkup([_cancel_button(grp_id)]), parse_mode=enums.ParseMode.HTML)
    if data.startswith("adv_remtut#"):
        slot = int(parts[1])
        key = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
        await save_group_settings(grp_id, key, "")
        await query.answer(f"ᴛᴜᴛᴏʀɪᴀʟ {slot} ʀᴇᴍᴏᴠᴇᴅ")
        return await show_tutorial_detail(client, query, grp_id, slot)


@Client.on_message(filters.command("cancel") & (filters.group | filters.private))
async def advanced_cancel(client, message):
    # In private chat, find the active group belonging to this user.
    key = None
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        key = (message.chat.id, message.from_user.id)
    else:
        matches = [k for k in PENDING if k[1] == message.from_user.id]
        if matches:
            key = matches[-1]
    if key not in PENDING:
        raise ContinuePropagation
    PENDING.pop(key, None)
    await message.reply_text("<b>ᴘʀᴏᴄᴇꜱꜱ ᴄᴀɴᴄᴇʟʟᴇᴅ ✅</b>")


@Client.on_message(filters.text & (filters.group | filters.private))
async def advanced_input(client, message):
    user_id = message.from_user.id
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        key = (message.chat.id, user_id)
    else:
        matches = [k for k in PENDING if k[1] == user_id]
        if not matches:
            raise ContinuePropagation
        key = matches[-1]
    state = PENDING.get(key)
    if not state:
        raise ContinuePropagation
    grp_id = key[0]
    if not await is_check_admin(client, grp_id, user_id):
        PENDING.pop(key, None)
        raise ContinuePropagation
    value = message.text.strip()
    if not value:
        return await message.reply_text("ᴠᴀʟᴜᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ")

    if state["type"] == "short" and state["stage"] == "domain":
        state["domain"] = value.replace("https://", "").replace("http://", "").rstrip("/")
        state["stage"] = "api"
        return await message.reply_text("<b>ɴᴏᴡ ꜱᴇɴᴅ ꜱʜᴏʀᴛɴᴇʀ ᴀᴘɪ</b>\n\nᴜꜱᴇ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ.", reply_markup=InlineKeyboardMarkup([_cancel_button(grp_id)]), parse_mode=enums.ParseMode.HTML)

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
        await save_group_settings(grp_id, keys[0], domain)
        await save_group_settings(grp_id, keys[1], api)
        PENDING.pop(key, None)
        return await message.reply_text(f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴜᴘᴅᴀᴛᴇᴅ ꜱʜᴏʀᴛᴇɴᴇʀ {slot} ᴠᴀʟᴜᴇꜱ ✅</b>\nᴡᴇʙꜱɪᴛᴇ: <code>{domain}</code>\nᴀᴘɪ: <code>{api}</code>", reply_markup=InlineKeyboardMarkup([_back(f"adv_shortlinks#{grp_id}")]), parse_mode=enums.ParseMode.HTML)

    if state["type"] == "gap":
        try:
            seconds = int(value)
            if seconds < 0:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ᴏꜰ ꜱᴇᴄᴏɴᴅꜱ ᴏʀ /cancel")
        slot = state["slot"]
        key_name = "verify_time" if slot == 1 else "third_verify_time"
        await save_group_settings(grp_id, key_name, seconds)
        PENDING.pop(key, None)
        return await message.reply_text(f"<b>ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ {slot} ᴜᴘᴅᴀᴛᴇᴅ ✅</b>\nᴛɪᴍᴇ: <code>{seconds}</code>", reply_markup=InlineKeyboardMarkup([_back(f"adv_gaps#{grp_id}")]), parse_mode=enums.ParseMode.HTML)

    if state["type"] == "tutorial":
        if not (value.startswith("http://") or value.startswith("https://")):
            return await message.reply_text("❌ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ʜᴛᴛᴘ/ʜᴛᴛᴘs ᴜʀʟ ᴏʀ /cancel")
        slot = state["slot"]
        key_name = {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}[slot]
        await save_group_settings(grp_id, key_name, value)
        PENDING.pop(key, None)
        return await message.reply_text(f"<b>ᴛᴜᴛᴏʀɪᴀʟ {slot} ᴜᴘᴅᴀᴛᴇᴅ ✅</b>\nᴠᴀʟᴜᴇ: <code>{value}</code>", reply_markup=InlineKeyboardMarkup([_back(f"adv_tutorials#{grp_id}")]), parse_mode=enums.ParseMode.HTML)
