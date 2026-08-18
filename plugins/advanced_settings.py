import requests
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import *
from utils import get_settings, save_group_settings, is_check_admin, get_readable_time

PENDING = {}


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
    # Compatibility wrapper: the canonical 2-column settings grid lives in commands.py.
    from plugins.commands import _show_main_settings
    return await _show_main_settings(client, query, grp_id)


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
        from plugins.commands import _show_main_settings
        return await _show_main_settings(client, query, grp_id)
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
        from plugins.commands import _show_main_settings, settings_group_callback
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
