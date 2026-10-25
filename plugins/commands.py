import os
import html
import requests
import logging
from functools import wraps
import random
import asyncio
import string
import pytz
from datetime import datetime as dt, timedelta
from Script import script
from pyrogram import Client, filters, enums, StopPropagation
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from database.ia_filterdb import (
    Media,
    get_file_details,
    get_bad_files,
    unpack_new_file_id,
)
from database.users_chats_db import db
from database.config_db import mdb
from database.topdb import JsTopDB
from database.jsreferdb import referdb
from plugins.pm_filter import auto_filter
from utils import (
    formate_file_name,
    get_settings,
    save_group_settings,
    is_req_subscribed,
    is_subscribed,
    get_size,
    get_shortlink,
    is_check_admin,
    get_status,
    temp,
    get_readable_time,
    save_default_settings,
)
import re
import base64
from shortzy import Shortzy
from info import *
from language import (
    language_markup, has_saved_language, get_user_language, tr,
    core_tr, home_tr, verify_tr, small_caps,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _debug_handler(func):
    """Log entry, completion and full traceback for commands/callbacks."""
    @wraps(func)
    async def _wrapped(client, event, *args, **kwargs):
        is_callback = hasattr(event, "data") and hasattr(event, "answer")
        user = getattr(getattr(event, "from_user", None), "id", None)
        chat = getattr(getattr(event, "chat", None), "id", None)
        if chat is None:
            chat = getattr(getattr(getattr(event, "message", None), "chat", None), "id", None)
        payload = getattr(event, "data", None) if is_callback else getattr(event, "text", None)
        logger.info("HANDLER_ENTER module=%s handler=%s kind=%s user=%s chat=%s payload=%r", __name__, func.__name__, "callback" if is_callback else "message", user, chat, payload)
        try:
            result = await func(client, event, *args, **kwargs)
            logger.info("HANDLER_OK module=%s handler=%s user=%s", __name__, func.__name__, user)
            return result
        except StopPropagation:
            logger.info("HANDLER_STOP_PROPAGATION module=%s handler=%s user=%s", __name__, func.__name__, user)
            raise
        except Exception as exc:
            logger.exception("HANDLER_FAILED module=%s handler=%s kind=%s user=%s chat=%s payload=%r error_type=%s error=%s", __name__, func.__name__, "callback" if is_callback else "message", user, chat, payload, type(exc).__name__, exc)
            if is_callback:
                try:
                    await event.answer("This button failed. The error was logged; please try again later.", show_alert=True)
                except Exception:
                    logger.exception("Could not show failure alert for handler=%s user=%s", func.__name__, user)
            raise
    return _wrapped


async def _build_fsub_caption(client, settings, channel_ids):
    """Add readable channel names and IDs to the force-subscription caption."""
    lines = []
    details = settings.get("fsub_channel_details") or {}
    seen = set()
    for raw_id in channel_ids:
        try:
            channel_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if channel_id in seen:
            continue
        seen.add(channel_id)
        detail = details.get(str(channel_id), {}) if isinstance(details, dict) else {}
        title = str(detail.get("title") or "").strip()
        username = str(detail.get("username") or "").strip().lstrip("@")
        if not title:
            try:
                chat = await client.get_chat(channel_id)
                title = str(getattr(chat, "title", None) or getattr(chat, "first_name", None) or "Channel")
                username = str(getattr(chat, "username", None) or username).strip().lstrip("@")
            except Exception:
                title = "Channel title unavailable"
        title_html = html.escape(title)
        username_text = f" (@{html.escape(username)})" if username else ""
        line = f"• <b>{title_html}</b>{username_text} — <code>{channel_id}</code>"
        # Telegram photo captions have a 1024-character limit. Keep the static
        # instructions and add as many required channels as safely fit.
        candidate = "\n".join(lines + [line])
        if len(script.FORCESUB_TEXT) + len("\n\n<b>Required channels:</b>\n") + len(candidate) > 1000:
            lines.append("• Additional required channels are shown in the Join buttons.")
            break
        lines.append(line)
    if not lines:
        return script.FORCESUB_TEXT
    return script.FORCESUB_TEXT + "\n\n<b>Required channels:</b>\n" + "\n".join(lines)
HOME_AUTO_DELETE = max(60, int(os.environ.get("HOME_AUTO_DELETE", "600")))


def _ist_now():
    return dt.now(pytz.timezone("Asia/Kolkata"))


async def _is_owner_shortener(domain, api=None):
    """Return True only for one of the three shorteners owned by OWNER_ID."""
    try:
        int(OWNER_ID)
    except (TypeError, ValueError):
        return False
    domain = str(domain or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    api = str(api or "").strip()
    if not domain or not api:
        return False
    owner_pairs = await db.get_owner_shortener_pairs()
    return any(
        (domain, api) == (
            str(owner_domain).strip().lower().replace("https://", "").replace("http://", "").rstrip("/"),
            str(owner_api).strip(),
        )
        for owner_domain, owner_api in (owner_pairs or [])
        if owner_domain and owner_api
    )


def _is_owner_tracking_record(record):
    """Only verification attempts explicitly stamped with BOT OWNER_ID are trackable."""
    if not record or not record.get("owner_shortener", False):
        return False
    try:
        return int(record.get("owner_id")) == int(OWNER_ID)
    except (TypeError, ValueError):
        return False


async def _shortener_log(client, log_chat, event, user, step, **fields):
    """Write shortener tracking events in the exact requested compact format."""
    if not log_chat:
        return

    group_id = fields.get("Group")
    is_direct_pm = group_id in (None, "", 0, "0")
    group_name = "DIRECT PM"
    group_link = "—"
    if not is_direct_pm:
        try:
            chat = await client.get_chat(int(group_id))
            group_name = chat.title or str(group_id)
            if chat.username:
                group_link = f"https://t.me/{chat.username}"
            elif getattr(chat, "invite_link", None):
                group_link = chat.invite_link
            else:
                group_link = "Private / Invite link unavailable"
        except Exception:
            group_name = str(group_id)
            group_link = "Unavailable"

    bot_name = "Unknown Bot"
    bot_username = ""
    try:
        me = await client.get_me()
        bot_name = me.first_name or me.username or "Unknown Bot"
        bot_username = f"@{me.username}" if me.username else ""
    except Exception:
        pass

    now = _ist_now()
    date_text = now.strftime("%-d %B %Y time %-I:%M%p %A")
    status = f"{int(step or 1)}/3"
    lines = [
        f"<b>🔎 SHORTENER TRACK — {event}</b>",
        f"👤 ᴜꜱᴇʀ: {user.mention} [ <code>{user.id}</code> ]",
        f"📊 ꜱᴛᴀᴛᴜꜱ: {status}",
        f"📆 ᴅᴀᴛᴇ: {date_text}",
        f"🤖 Bot: {bot_name} {bot_username}".rstrip(),
        f"🧩 Verified by bot: {fields.get('BotLabel', bot_name)}",
        f"🏷️ Group Name: {group_name}",
        f"🔗 Group Link: {group_link}",
        f"Group: {0 if is_direct_pm else group_id}",
    ]

    mode = fields.get("Mode")
    if mode is not None and mode != "":
        lines.append(f"Mode: {mode}")
    domain = fields.get("Domain")
    if domain:
        lines.append(f"Domain: {domain}")
    api_key = fields.get("Api key")
    if api_key:
        lines.append(f"Api key: {api_key}")
    short_url = fields.get("ShortURL")
    if short_url:
        lines.append(f"ShortURL: {short_url}")

    # Keep diagnostics that are not part of the user-facing requested template
    # out of SHORTLINK_CREATED/SHORTLINK_CLICKED messages. Error events may add
    # their reason for debugging.
    if event == "SHORTENER_API_ERROR" and fields.get("Error"):
        lines.append(f"Error: {fields['Error']}")

    try:
        await client.send_message(
            int(log_chat),
            "\n".join(lines),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Could not write shortener diagnostic log")


async def _mark_get_file_click(client, user, group_id, delivery_key):
    """Record the final Telegram Get File/Send All deep-link separately."""
    try:
        record = await db.get_latest_verification_for_delivery(user.id, group_id, delivery_key)
        if (not record or not record.get("verified") or record.get("get_file_clicked_at")
                or not _is_owner_tracking_record(record)):
            return
        now = _ist_now()
        await db.update_verify_id_info(
            user.id, record["hash"],
            {"get_file_clicked_at": now, "get_file_clicked": True},
        )
        settings = await get_settings(group_id)
        step = int(record.get("step") or record.get("verification_step") or 1)
        await _shortener_log(
            client, (LINK_TRACK_CHANNEL or LOG_VR_CHANNEL), "GET_FILE_CLICKED", user, step,
            Group=group_id, Mode=record.get("mode", "file"),
            Domain=record.get("shortener_domain", "unknown"),
            VerifyID=record.get("hash", ""), Delivery=delivery_key,
            **{"Shortener return": "YES"},
        )
    except Exception:
        logger.exception("Could not record Get File click")


def _global_home_markup(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(home_tr(lang, "add_group"), url=f"http://telegram.dog/{temp.U_NAME}?startgroup=start")],
        [InlineKeyboardButton(home_tr(lang, "disable_ads"), callback_data="jisshupremium"), InlineKeyboardButton(home_tr(lang, "special"), callback_data="special")],
        [InlineKeyboardButton(home_tr(lang, "help"), callback_data="help"), InlineKeyboardButton(home_tr(lang, "about"), callback_data="about")],
        [InlineKeyboardButton(home_tr(lang, "earn"), callback_data="earn")],
        [InlineKeyboardButton(tr(lang, "language_button"), callback_data="global_lang:menu")],
        [InlineKeyboardButton(home_tr(lang, "clean"), callback_data="clean_home")],
    ])


def _file_mode_greeting():
    hour = dt.now(pytz.timezone("Asia/Kolkata")).hour
    if 5 <= hour < 12:
        return "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ"
    if 12 <= hour < 17:
        return "ɢᴏᴏᴅ ᴀғᴛᴇʀɴᴏᴏɴ"
    if 17 <= hour < 21:
        return "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ"
    return "ɢᴏᴏᴅ ɴɪɢʜᴛ"


def _file_mode_caption(settings, file, mention):
    template = settings.get("file_mode_caption") or FILE_MODE_CAPTION
    return template.format(
        greeting=_file_mode_greeting(),
        mention=mention or "ᴜsᴇʀ",
        file_name=formate_file_name(file.file_name),
        file_size=get_size(file.file_size),
        file_caption=file.caption or "",
    )


def _file_mode_markup(settings, file_id):
    tutorial = settings.get("tutorial", TUTORIAL)
    mode = settings.get("file_mode_type", "verify")
    if mode == "shortlink":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📎 ꜱʜᴏʀᴛʟɪɴᴋ", callback_data=f"stream#{file_id}")],
            [InlineKeyboardButton("💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ", callback_data="getpremium")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 ꜰɪʟᴇ", callback_data=f"stream#{file_id}"),
         InlineKeyboardButton("ʜᴏᴡ ᴛᴏ ᴠᴇʀɪғʏ ❓", url=tutorial)],
        [InlineKeyboardButton("💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ", callback_data="getpremium")],
    ])


@Client.on_callback_query(filters.regex(r"^global_lang:"))
@_debug_handler
async def global_language_callback(client: Client, query):
    value = query.data.split(":", 1)[1]
    logger.info("GLOBAL_LANG callback received: user=%s data=%r chat=%s message=%s", getattr(query.from_user, "id", None), query.data, getattr(getattr(query, "message", None), "chat", None) and query.message.chat.id, getattr(getattr(query, "message", None), "id", None))
    if value == "menu":
        lang = await get_user_language(query.from_user.id, query.from_user)
        await query.answer()
        text = tr(lang, "language_title") + "\n\n" + tr(lang, "language_body")
        logger.info("GLOBAL_LANG showing picker: user=%s", query.from_user.id)
        return await _edit_language_message(query, text, language_markup())
    from language import LANGUAGES
    if value not in LANGUAGES:
        return await query.answer("Language unavailable.", show_alert=True)
    # Persist the language before changing the message. If MongoDB is down,
    # keep the picker visible and tell the user instead of pretending it saved.
    logger.info("GLOBAL_LANG saving selection: user=%s language=%s", query.from_user.id, value)
    try:
        await db.update_user({
            "id": int(query.from_user.id),
            "name": query.from_user.first_name or "User",
            "language": value,
            "language_code": value,
        })
    except Exception:
        logger.exception("Could not save global language for user %s", query.from_user.id)
        try:
            await query.answer("Could not save your language right now. Please try again.", show_alert=True)
        except Exception:
            pass
        return

    try:
        await query.answer(tr(value, "language_saved"), show_alert=True)
    except Exception:
        pass
    logger.info("GLOBAL_LANG saved successfully: user=%s language=%s; refreshing home UI", query.from_user.id, value)
    # Rebuild the normal home menu immediately after the language is persisted.
    markup = _global_home_markup(value)
    try:
        if query.message and (query.message.photo or query.message.video or query.message.animation or query.message.document):
            await query.message.edit_caption(
                caption=core_tr(value, "start", mention=query.from_user.mention, status=get_status()),
                reply_markup=markup, parse_mode=enums.ParseMode.HTML,
            )
        elif query.message:
            await query.message.edit_text(
                core_tr(value, "start", mention=query.from_user.mention, status=get_status()),
                reply_markup=markup, parse_mode=enums.ParseMode.HTML,
            )
        else:
            logger.warning("GLOBAL_LANG selection saved but callback has no message to refresh: user=%s language=%s", query.from_user.id, value)
    except Exception as exc:
        from pyrogram.errors import MessageNotModified
        if isinstance(exc, MessageNotModified):
            logger.info("GLOBAL_LANG home UI already up to date: user=%s language=%s", query.from_user.id, value)
        else:
            logger.exception("GLOBAL_LANG failed refreshing home UI: user=%s language=%s", query.from_user.id, value)


async def _edit_language_message(query, text, markup):
    try:
        if query.message and (query.message.photo or query.message.video or query.message.animation):
            return await query.message.edit_caption(caption=text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        return await query.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
    except Exception as exc:
        from pyrogram.errors import MessageNotModified
        if isinstance(exc, MessageNotModified):
            return
        logger.exception("Could not display global language picker")


async def _delete_home_later(client, user_id, message_id, delay):
    try:
        await asyncio.sleep(delay)
        await client.delete_messages(user_id, message_id)
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^clean_home$"), group=-1)
@_debug_handler
async def clean_home_callback(client, query):
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer("Home cleaned 🧹")
    raise StopPropagation


async def _new_shortener_make_url(domain, api, target):
    """Create a URL for the group-specific three-step shortener.

    LinkCut (linkcut.org) has its own GET API and JSON schema; it is not
    compatible with assuming every provider follows Shortzy's API format.
    Other providers continue to use the existing Shortzy integration.
    """
    if not domain or not api or not target:
        return None
    raw_domain = str(domain).strip()
    if not raw_domain:
        return None
    normalized_domain = raw_domain.rstrip("/")
    if normalized_domain.startswith(("http://", "https://")):
        normalized_domain = normalized_domain.split("://", 1)[1]
    normalized_domain = normalized_domain.split("/", 1)[0].strip().rstrip(".").lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]
    if not normalized_domain:
        return None

    if normalized_domain == "linkcut.org":
        import aiohttp
        endpoint = "https://linkcut.org/api"
        timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    endpoint,
                    params={"api": str(api).strip(), "url": str(target)},
                    headers={"Accept": "application/json", "User-Agent": "IMDXBot/1.0"},
                ) as response:
                    body = await response.text()
                    if response.status != 200:
                        logger.warning(
                            "LinkCut API returned HTTP %s (response starts: %r)",
                            response.status, body[:180],
                        )
                        return None
                    try:
                        payload = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        logger.warning("LinkCut API returned non-JSON response (starts: %r)", body[:180])
                        return None
                    if not isinstance(payload, dict):
                        logger.warning("LinkCut API returned unexpected JSON type: %s", type(payload).__name__)
                        return None
                    status = str(payload.get("status", "")).lower()
                    short_url = payload.get("shortenedUrl")
                    if status == "success" and isinstance(short_url, str):
                        short_url = short_url.strip()
                        if short_url.startswith(("https://", "http://")):
                            return short_url
                    logger.warning(
                        "LinkCut API reported failure: status=%r message=%r",
                        payload.get("status"), payload.get("message"),
                    )
                    return None
        except asyncio.TimeoutError:
            logger.warning("LinkCut API request timed out")
            return None
        except Exception:
            logger.exception("LinkCut API request failed")
            return None

    shortener = Shortzy(str(api).strip(), normalized_domain)
    try:
        result = await shortener.convert(target)
        if result:
            return str(result)
    except Exception:
        logger.exception("New shortener conversion failed")
    try:
        result = await shortener.get_quick_link(target)
        return str(result) if result else None
    except Exception:
        logger.exception("New shortener quick-link fallback failed")
        return None


async def _new_shortener_send_step(client, message, user_id, group_id, delivery_key, mode, step):
    """Issue a single date/user/group-bound attempt and send its short link."""
    from database.new_shortener import begin_step, save_attempt
    settings = await get_settings(int(group_id))
    suffix = str(step)
    domain = settings.get(f"new_shortener_step{suffix}_url")
    api = settings.get(f"new_shortener_api{suffix}")
    tutorial = settings.get(f"new_shortener_tutorial{suffix}")
    if not tutorial:
        tutorial = settings.get(
            {1: "tutorial", 2: "tutorial_2", 3: "tutorial_3"}.get(step, "tutorial"),
            {1: TUTORIAL, 2: TUTORIAL_2, 3: TUTORIAL_3}.get(step, TUTORIAL),
        )
    if not domain or not api:
        await message.reply_text(
            f"⚠️ The group administrator has not configured New Shortener Step {step}. Please contact the group admin."
        )
        return False
    token = await begin_step(user_id, group_id, step)
    if not token:
        await message.reply_text("This verification step is no longer valid. Please request the movie link again.")
        return False
    await save_attempt(token, user_id, group_id, step, delivery_key, mode)
    try:
        from database.users_chats_db import db
        await db.misc.update_one(
            {"_id": f"new_shortener_attempt:{token}"},
            {"$set": {"shortener_domain": str(domain or "")}},
        )
    except Exception:
        logger.exception("Could not save new shortener domain for tracking")
    bot_username = (getattr(temp, "U_NAME", "") or "").lstrip("@")
    if not bot_username:
        from database.new_shortener import cancel_step
        await cancel_step(user_id, group_id, step, token)
        await message.reply_text("⚠️ The bot username is unavailable. Please try again later.")
        return False
    target = f"https://t.me/{bot_username}?start=ns_{token}"
    short_url = await _new_shortener_make_url(domain, api, target)
    if not short_url:
        from database.new_shortener import cancel_step
        await cancel_step(user_id, group_id, step, token)
        await message.reply_text("⚠️ Shortener service is temporarily unavailable. Please try again later.")
        return False
    # Match the legacy setshortlink presentation only. Keep the new short URL,
    # token, attempt, and three-step verification logic above/below unchanged.
    ui_lang = await get_user_language(user_id, message.from_user)
    short_file = (await get_file_details(delivery_key) or [None])[0]
    file_name = formate_file_name(short_file.file_name) if short_file else "File"
    file_size = get_size(short_file.file_size) if short_file else "N/A"
    caption = verify_tr(
        ui_lang, f"short{step}", mention=message.from_user.mention,
        status=get_status(), greeting=_file_mode_greeting(),
        name=file_name, size=file_size,
    )
    verify_label = {"hi": "शॉर्टलिंक", "ta": "SHORTLINK", "te": "SHORTLINK",
                    "kn": "SHORTLINK", "ml": "SHORTLINK", "bn": "SHORTLINK",
                    "mr": "SHORTLINK", "gu": "SHORTLINK", "pa": "SHORTLINK",
                    "ur": "SHORTLINK", "as": "SHORTLINK", "ne": "SHORTLINK",
                    "hinglish": "SHORTLINK"}.get(ui_lang, "SHORTLINK")
    tutorial_label = {"hi": "कैसे डाउनलोड करें", "hinglish": "DOWNLOAD KAISE KARE",
                      "as": "ডাউনলোড কেনেকৈ কৰিব", "bn": "কীভাবে ডাউনলোড করবেন"}.get(
                          ui_lang, "VERIFY HOW TO DOWNLOAD")
    premium_label = {"hi": "Premium खरीदें", "ta": "Premium வாங்க",
                     "te": "Premium కొనండి", "kn": "Premium ಖರೀದಿಸಿ",
                     "ml": "Premium വാങ്ങുക", "bn": "Premium কিনুন",
                     "mr": "Premium घ्या", "gu": "Premium ખરીદો",
                     "pa": "Premium ਲਵੋ", "ur": "Premium خریدیں",
                     "as": "Premium ক্ৰয় কৰক", "ne": "Premium किन्नुहोस्",
                     "hinglish": "PREMIUM LO"}.get(ui_lang, "BUY PREMIUM")
    buttons = [[InlineKeyboardButton(f"🔗 {verify_label} {step}/3 🔗", url=short_url)]]
    if tutorial:
        buttons[0].append(InlineKeyboardButton(tutorial_label, url=str(tutorial)))
    buttons.append([InlineKeyboardButton(premium_label, callback_data="getpremium")])
    sent_shortener_message = await message.reply_text(
        caption,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML,
        protect_content=bool(settings.get("file_secure", PROTECT_CONTENT)),
    )
    # Follow the group's existing auto-delete setting and delay for shortlink
    # prompts too. Run deletion in the background so verification can continue.
    if settings.get("auto_delete", False):
        try:
            delete_delay = max(1, int(settings.get("delete_time", FILE_AUTO_DEL_TIMER)))
        except (TypeError, ValueError):
            delete_delay = max(1, int(FILE_AUTO_DEL_TIMER))

        async def _delete_shortener_prompt_after_delay(sent_message, delay):
            await asyncio.sleep(delay)
            try:
                await sent_message.delete()
            except Exception:
                logger.debug("Could not auto-delete shortener prompt", exc_info=True)

        asyncio.create_task(_delete_shortener_prompt_after_delay(sent_shortener_message, delete_delay))
    return True


def _new_shortener_gap_active(state, settings):
    """Whether the user is still inside the configured file-access gap after step 1 or 2."""
    completed_step = int(state.get("completed_step", 0) or 0)
    if completed_step not in (1, 2):
        return False
    completed_at = state.get("last_completed_at")
    if not completed_at:
        return False
    try:
        now = dt.now(pytz.timezone("Asia/Kolkata"))
        expires_at = state.get("gap_expires_at")
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = pytz.UTC.localize(expires_at)
            return now < expires_at.astimezone(pytz.timezone("Asia/Kolkata"))
        # Backward compatibility for state created before explicit expiry was stored.
        if completed_at.tzinfo is None:
            completed_at = pytz.UTC.localize(completed_at)
        completed_at = completed_at.astimezone(pytz.timezone("Asia/Kolkata"))
        gap_key = "new_shortener_gap1" if completed_step == 1 else "new_shortener_gap2"
        gap_seconds = max(0, int(settings.get(gap_key, 0) or 0))
        elapsed = (now - completed_at).total_seconds()
        return elapsed < gap_seconds
    except (TypeError, ValueError):
        return False


async def _new_shortener_return(client, message, token):
    """Validate a shortener return, grant the configured gap, then progress."""
    from database.new_shortener import consume_attempt, accept_step, get_attempt
    attempt = await get_attempt(token)
    if not attempt or int(attempt.get("user_id", 0)) != int(message.from_user.id):
        await message.reply_text("⚠️ This verification link is invalid, expired, or belongs to another user.")
        return True
    user_id = int(attempt["user_id"])
    group_id = int(attempt["group_id"])
    step = int(attempt["step"])
    settings = await get_settings(group_id)
    if not settings.get("new_shortener_enabled", False):
        await message.reply_text("New Shortener verification is disabled for this group. Request the movie link again.")
        return True
    claimed = await consume_attempt(token, user_id, group_id, step)
    gap_key = "new_shortener_gap1" if step == 1 else "new_shortener_gap2"
    try:
        gap_seconds = max(0, int(settings.get(gap_key, 0) or 0)) if step < 3 else 0
    except (TypeError, ValueError):
        gap_seconds = 0
    if not claimed or not await accept_step(
        user_id, group_id, step, token, enabled=True, gap_seconds=gap_seconds
    ):
        await message.reply_text("⚠️ This verification step has expired or was already used. Request the movie link again.")
        return True
    delivery_key = str(attempt.get("delivery_key") or "")
    mode = str(attempt.get("mode") or "file")
    try:
        await _shortener_log(
            client, LOG_VR_CHANNEL, "NEW_SHORTENER_VERIFIED", message.from_user, step,
            Group=group_id, Mode=mode, BotLabel="Devil",
            Domain=str(attempt.get("shortener_domain") or "configured step " + str(step)),
            VerifyID=token, **{"Shortener return": "YES"},
        )
    except Exception:
        logger.exception("Could not write new shortener success log")
    payload_prefix = "allfilesmode" if mode == "allfiles" else "filemode"
    payload = f"{payload_prefix}_{group_id}_{delivery_key}"
    if step < 3:
        # Legacy behavior: completing a step grants access to files during the
        # configured gap. The next shortener is required only after that gap.
        gap_key = "new_shortener_gap1" if step == 1 else "new_shortener_gap2"
        try:
            gap_seconds = max(0, int(settings.get(gap_key, 0) or 0))
        except (TypeError, ValueError):
            gap_seconds = 0
        await message.reply_text(
            f"✅ <b>Step {step}/3 verified.</b> You can access files for {gap_seconds} seconds before the next verification step.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 GET FILE", url=f"https://t.me/{temp.U_NAME}?start={payload}")]]),
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "✅ <b>Verification completed.</b> Tap below to receive your requested file.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 GET FILE", url=f"https://t.me/{temp.U_NAME}?start={payload}")]]),
            parse_mode=enums.ParseMode.HTML,
        )
    return True


@Client.on_message(filters.command("start") & filters.incoming)
@_debug_handler
async def start(client: Client, message):
    logger.info("START_HANDLER entered: chat_id=%s chat_type=%s message_id=%s from_user_id=%s text=%r", getattr(getattr(message, "chat", None), "id", None), getattr(getattr(message, "chat", None), "type", None), getattr(message, "id", None), getattr(getattr(message, "from_user", None), "id", None), (getattr(message, "text", None) or "")[:120])
    # Reactions are cosmetic only. Some chats/bot API versions reject them;
    # never let a failed reaction abort /start, file delivery, or verification.
    try:
        await message.react(emoji=random.choice(REACTIONS))
    except Exception:
        logger.debug("Could not react to /start; continuing normally", exc_info=True)
    m = message
    user_id = m.from_user.id
    # IMPORTANT: verification/shortlink deep-links are handled before the
    # first-time language picker. A shortener return is also a /start link;
    # blocking it here leaves the user stuck at /start. New verification
    # returns use a short server-side token instead of embedding delivery state.
    if message.chat.type == enums.ChatType.PRIVATE and len(m.command) == 2 and m.command[1].startswith("settings_"):
        from plugins.advanced_settings import show_group_list, show_group_settings
        try:
            grp_id = int(m.command[1].split("_", 1)[1])
        except (TypeError, ValueError):
            return await show_group_list(client, message)
        return await show_group_settings(client, message, grp_id)
    verification_return_mode = None
    # Telegram normally exposes deep-link payloads through message.command, but
    # some clients/redirect chains can leave the payload only in message.text.
    # Normalize both forms so a shortener return can never fall through to the
    # ordinary /start handler and appear to be stuck.
    start_payload = ""
    try:
        if len(getattr(m, "command", []) or []) >= 2:
            start_payload = str(m.command[1] or "").strip()
        if not start_payload and getattr(m, "text", None):
            parts = str(m.text).split(maxsplit=1)
            if len(parts) == 2:
                start_payload = parts[1].strip()
    except Exception:
        start_payload = ""

    logger.info("START_HANDLER parsed: user=%s payload=%s", user_id, start_payload[:80])
    if start_payload.startswith("ns_"):
        token = start_payload[3:].strip()
        if not token:
            await message.reply_text("⚠️ Invalid verification link. Please request the movie link again.")
            return
        await _new_shortener_return(client, message, token)
        return
    if start_payload.startswith("vr_"):
        logger.info("Processing verification return token for user=%s", user_id)
        # New verification-return links carry only a short opaque token.
        # The original user/group/delivery data stays in MongoDB.
        return_token = start_payload[3:].strip()
        if not return_token:
            await message.reply_text("<b>⚠️ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ʟɪɴᴋ ɪs ɪɴᴠᴀʟɪᴅ. ᴘʟᴇᴀsᴇ ɢᴇɴᴇʀᴀᴛᴇ ᴀ ɴᴇᴡ ᴏɴᴇ.</b>", parse_mode=enums.ParseMode.HTML)
            return
        try:
            verify_id_info = await db.get_verify_id_by_return_token(return_token)
        except Exception:
            logger.exception("Verification return token lookup failed: %s", return_token)
            await message.reply_text("<b>⚠️ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ sᴇʀᴠɪᴄᴇ ɪs ᴛᴇᴍᴘᴏʀᴀʀɪʟʏ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴛʜᴇ ʟɪɴᴋ ᴀɢᴀɪɴ.</b>", parse_mode=enums.ParseMode.HTML)
            return
        if not verify_id_info or verify_id_info.get("verified"):
            grp_id = int((verify_id_info or {}).get("group_id") or 0)
            if _is_owner_tracking_record(verify_id_info or {}):
                try:
                    log_chat = LOG_VR_CHANNEL
                    await _shortener_log(
                        client, log_chat, "SHORTENER_RETURN_REJECTED", message.from_user,
                        int((verify_id_info or {}).get("step") or 1),
                        Group=grp_id, VerifyToken=return_token,
                        Reason="unknown_or_already_used",
                        ActualUser=message.from_user.id,
                    )
                except Exception:
                    logger.exception("Could not write rejected token return log")
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪɴ...</b>")
            return

        user_id = int(verify_id_info["user_id"])
        verify_id = str(verify_id_info.get("hash") or "")
        logger.info("Verification token resolved: token=%s user=%s verify_id=%s group=%s", return_token, user_id, verify_id, verify_id_info.get("group_id"))
        grp_id = int(verify_id_info.get("group_id") or 0)
        file_id = str(verify_id_info.get("delivery_key") or "")
        verification_return_mode = verify_id_info.get("mode", "file")
        if verification_return_mode not in {"file", "allfiles"}:
            verification_return_mode = "file"
        if int(message.from_user.id) != user_id:
            if _is_owner_tracking_record(verify_id_info):
                try:
                    log_chat = LOG_VR_CHANNEL
                    await _shortener_log(
                        client, log_chat, "SHORTENER_RETURN_REJECTED", message.from_user,
                        int(verify_id_info.get("step") or 1),
                        Group=grp_id, VerifyToken=return_token,
                        Reason="token_user_mismatch", ActualUser=message.from_user.id,
                        TokenUser=user_id,
                    )
                except Exception:
                    logger.exception("Could not write token mismatch log")
            await message.reply("<b>ʟɪɴᴋ ɪs ɴᴏᴛ ᴠᴀʟɪᴅ ғᴏʀ ʏᴏᴜʀ ᴜsᴇʀ.</b>")
            return
        # Settings are not required to accept the return token; avoiding this
        # extra DB dependency makes the shortener return path more reliable.
    elif start_payload.startswith(("notcopy_", "jisshu_")):
        parts = start_payload.split("_", 4)
        # Legacy verification links remain supported for backward compatibility.
        # New links use the short server-side token above.
        if len(parts) == 5:
            _, userid, verify_id, grp_id, file_id = parts
        else:
            _, userid, verify_id, file_id = start_payload.split("_", 3)
            grp_id = temp.CHAT.get(int(userid), 0)
        user_id = int(userid)
        grp_id = int(grp_id or 0)
        verification_return_mode = "allfiles" if start_payload.startswith("jisshu") else "file"
        settings = await get_settings(grp_id)
        verify_id_info = await db.get_verify_id_info(user_id, verify_id)
        if not verify_id_info or verify_id_info.get("verified"):
            # A return that never reaches the normal acceptance path is still
            # useful evidence when diagnosing a shortener that reports/cuts clicks.
            if _is_owner_tracking_record(verify_id_info or {}):
                try:
                    log_chat = LOG_VR_CHANNEL
                    await _shortener_log(
                        client, log_chat, "SHORTENER_RETURN_REJECTED", message.from_user,
                        int((verify_id_info or {}).get("step") or 1),
                        Group=grp_id, VerifyID=verify_id,
                        Reason="unknown_or_already_used",
                        ActualUser=message.from_user.id, TokenUser=user_id,
                    )
                except Exception:
                    logger.exception("Could not write rejected shortener return log")
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪɴ...</b>")
            return
        if int(message.from_user.id) != int(user_id):
            if _is_owner_tracking_record(verify_id_info):
                try:
                    log_chat = LOG_VR_CHANNEL
                    await _shortener_log(
                        client, log_chat, "SHORTENER_RETURN_REJECTED", message.from_user,
                        int(verify_id_info.get("step") or 1),
                        Group=grp_id, VerifyID=verify_id,
                        Reason="token_user_mismatch", ActualUser=message.from_user.id, TokenUser=user_id,
                    )
                except Exception:
                    logger.exception("Could not write token mismatch log")
            await message.reply("<b>ʟɪɴᴋ ɪs ɴᴏᴛ ᴠᴀʟɪᴅ ғᴏʀ ʏᴏᴜʀ ᴜsᴇʀ.</b>")
            return
    if verification_return_mode:
        ist_timezone = pytz.timezone("Asia/Kolkata")
        if await db.user_verified(user_id):
            key = "third_time_verified"
        else:
            key = (
                "second_time_verified"
                if await db.is_user_verified(user_id)
                else "last_verified"
            )
        current_time = dt.now(tz=ist_timezone)
        result = await db.update_notcopy_user(user_id, {key: current_time})
        if key == "third_time_verified":
            num = 3
        else:
            num = 2 if key == "second_time_verified" else 1
        verification_update = {
            "verified": True,
            "verified_at": current_time,
            "verification_step": num,
            "return_accepted": True,
        }
        # Step 1 is the master recycle event. Record its rolling 24-hour
        # expiry for diagnostics; Step 2/3 do not reset this timer.
        if num == 1:
            verification_update["master_24h_started_at"] = current_time
            verification_update["master_24h_expires_at"] = current_time + timedelta(hours=24)
        await db.update_verify_id_info(user_id, verify_id, verification_update)
        logger.info("Verification return accepted: user=%s verify_id=%s step=%s", user_id, verify_id, num)
        msg = verify_tr(
            await get_user_language(user_id, message.from_user),
            "done",
            mention=message.from_user.mention,
            num=num,
            duration=get_readable_time(TWO_VERIFY_GAP),
        )
        if verification_return_mode == "allfiles":
            verifiedfiles = (
                f"https://telegram.me/{temp.U_NAME}?start=allfiles_{grp_id}_{file_id}"
            )
        else:
            verifiedfiles = (
                f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}"
            )
        if _is_owner_tracking_record(verify_id_info):
            try:
                date_text = current_time.strftime("%-d %B %Y time %-I:%M%p %A")
                verification_log = "\n".join([
                    "<b>🔐 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ʀᴇᴛᴜʀɴ ᴀᴄᴄᴇᴘᴛᴇᴅ</b>",
                    "",
                    "#VerificationCompleted",
                    f"👤 ᴜꜱᴇʀ: {m.from_user.mention} [ {user_id} ]",
                    f"📆 ᴅᴀᴛᴇ: {date_text}",
                    "Get File click: PENDING",
                    f"📊 ꜱᴛᴀᴛᴜꜱ: #Verificaton_{num}_Completed",
                ])
                await client.send_message(LOG_VR_CHANNEL, verification_log)
            except Exception:
                logger.exception("Could not write verification return log")
        ui_lang = await get_user_language(user_id, message.from_user)
        btn = [
            [
                InlineKeyboardButton(tr(ui_lang, "send_all"), url=verifiedfiles),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(btn)
        await m.reply_photo(
            photo=(VERIFY_IMG),
            caption=msg,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        return

    # Normal private /start still requires a language selection. The verification
    # deep-link above is deliberately exempt so shortener returns always run.
    if message.chat.type == enums.ChatType.PRIVATE and not await has_saved_language(user_id):
        logger.info("START_HANDLER showing first-time language picker: user=%s", user_id)
        try:
            await db.update_user({"id": int(user_id), "name": message.from_user.first_name})
        except Exception:
            logger.exception("Could not initialize user record before language selection; showing picker anyway")
        await message.reply_text(
            tr("en", "language_title") + "\n\n" + tr("en", "language_body"),
            reply_markup=language_markup(),
            parse_mode=enums.ParseMode.HTML,
        )
        logger.info("START_HANDLER language picker sent successfully: user=%s", user_id)
        return
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        status = get_status()
        aks = await message.reply_text(f"<b>🔥 ʏᴇs {status},\nʜᴏᴡ ᴄᴀɴ ɪ ʜᴇʟᴘ ʏᴏᴜ??</b>")
        await asyncio.sleep(600)
        await aks.delete()
        await m.delete()
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            group_link = await message.chat.export_invite_link()
            user = message.from_user.mention if message.from_user else "Dear"
            await client.send_message(
                LOG_CHANNEL,
                script.NEW_GROUP_TXT.format(
                    temp.B_LINK,
                    message.chat.title,
                    message.chat.id,
                    message.chat.username,
                    group_link,
                    total,
                    user,
                ),
            )
            await db.add_chat(message.chat.id, message.chat.title)
        return
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(
            LOG_CHANNEL,
            script.NEW_USER_TXT.format(
                temp.B_LINK, message.from_user.id, message.from_user.mention
            ),
        )
    logger.info("START_HANDLER user record ready: user=%s", user_id)
    lang = await get_user_language(message.from_user.id, message.from_user)
    logger.info("START_HANDLER resolved language: user=%s language=%s command=%r", user_id, lang, getattr(message, "command", None))
    if len(message.command) != 2:
        lang = await get_user_language(message.from_user.id, message.from_user)
        reply_markup = _global_home_markup(lang)
        m = await message.reply_sticker(
            "CAACAgUAAx0CZz_GMwACMBdnXZA4SejgJ6a_0TrNzOfn9ImI_QACNwsAArT4iFVaZPJf8ldVVh4E"
        )
        await asyncio.sleep(1)
        await m.delete()
        logger.info("START_HANDLER sending home photo: user=%s language=%s", user_id, lang)
        home_message = await message.reply_photo(
            photo=random.choice(START_IMG),
            caption=core_tr(lang, "start", mention=message.from_user.mention, status=get_status()),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        try:
            await message.delete()
        except Exception:
            pass
        asyncio.create_task(_delete_home_later(client, message.from_user.id, home_message.id, HOME_AUTO_DELETE))
        logger.info("START_HANDLER completed successfully: user=%s home_message_id=%s", user_id, home_message.id)
        return
    if len(message.command) == 2 and message.command[1] in [
        "subscribe", "error", "okay", "help",
    ]:
        lang = await get_user_language(message.from_user.id, message.from_user)
        return await message.reply_photo(
            photo=START_IMG,
            caption=core_tr(lang, "start", mention=message.from_user.mention, status=get_status()),
            reply_markup=_global_home_markup(lang),
            parse_mode=enums.ParseMode.HTML,
        )
    if len(message.command) == 2 and message.command[1].startswith("reff_"):
        try:
            user_id = int(message.command[1].split("_")[1])
        except ValueError:
            await message.reply_text("𝖨𝗇𝗏𝖺𝗅𝗂𝖽 𝖱𝖾𝖿𝖾𝗋⁉️")
            return
        if user_id == message.from_user.id:
            await message.reply_text("𝖧𝖾𝗒 𝖣𝗎𝖽𝖾 𝖸𝗈𝗎 𝖢𝖺𝗇'𝗍 𝖱𝖾𝖿𝖾𝗋 𝖸𝗈𝗎𝗋𝗌𝖾𝗅𝖿⁉️")
            return
        if referdb.is_user_in_list(message.from_user.id):
            await message.reply_text("‼️ 𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖠𝗅𝗅𝗋𝖾𝖺𝖽𝗒 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝗈𝗋 𝖩𝗈𝗂𝗇𝖾𝖽")
            return
        if await db.is_user_exist(message.from_user.id):
            await message.reply_text("‼️ 𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖠𝗅𝗅𝗋𝖾𝖺𝖽𝗒 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝗈𝗋 𝖩𝗈𝗂𝗇𝖾𝖽")
            return
        try:
            uss = await client.get_users(user_id)
        except Exception:
            return
        referdb.add_user(message.from_user.id)
        fromuse = referdb.get_refer_points(user_id) + 10
        if fromuse == 100:
            referdb.add_refer_points(user_id, 0)
            await message.reply_text(f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {uss.mention}!")
            await client.send_message(
                user_id, text=f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {message.from_user.mention}!"
            )
            await add_premium(client, user_id, uss)
        else:
            referdb.add_refer_points(user_id, fromuse)
            await message.reply_text(f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {uss.mention}!")
            await client.send_message(
                user_id, f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 {message.from_user.mention}!"
            )
        return

    if len(message.command) == 2 and message.command[1].startswith("getfile"):
        searches = message.command[1].split("-", 1)[1]
        search = searches.replace("-", " ")
        message.text = search
        await auto_filter(client, message)
        return

    if len(message.command) == 2 and message.command[1] in ["ads"]:
        msg, _, impression = await mdb.get_advirtisment()
        user = await db.get_user(message.from_user.id)
        seen_ads = user.get("seen_ads", False)
        JISSHU_ADS_LINK = await db.jisshu_get_ads_link()
        buttons = [[InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        if msg:
            await message.reply_photo(
                photo=JISSHU_ADS_LINK if JISSHU_ADS_LINK else URL,
                caption=msg,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            if impression is not None and not seen_ads:
                await mdb.update_advirtisment_impression(int(impression) - 1)
                await db.update_value(message.from_user.id, "seen_ads", True)
        else:
            await message.reply("<b>No Ads Found</b>")
        await mdb.reset_advertisement_if_expired()
        if msg is None and seen_ads:
            await db.update_value(message.from_user.id, "seen_ads", False)
        return

    data = message.command[1]
    try:
        pre, grp_id, file_id = data.split("_", 2)
        print(f"Group Id - {grp_id}")
    except:
        pre, grp_id, file_id = "", 0, data

    # A verified Telegram deep-link is the final Get File/Send All click.
    # Track it separately from shortener completion so redirect/click problems
    # can be diagnosed from the log channel.
    if pre in ("file", "allfiles"):
        await _mark_get_file_click(client, m.from_user, int(grp_id), str(file_id))

    # filemode/allfilesmode are reached only after the user has completed the
    # File Mode shortlink. They must bypass the verification gate and then be
    # sent as normal files with the group's original caption/buttons.
    file_mode_completed = pre in ("filemode", "allfilesmode")

    # Premium users must bypass the access gates and reach the original file
    # delivery path. This uses the same DB record as /add_premium.
    user_id = m.from_user.id
    premium_active = await db.has_premium_access(user_id)

    # Premium is the first access decision. Do not require group settings,
    # force-subscription, or verification before checking the real Premium
    # record used by /add_premium.
    # grp_id=0 represents a direct PM. Use the global/default settings for PM
    # while keeping the origin explicitly as 0 for accurate tracking.
    settings = await get_settings(int(grp_id))
    if not premium_active:
        # Preserve the legacy fsub_id field while allowing the settings UI to manage
        # multiple force-subscribe channels independently for each group.
        # Group-specific channels are enforced only when explicitly enabled.
        # Legacy global AUTH_CHANNEL/AUTH_REQ_CHANNEL remains separately enforced
        # below, preserving existing deployments without leaking one group's list.
        fsub_channels = settings.get("fsub_channels", []) if settings.get("fsub_enabled", False) else []
        try:
            fsub_channels = [int(c) for c in fsub_channels if str(c).strip()]
        except (TypeError, ValueError):
            fsub_channels = []

        if AUTH_REQ_CHANNEL and int(AUTH_REQ_CHANNEL) in fsub_channels and len(fsub_channels) == 1:
            if not await is_req_subscribed(client, message):
                try:
                    invite_link = await client.create_chat_invite_link(
                        int(AUTH_REQ_CHANNEL), creates_join_request=True
                    )
                except ChatAdminRequired:
                    logger.error("Make sure Bot is admin in Forcesub channel")
                    return
                label = (settings.get("fsub_button_labels") or {}).get(str(int(AUTH_REQ_CHANNEL)), "⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️")
                btn = [[InlineKeyboardButton(str(label)[:64], url=invite_link.invite_link)]]
                if message.command[1] != "subscribe":
                    btn.append([[InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")]][0])
                fsub_caption = await _build_fsub_caption(client, settings, [AUTH_REQ_CHANNEL])
                await client.send_photo(
                    chat_id=message.from_user.id, photo=FORCESUB_IMG, caption=fsub_caption,
                    reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML,
                )
                return
        else:
            btn = []
            required_channel_ids = []
            missing_custom = False
            for channel in fsub_channels:
                if channel == int(AUTH_CHANNEL):
                    continue
                try:
                    subscribed = await is_subscribed(client, message.from_user.id, channel)
                except Exception:
                    subscribed = False
                if not subscribed:
                    missing_custom = True
                    required_channel_ids.append(channel)
                    try:
                        invite = await client.create_chat_invite_link(channel)
                        label = (settings.get("fsub_button_labels") or {}).get(str(channel), "⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️")
                        btn.append([InlineKeyboardButton(str(label)[:64], url=invite.invite_link)])
                    except Exception:
                        pass

            default_missing = not await is_req_subscribed(client, message)
            if default_missing:
                required_channel_ids.append(int(AUTH_CHANNEL))
                try:
                    invite_link_default = await client.create_chat_invite_link(int(AUTH_CHANNEL), creates_join_request=True)
                    label = (settings.get("fsub_button_labels") or {}).get(str(int(AUTH_CHANNEL)), "⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️")
                    btn.append([InlineKeyboardButton(str(label)[:64], url=invite_link_default.invite_link)])
                except Exception:
                    pass

            if message.command[1] != "subscribe" and (missing_custom or default_missing):
                btn.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
            if btn:
                fsub_caption = await _build_fsub_caption(client, settings, required_channel_ids)
                await client.send_photo(
                    chat_id=message.from_user.id, photo=FORCESUB_IMG, caption=fsub_caption,
                    reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML,
                )
                return

    if not premium_active:
        grp_id = int(grp_id)
        print(f"Group Id - {grp_id}")
        user_verified = await db.is_user_verified(user_id)
        settings = await get_settings(grp_id)
        print(f"Id Settings - {settings}")
        verification_enabled = bool(settings.get("is_verify", IS_VERIFY))

        # A PM request has grp_id=0, but its valid gap may belong to a group
        # verification; check that first to avoid incorrectly issuing Step 1 again.
        # A PM request may not carry its originating group ID. Continue the
        # user's latest same-day three-step state there, including after expiry.
        new_shortener_gap_access = False
        # New 3-step progress is user-wide for access purposes, even though
        # each cycle is stored against the group where it started. This makes
        # the configured gap apply in group requests and in PM, and prevents
        # the legacy Set Shortlink gate from interrupting an active new gap.
        if not file_mode_completed:
            try:
                from database.new_shortener import find_latest_state_for_user
                latest_state = await find_latest_state_for_user(user_id)
                if latest_state:
                    origin_group_id = int(latest_state.get("group_id", 0) or 0)
                    origin_settings = await get_settings(origin_group_id)
                    if origin_settings.get("new_shortener_enabled", False):
                        if latest_state.get("completed", False):
                            # Step 3 grants access until the IST calendar-day reset.
                            new_shortener_gap_access = True
                        else:
                            new_shortener_gap_access = _new_shortener_gap_active(
                                latest_state, origin_settings
                            )
                            if not new_shortener_gap_access:
                                next_step = int(latest_state.get("completed_step", 0)) + 1
                                if next_step in (2, 3):
                                    await _new_shortener_send_step(
                                        client, message, user_id, origin_group_id,
                                        str(file_id),
                                        "allfiles" if pre == "allfiles" else "file",
                                        next_step,
                                    )
                                    return
            except Exception:
                logger.exception("Could not continue new-shortener verification across chats")
        # Independent three-step shortener, separate from the legacy shortener.
        if settings.get("new_shortener_enabled", False) and not new_shortener_gap_access:
            from database.new_shortener import get_state
            new_state = await get_state(user_id, grp_id)
            new_shortener_gap_access = _new_shortener_gap_active(new_state, settings)
            if not new_state.get("completed", False) and not new_shortener_gap_access:
                next_step = int(new_state.get("completed_step", 0)) + 1
                if next_step in (1, 2, 3):
                    await _new_shortener_send_step(
                        client, message, user_id, grp_id, str(file_id),
                        "allfiles" if pre == "allfiles" else "file", next_step
                    )
                    return

        # The verification gate only runs when a real shortener is configured.
        # Deleting/disabling the shortener must restore the original direct-file
        # path for non-premium users; Premium already bypasses this block above.
        primary_shortener_available = bool(settings.get("shortner") and settings.get("api"))

        # File Mode VERIFY and SHORTLINK use the SAME verification state.
        # The selected file mode must never reset the user's 1/3 -> 2/3 -> 3/3
        # progress or bypass the existing verification-gap logic.

        # IMPORTANT:
        # Both VERIFY and SHORTLINK modes intentionally use this same
        # verification block. The mode changes only the presentation; the
        # user's verification state and the existing 1st/2nd/3rd gap logic
        # remain shared.

        # Secondary/third shortener states are ignored completely when the
        # master Verification switch is OFF.
        is_second_shortener = (
            await db.use_second_shortener(user_id, settings.get("verify_time", TWO_VERIFY_GAP))
            if verification_enabled and primary_shortener_available else False
        )
        is_third_shortener = (
            await db.use_third_shortener(user_id, settings.get("third_verify_time", THREE_VERIFY_GAP))
            if verification_enabled and primary_shortener_available else False
        )

        # If the selected secondary/third shortener was removed, don't send a
        # broken shortlink. Fall back to the configured primary shortener.
        if is_second_shortener and not (settings.get("shortner_two") and settings.get("api_two")):
            is_second_shortener = False
        if is_third_shortener and not (settings.get("shortner_three") and settings.get("api_three")):
            is_third_shortener = False

        if (not settings.get("new_shortener_enabled", False)) and (not new_shortener_gap_access) and (not file_mode_completed) and verification_enabled and primary_shortener_available and ((not user_verified) or is_second_shortener or is_third_shortener):
            verify_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
            step = 3 if is_third_shortener else (2 if is_second_shortener else 1)
            if is_third_shortener:
                shortener_domain = settings.get("shortner_three")
            elif is_second_shortener:
                shortener_domain = settings.get("shortner_two")
            else:
                shortener_domain = settings.get("shortner")
            shortener_api = (settings.get("api_three") if is_third_shortener
                             else settings.get("api_two") if is_second_shortener
                             else settings.get("api"))
            owner_shortener = await _is_owner_shortener(shortener_domain, shortener_api)
            delivery_mode = "allfiles" if message.command[1].startswith("allfiles") else "file"
            # Telegram limits bot deep-link start parameters to 64 bytes. The
            # previous return URL embedded user_id + verify_id + group_id +
            # file_id and could exceed that limit before Telegram invoked /start.
            # Keep that state server-side and expose only a short opaque token.
            return_token = "".join(
                random.choices(string.ascii_letters + string.digits, k=16)
            )
            await db.create_verify_id(
                user_id, verify_id, created_at=_ist_now(), group_id=int(grp_id),
                delivery_key=str(file_id), mode=delivery_mode, step=step,
                shortener_domain=shortener_domain or "unknown",
                shortener_api=shortener_api or "",
                owner_shortener=owner_shortener,
                owner_id=(int(OWNER_ID) if owner_shortener else None),
                return_token=return_token,
            )
            temp.CHAT[user_id] = grp_id
            telegram_return_link = f"https://telegram.me/{temp.U_NAME}?start=vr_{return_token}"
            tracking_base = str(URL or "").strip().rstrip("/")
            if tracking_base and not tracking_base.startswith(("http://", "https://")):
                tracking_base = "https://" + tracking_base
            target_link = (
                f"{tracking_base}/verify-click/{return_token}"
                if tracking_base
                else telegram_return_link
            )
            try:
                verify = await get_shortlink(target_link, grp_id, is_second_shortener, is_third_shortener)
            except Exception as exc:
                verify = None
                if owner_shortener:
                    await _shortener_log(
                        client, (LINK_TRACK_CHANNEL or LOG_VR_CHANNEL), "SHORTENER_API_ERROR", message.from_user, step,
                        Group=grp_id, Mode=delivery_mode, Domain=shortener_domain or "unknown",
                        VerifyID=verify_id, Error=str(exc)[:300],
                    )
            if not verify:
                if owner_shortener:
                    await _shortener_log(
                        client, (LINK_TRACK_CHANNEL or LOG_VR_CHANNEL), "SHORTENER_API_ERROR", message.from_user, step,
                        Group=grp_id, Mode=delivery_mode, Domain=shortener_domain or "unknown",
                        VerifyID=verify_id, Error="shortener returned no URL",
                    )
                # Do not create a message with a dead/None URL when the
                # shortener API is down. The user gets a clear retry instead
                # of the handler silently failing.
                await m.reply_text(
                    "<b>⚠️ ᴛʜᴇ sʜᴏʀᴛʟɪɴᴋ sᴇʀᴠɪᴄᴇ ɪs ᴛᴇᴍᴘᴏʀᴀʀɪʟʏ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>"
                )
                return
            await db.update_verify_id_info(user_id, verify_id, {"shortlink": verify, "shortlink_created_at": _ist_now()})
            if owner_shortener:
                await _shortener_log(
                    client, (LINK_TRACK_CHANNEL or LOG_VR_CHANNEL), "SHORTLINK_CREATED", message.from_user, step,
                    Group=grp_id, Mode=delivery_mode, Domain=shortener_domain or "unknown",
                    **{"Api key": shortener_api or ""}, VerifyID=verify_id, ShortURL=str(verify)[:700],
                )
            if is_third_shortener:
                howtodownload = settings.get("tutorial_3", TUTORIAL_3)
            else:
                howtodownload = settings.get("tutorial_2", TUTORIAL_2) if is_second_shortener else settings.get("tutorial", TUTORIAL)
            shortlink_mode = (
                settings.get("file_mode", False)
                and settings.get("file_mode_type", "verify") == "shortlink"
            )
            ui_lang = await get_user_language(user_id, message.from_user)
            verify_labels = {
                "en": ("SHORTLINK" if shortlink_mode else "VERIFY"),
                "hi": ("शॉर्टलिंक" if shortlink_mode else "सत्यापित"),
                "ta": ("SHORTLINK" if shortlink_mode else "சரிபார்"),
                "te": ("SHORTLINK" if shortlink_mode else "వెరిఫై"),
                "kn": ("SHORTLINK" if shortlink_mode else "ಪರಿಶೀಲಿಸಿ"),
                "ml": ("SHORTLINK" if shortlink_mode else "പരിശോധിക്കുക"),
                "bn": ("SHORTLINK" if shortlink_mode else "ভেরিফাই"),
                "mr": ("SHORTLINK" if shortlink_mode else "पडताळा"),
                "gu": ("SHORTLINK" if shortlink_mode else "ચકાસો"),
                "pa": ("SHORTLINK" if shortlink_mode else "ਵੇਰੀਫਾਈ"),
                "ur": ("SHORTLINK" if shortlink_mode else "تصدیق"),
                "as": ("SHORTLINK" if shortlink_mode else "ভেৰিফাই"),
                "ne": ("SHORTLINK" if shortlink_mode else "VERIFY"),
                "hinglish": ("SHORTLINK" if shortlink_mode else "VERIFY"),
            }
            how_labels = {
                "en": "ʟᴇᴀʀɴ ʜᴏᴡ" if shortlink_mode else "ᴠᴇʀɪғʏ ɢᴜɪᴅᴇ",
                "hi": "कैसे करें" if shortlink_mode else "वेरीफाई गाइड",
                "ta": "எப்படி" if shortlink_mode else "சரிபார்ப்பு வழி",
                "te": "ఎలా" if shortlink_mode else "వెరిఫై గైడ్",
                "kn": "ಹೇಗೆ" if shortlink_mode else "ಪರಿಶೀಲನೆ ಮಾರ್ಗದರ್ಶಿ",
                "ml": "എങ്ങനെ" if shortlink_mode else "പരിശോധന ഗൈഡ്",
                "bn": "কীভাবে" if shortlink_mode else "ভেরিফাই গাইড",
                "mr": "कसे?" if shortlink_mode else "व्हेरिफाय गाइड",
                "gu": "કેવી રીતે" if shortlink_mode else "વેરિફાય ગાઇડ",
                "pa": "ਕਿਵੇਂ?" if shortlink_mode else "ਵੇਰੀਫਾਈ ਗਾਈਡ",
                "ur": "کیسے؟" if shortlink_mode else "تصدیق گائیڈ",
                "as": "কেনেকৈ" if shortlink_mode else "ভেৰিফাই গাইড",
                "ne": "कसरी?" if shortlink_mode else "VERIFY गाइड",
                "hinglish": "KAISE?" if shortlink_mode else "VERIFY GUIDE",
            }
            premium_labels = {
                "en": "ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ",
                "hi": "Premium खरीदें",
                "ta": "Premium வாங்க",
                "te": "Premium కొనండి",
                "kn": "Premium ಖರೀದಿಸಿ",
                "ml": "Premium വാങ്ങുക",
                "bn": "Premium কিনুন",
                "mr": "Premium घ्या",
                "gu": "Premium ખરીદો",
                "pa": "Premium ਲਵੋ",
                "ur": "Premium خریدیں",
                "as": "Premium ক্ৰয় কৰক",
                "ne": "Premium किन्नुहोस्",
                "hinglish": "PREMIUM LO",
            }
            # Compact visible labels only. URLs, callbacks, shortener
            # generation, verification state and payment logic are untouched.
            verify_button_text = small_caps(
                f"🔗 {verify_labels.get(ui_lang, verify_labels['en'])} 🔗"
                if shortlink_mode
                else f"✅ {verify_labels.get(ui_lang, verify_labels['en'])} ✅"
            )
            how_button_text = small_caps(how_labels.get(ui_lang, how_labels["en"]))
            buttons = [
                [InlineKeyboardButton(text=verify_button_text, url=verify), InlineKeyboardButton(text=how_button_text, url=howtodownload)],
                [InlineKeyboardButton(text=small_caps(premium_labels.get(ui_lang, premium_labels["en"])), callback_data="getpremium")],
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            if shortlink_mode:
                verify_key = "short3" if await db.user_verified(user_id) else ("short2" if is_second_shortener else "short1")
            else:
                verify_key = "verify3" if await db.user_verified(user_id) else ("verify2" if is_second_shortener else "verify1")
            msg = verify_tr(
                ui_lang,
                verify_key,
                mention=message.from_user.mention,
                status=get_status(),
                greeting=_file_mode_greeting(),
                name=formate_file_name((await get_file_details(file_id) or [None])[0].file_name) if (await get_file_details(file_id) or [None])[0] else "File",
                size=get_size((await get_file_details(file_id) or [None])[0].file_size) if (await get_file_details(file_id) or [None])[0] else "N/A",
            )
            if shortlink_mode:
                # Shortlink mode shows the same dynamic movie/file information
                # as the File Mode caption, while keeping the Shortlink 1/3 →
                # 2/3 → 3/3 progress section. VERIFY mode is unchanged.
                shortlink_file = (await get_file_details(file_id) or [None])[0]
                if shortlink_file:
                    d = await m.reply_text(
                        text=msg.format(
                            message.from_user.mention,
                            _file_mode_greeting(),
                            formate_file_name(shortlink_file.file_name),
                            get_size(shortlink_file.file_size),
                        ),
                        protect_content=True, reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML,
                    )
                else:
                    d = await m.reply_text(
                        text=msg.format(message.from_user.mention, _file_mode_greeting(), "File", "N/A"),
                        protect_content=True, reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML,
                    )
            else:
                d = await m.reply_text(
                    text=msg.format(message.from_user.mention, get_status()),
                    protect_content=True, reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
            await asyncio.sleep(300)
            await d.delete()
            await m.delete()
            return

    if pre == "filemode":
        data = f"file_{grp_id}_{file_id}"
    elif pre == "allfilesmode":
        data = f"allfiles_{grp_id}_{file_id}"

    if data and data.startswith("allfiles"):
        _, grp_id, key = data.split("_", 2)
        files = temp.FILES_ID.get(key)
        if not files:
            await message.reply_text("<b>⚠️ ᴀʟʟ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>")
            return
        files_to_delete = []
        delete_delay = None
        auto_delete_enabled = False
        for file in files:
            # grp_id is encoded in allfiles_<grp_id>_<key>; do not depend on
            # temp.CHAT for direct/Premium starts.
            settings = await get_settings(int(grp_id))
            auto_delete_enabled = bool(settings.get("auto_delete", False))
            try:
                delete_delay = max(1, int(settings.get("delete_time", FILE_AUTO_DEL_TIMER)))
            except (TypeError, ValueError):
                delete_delay = max(1, int(FILE_AUTO_DEL_TIMER))
            # File Mode is only the access gate. Once the user reaches this
            # delivery path, always restore the group's original caption and
            # normal direct-file button.
            CAPTION = settings["caption"]
            f_caption = CAPTION.format(
                file_name=formate_file_name(file.file_name),
                file_size=get_size(file.file_size),
                file_caption=file.caption,
            )
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
                "✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f"stream#{file.file_id}"
            )]])
            toDel = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file.file_id,
                caption=f_caption,
                protect_content=bool(settings.get("file_secure", PROTECT_CONTENT)),
                reply_markup=reply_markup,
            )
            files_to_delete.append(toDel)

        delCap = "<i>ᴀʟʟ {} ꜰɪʟᴇꜱ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀꜰᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            len(files_to_delete),
            (
                f"{delete_delay / 60} ᴍɪɴᴜᴛᴇs"
                if delete_delay >= 60
                else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
            ),
        )
        afterDelCap = "<i>ᴀʟʟ {} ꜰɪʟᴇꜱ ᴀʀᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀꜰᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            len(files_to_delete),
            (
                f"{delete_delay / 60} ᴍɪɴᴜᴛᴇs"
                if delete_delay >= 60
                else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
            ),
        )
        replyed = await message.reply(delCap)
        await asyncio.sleep(delete_delay)
        for file in files_to_delete:
            try:
                await file.delete()
            except:
                pass
        return await replyed.edit(
            afterDelCap,
        )
    if not data:
        return

    files_ = await get_file_details(file_id)
    if not files_:
        pre, file_id = (
            (base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")
        ).split("_", 1)
        return await message.reply("<b>⚠️ ᴀʟʟ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>")
    files = files_[0]
    settings = await get_settings(grp_id)
    auto_delete_enabled = bool(settings.get("auto_delete", False))
    try:
        delete_delay = max(1, int(settings.get("delete_time", FILE_AUTO_DEL_TIMER)))
    except (TypeError, ValueError):
        delete_delay = max(1, int(FILE_AUTO_DEL_TIMER))
    # This is the final delivery stage, so File Mode must never be rendered
    # again here. File Mode is only used before access is granted.
    CAPTION = settings["caption"]
    f_caption = CAPTION.format(
        file_name=formate_file_name(files.file_name),
        file_size=get_size(files.file_size),
        file_caption=files.caption,
    )
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
        "✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f"stream#{file_id}"
    )]])
    toDel = await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=bool(settings.get("file_secure", PROTECT_CONTENT)),
        reply_markup=reply_markup,
    )
    delCap = "<i>ʏᴏᴜʀ ꜰɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀғᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
        f"{delete_delay / 60} ᴍɪɴᴜᴛᴇs"
        if delete_delay >= 60
        else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
    )
    afterDelCap = (
        "<i>ʏᴏᴜʀ ꜰɪʟᴇ ɪs ᴅᴇʟᴇᴛᴇᴅ ᴀғᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            f"{delete_delay / 60} ᴍɪɴᴜᴛᴇs"
            if delete_delay >= 60
            else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
        )
    )
    if not auto_delete_enabled:
        return
    replyed = await message.reply(delCap, reply_to_message_id=toDel.id)
    async def _delete_file_after():
        await asyncio.sleep(delete_delay)
        try:
            await toDel.delete()
        except Exception:
            pass
        try:
            await replyed.edit(afterDelCap)
        except Exception:
            pass
    asyncio.create_task(_delete_file_after())
    return


@Client.on_message(filters.command("delete"))
async def delete(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑")
        return
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("ᴘʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        await message.reply(
            "Reply to file with /delete which you want to delete", quote=True
        )
        return
    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit("<b>ᴛʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ꜰɪʟᴇ ꜰᴏʀᴍᴀᴛ</b>")
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)
    result = await Media.collection.delete_one(
        {
            "_id": file_id,
        }
    )
    if result.deleted_count:
        await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many(
            {
                "file_name": file_name,
                "file_size": media.file_size,
                "mime_type": media.mime_type,
            }
        )
        if result.deleted_count:
            await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
        else:
            result = await Media.collection.delete_many(
                {
                    "file_name": media.file_name,
                    "file_size": media.file_size,
                    "mime_type": media.mime_type,
                }
            )
            if result.deleted_count:
                await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
            else:
                await msg.edit("<b>ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ</b>")


@Client.on_message(filters.command("deleteall"))
async def delete_all_index(bot, message):
    files = await Media.count_documents()
    if int(files) == 0:
        return await message.reply_text("Not have files to delete")
    btn = [
        [InlineKeyboardButton(text="ʏᴇs", callback_data="all_files_delete")],
        [InlineKeyboardButton(text="ᴄᴀɴᴄᴇʟ", callback_data="close_data")],
    ]
    if message.from_user.id not in ADMINS:
        await message.reply("ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑")
        return
    await message.reply_text(
        "<b>ᴛʜɪs ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇs.\nᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ??</b>",
        reply_markup=reply_markup,
    )


@Client.on_message(filters.command("settings"))
async def settings(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply("<b>💔 ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ...</b>")

    if message.chat.type == enums.ChatType.PRIVATE:
        from plugins.advanced_settings import show_group_list
        return await show_group_list(client, message)

    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<code>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ ᴏʀ ᴘʀɪᴠᴀᴛᴇ.</code>")

    grp_id = message.chat.id
    if not await is_check_admin(client, grp_id, user_id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ</b>")

    try:
        pm_url = f"https://t.me/{temp.U_NAME}?start=settings_{grp_id}"
    except Exception:
        pm_url = f"https://t.me/{client.me.username}?start=settings_{grp_id}"
    buttons = [[InlineKeyboardButton("⚠️ GO TO PRIVATE ⚠️", url=pm_url)]]
    return await message.reply_text(
        "⚠️ ᴘʟᴇᴀsᴇ ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ ɪɴ ᴘʀɪᴠᴀᴛᴇ!!",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@Client.on_message(filters.command("set_template"))
async def save_template(client, message):
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        template = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, "template", template)
    await message.reply_text(
        f"Successfully changed template for {title} to\n\n{template}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("send"))
async def send_msg(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("<b>ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ...</b>")
        return
    if message.reply_to_message:
        target_ids = message.text.split(" ")[1:]
        if not target_ids:
            await message.reply_text(
                "<b>ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴏɴᴇ ᴏʀ ᴍᴏʀᴇ ᴜꜱᴇʀ ɪᴅꜱ ᴀꜱ ᴀ ꜱᴘᴀᴄᴇ...</b>"
            )
            return
        out = "\n\n"
        success_count = 0
        try:
            users = await db.get_all_users()
            for target_id in target_ids:
                try:
                    user = await bot.get_users(target_id)
                    out += f"{user.id}\n"
                    await message.reply_to_message.copy(int(user.id))
                    success_count += 1
                except Exception as e:
                    out += f"‼️ ᴇʀʀᴏʀ ɪɴ ᴛʜɪꜱ ɪᴅ - <code>{target_id}</code> <code>{str(e)}</code>\n"
            await message.reply_text(
                f"<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴛ ɪɴ `{success_count}` ɪᴅ\n<code>{out}</code></b>"
            )
        except Exception as e:
            await message.reply_text(f"<b>‼️ ᴇʀʀᴏʀ - <code>{e}</code></b>")
    else:
        await message.reply_text(
            "<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴀꜱ ᴀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇꜱꜱᴀɢᴇ, ꜰᴏʀ ᴇɢ - <code>/send userid1 userid2</code></b>"
        )


@Client.on_message(filters.regex("#request"))
async def send_request(bot, message):
    try:
        request = message.text.split(" ", 1)[1]
    except:
        await message.reply_text("<b>‼️ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ɪɴᴄᴏᴍᴘʟᴇᴛᴇ</b>")
        return
    buttons = [
        [InlineKeyboardButton("👀 ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ 👀", url=f"{message.link}")],
        [
            InlineKeyboardButton(
                "⚙ sʜᴏᴡ ᴏᴘᴛɪᴏɴ ⚙",
                callback_data=f"show_options#{message.from_user.id}#{message.id}",
            )
        ],
    ]
    req_settings = await get_settings(message.chat.id) if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP] else {}
    request_target = req_settings.get("request_channel", REQUEST_CHANNEL)
    sent_request = await bot.send_message(
        request_target,
        script.REQUEST_TXT.format(
            message.from_user.mention, message.from_user.id, request
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    btn = [
        [InlineKeyboardButton("✨ ᴠɪᴇᴡ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ✨", url=f"{sent_request.link}")]
    ]
    await message.reply_text(
        "<b>✅ sᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ʜᴀꜱ ʙᴇᴇɴ ᴀᴅᴅᴇᴅ, ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ ꜱᴏᴍᴇᴛɪᴍᴇ...</b>",
        reply_markup=reply_markup,
    )


@Client.on_message(filters.command("search"))
async def search_files(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("Only the bot owner can use this command... 😑")
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, this command won't work in groups. It only works in my PM!</b>"
        )
    try:
        keyword = message.text.split(" ", 1)[1]
    except IndexError:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, give me a keyword along with the command to delete files.</b>"
        )
    files, total = await get_bad_files(keyword)
    if int(total) == 0:
        await message.reply_text(
            "<i>I could not find any files with this keyword 😐</i>"
        )
        return
    file_names = "\n\n".join(
        f"{index + 1}. {item['file_name']}" for index, item in enumerate(files)
    )
    file_data = f"🚫 Your search - '{keyword}':\n\n{file_names}"
    with open("file_names.txt", "w", encoding="utf-8") as file:
        file.write(file_data)
    await message.reply_document(
        document="file_names.txt",
        caption=f"<b>♻️ ʙʏ ʏᴏᴜʀ ꜱᴇᴀʀᴄʜ, ɪ ꜰᴏᴜɴᴅ - <code>{total}</code> ꜰɪʟᴇs</b>",
        parse_mode=enums.ParseMode.HTML,
    )
    os.remove("file_names.txt")


@Client.on_message(filters.command("deletefiles"))
async def deletemultiplefiles(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑")
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(
            f"<b>ʜᴇʏ {message.from_user.mention}, ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏɴ'ᴛ ᴡᴏʀᴋ ɪɴ ɢʀᴏᴜᴘs. ɪᴛ ᴏɴʟʏ ᴡᴏʀᴋs ᴏɴ ᴍʏ ᴘᴍ !!</b>"
        )
    else:
        pass
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(
            f"<b>ʜᴇʏ {message.from_user.mention}, ɢɪᴠᴇ ᴍᴇ ᴀ ᴋᴇʏᴡᴏʀᴅ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ ꜰɪʟᴇs.</b>"
        )
    files, total = await get_bad_files(keyword)
    if int(total) == 0:
        await message.reply_text(
            "<i>ɪ ᴄᴏᴜʟᴅ ɴᴏᴛ ꜰɪɴᴅ ᴀɴʏ ꜰɪʟᴇs ᴡɪᴛʜ ᴛʜɪs ᴋᴇʏᴡᴏʀᴅ 😐</i>"
        )
        return
    btn = [
        [
            InlineKeyboardButton(
                "ʏᴇs, ᴄᴏɴᴛɪɴᴜᴇ ✅", callback_data=f"killfilesak#{keyword}"
            )
        ],
        [InlineKeyboardButton("ɴᴏ, ᴀʙᴏʀᴛ ᴏᴘᴇʀᴀᴛɪᴏɴ 😢", callback_data="close_data")],
    ]
    await message.reply_text(
        text=f"<b>ᴛᴏᴛᴀʟ ꜰɪʟᴇs ꜰᴏᴜɴᴅ - <code>{total}</code>\n\nᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ?\n\nɴᴏᴛᴇ:- ᴛʜɪs ᴄᴏᴜʟᴅ ʙᴇ ᴀ ᴅᴇsᴛʀᴜᴄᴛɪᴠᴇ ᴀᴄᴛɪᴏɴ!!</b>",
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command("del_file"))
async def delete_files(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("Only the bot owner can use this command... 😑")
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, this command won't work in groups. It only works on my PM!</b>"
        )
    try:
        keywords = message.text.split(" ", 1)[1].split(",")
    except IndexError:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, give me keywords separated by commas along with the command to delete files.</b>"
        )
    deleted_files_count = 0
    not_found_files = []
    for keyword in keywords:
        result = await Media.collection.delete_many({"file_name": keyword.strip()})
        if result.deleted_count:
            deleted_files_count += 1
        else:
            not_found_files.append(keyword.strip())
    if deleted_files_count > 0:
        await message.reply_text(
            f"<b>{deleted_files_count} file successfully deleted from the database 💥</b>"
        )
    if not_found_files:
        await message.reply_text(
            f'<b>Files not found in the database - <code>{", ".join(not_found_files)}</code></b>'
        )


@Client.on_message(filters.command("set_caption"))
async def save_caption(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        caption = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, "caption", caption)
    await message.reply_text(
        f"Successfully changed caption for {title} to\n\n{caption}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("set_tutorial"))
async def save_tutorial(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        tutorial = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(
            "<b>Command Incomplete!!\n\nuse like this -</b>\n\n<code>/set_caption https://telegram.me/+JWsoDEJEB9EyNDU1</code>"
        )
    await save_group_settings(grp_id, "tutorial", tutorial)
    await message.reply_text(
        f"<b>Successfully Changed 1st Verification Tutorial For {title} To</b>\n\n{tutorial}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("set_tutorial_2"))
async def set_tutorial_2(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    invite_link = await client.export_chat_invite_link(grp_id)
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text(
            f"<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...\n\nGroup Name: {title}\nGroup ID: {grp_id}\nGroup Invite Link: {invite_link}</b>"
        )
    try:
        tutorial = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(
            "<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ !!\n\nᴜꜱᴇ ʟɪᴋᴇ ᴛʜɪꜱ -</b>\n\n<code>/set_tutorial_2 https://telegram.dog/DwldMS/2</code>"
        )
    await save_group_settings(grp_id, "tutorial_2", tutorial)
    await message.reply_text(
        f"<b>Successfully Changed 2nd Verification Tutorial For {title} To</b>\n\n{tutorial}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("set_tutorial_3"))
async def set_tutorial_3(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    invite_link = await client.export_chat_invite_link(grp_id)
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text(
            f"<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...\n\nGroup Name: {title}\nGroup ID: {grp_id}\nGroup Invite Link: {invite_link}</b>"
        )
    try:
        tutorial = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(
            "<b>Command Incomplete!!\n\nuse like this -</b>\n\n<code>/set_tutorial https://telegram.dog/infinity_botzz</code>"
        )
    await save_group_settings(grp_id, "tutorial_3", tutorial)
    await message.reply_text(
        f"<b>Successfully Changed 3rd Verification Tutorial For {title} To</b>\n\n{tutorial}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("set_verify"))
async def set_shortner(c, m):
    grp_id = m.chat.id
    chat_type = m.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await m.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    if not await is_check_admin(c, grp_id, m.from_user.id):
        return await m.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(m.text.split()) == 1:
        await m.reply(
            "<b>Use this command like this - \n\n`/set_shortner tnshort.net 9bccb0b14ed6841652fa22d3481907788c1b8838`</b>"
        )
        return
    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    try:
        URL = m.command[1]
        API = m.command[2]
        resp = requests.get(
            f"https://{URL}/api?api={API}&url=https://t.me/+BJfqwUjbkQFmNTU1"
        ).json()
        if resp["status"] == "success":
            SHORT_LINK = resp["shortenedUrl"]
        await save_group_settings(grp_id, "shortner", URL)
        await save_group_settings(grp_id, "api", API)
        await m.reply_text(
            f"<b><u>✓ sᴜᴄᴄᴇssꜰᴜʟʟʏ ʏᴏᴜʀ sʜᴏʀᴛɴᴇʀ ɪs ᴀᴅᴅᴇᴅ</u>\n\nᴅᴇᴍᴏ - {SHORT_LINK}\n\nsɪᴛᴇ - `{URL}`\n\nᴀᴘɪ - `{API}`</b>",
            quote=True,
        )
        user_id = m.from_user.id
        user_info = (
            f"@{m.from_user.username}"
            if m.from_user.username
            else f"{m.from_user.mention}"
        )
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        log_message = f"#New_Shortner_Set_For_1st_Verify\n\nName - {user_info}\nId - `{user_id}`\n\nDomain name - {URL}\nApi - `<masked>`\nGroup link - {grp_link}"
        await c.send_message(
            LOG_API_CHANNEL, log_message, disable_web_page_preview=True
        )
    except Exception as e:
        await save_group_settings(grp_id, "shortner", SHORTENER_WEBSITE)
        await save_group_settings(grp_id, "api", SHORTENER_API)
        await m.reply_text(
            f"<b><u>💢 ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ!!</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ʙᴏᴛ ᴏᴡɴᴇʀ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\nʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://telegram.me/+JWsoDEJEB9EyNDU1>sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\nʟɪᴋᴇ -\n\n`/set_shortner mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>",
            quote=True,
        )


@Client.on_message(filters.command("set_verify_2"))
async def set_shortner_2(c, m):
    grp_id = m.chat.id
    chat_type = m.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await m.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    if not await is_check_admin(c, grp_id, m.from_user.id):
        return await m.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(m.text.split()) == 1:
        await m.reply(
            "<b>Use this command like this - \n\n`/set_shortner_2 tnshort.net 9bccb0b14ed6841652fa22d3481907788c1b8838`</b>"
        )
        return
    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    try:
        URL = m.command[1]
        API = m.command[2]
        resp = requests.get(
            f"https://{URL}/api?api={API}&url=https://t.me/+BJfqwUjbkQFmNTU1"
        ).json()
        if resp["status"] == "success":
            SHORT_LINK = resp["shortenedUrl"]
        await save_group_settings(grp_id, "shortner_two", URL)
        await save_group_settings(grp_id, "api_two", API)
        await m.reply_text(
            f"<b><u>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ʏᴏᴜʀ sʜᴏʀᴛɴᴇʀ ɪs ᴀᴅᴅᴇᴅ</u>\n\nᴅᴇᴍᴏ - {SHORT_LINK}\n\nsɪᴛᴇ - `{URL}`\n\nᴀᴘɪ - `{API}`</b>",
            quote=True,
        )
        user_id = m.from_user.id
        user_info = (
            f"@{m.from_user.username}"
            if m.from_user.username
            else f"{m.from_user.mention}"
        )
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        log_message = f"#New_Shortner_Set_For_2nd_Verify\n\nName - {user_info}\nId - `{user_id}`\n\nDomain name - {URL}\nApi - `<masked>`\nGroup link - {grp_link}"
        await c.send_message(
            LOG_API_CHANNEL, log_message, disable_web_page_preview=True
        )
    except Exception as e:
        await save_group_settings(grp_id, "shortner_two", SHORTENER_WEBSITE2)
        await save_group_settings(grp_id, "api_two", SHORTENER_API2)
        await m.reply_text(
            f"<b><u>💢 ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ!!</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ʙᴏᴛ ᴏᴡɴᴇʀ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\nʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://telegram.me/+JWsoDEJEB9EyNDU1>sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\nʟɪᴋᴇ -\n\n`/set_shortner_2 mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>",
            quote=True,
        )


@Client.on_message(filters.command("set_verify_3"))
async def set_shortner_3(c, m):
    chat_type = m.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await m.reply_text(
            "<b>Use this command in Your group ! Not in Private</b>"
        )
    if len(m.text.split()) == 1:
        return await m.reply(
            "<b>Use this command like this - \n\n`/set_shortner_3 tnshort.net 9bccb0b14ed6841652fa22d3481907788c1b8838`</b>"
        )
    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await sts.delete()
    userid = m.from_user.id if m.from_user else None
    if not userid:
        return await m.reply("<b>⚠️ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ᴏꜰ ᴛʜɪs ɢʀᴏᴜᴘ</b>")
    grp_id = m.chat.id
    # check if user admin or not
    if not await is_check_admin(c, grp_id, userid):
        return await m.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(m.command) == 1:
        await m.reply_text(
            "<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴛᴏ ᴀᴅᴅ sʜᴏʀᴛɴᴇʀ & ᴀᴘɪ\n\nᴇx - `/set_shortner_3 mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`</b>",
            quote=True,
        )
        return
    try:
        URL = m.command[1]
        API = m.command[2]
        resp = requests.get(
            f"https://{URL}/api?api={API}&url=https://t.me/+BJfqwUjbkQFmNTU1"
        ).json()
        if resp["status"] == "success":
            SHORT_LINK = resp["shortenedUrl"]
        await save_group_settings(grp_id, "shortner_three", URL)
        await save_group_settings(grp_id, "api_three", API)
        await m.reply_text(
            f"<b><u>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ʏᴏᴜʀ sʜᴏʀᴛɴᴇʀ ɪs ᴀᴅᴅᴇᴅ</u>\n\nᴅᴇᴍᴏ - {SHORT_LINK}\n\nsɪᴛᴇ - `{URL}`\n\nᴀᴘɪ - `{API}`</b>",
            quote=True,
        )
        user_id = m.from_user.id
        if m.from_user.username:
            user_info = f"@{m.from_user.username}"
        else:
            user_info = f"{m.from_user.mention}"
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        log_message = f"#New_Shortner_Set_For_3rd_Verify\n\nName - {user_info}\nId - `{user_id}`\n\nDomain name - {URL}\nApi - `<masked>`\nGroup link - {grp_link}"
        await c.send_message(
            LOG_API_CHANNEL, log_message, disable_web_page_preview=True
        )
    except Exception as e:
        await save_group_settings(grp_id, "shortner_three", SHORTENER_WEBSITE3)
        await save_group_settings(grp_id, "api_three", SHORTENER_API3)
        await m.reply_text(
            f"<b><u>💢 ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ!!</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ʙᴏᴛ ᴏᴡɴᴇʀ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\nʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://telegram.me/+JWsoDEJEB9EyNDU1>sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\nʟɪᴋᴇ -\n\n`/set_shortner_3 mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>",
            quote=True,
        )


@Client.on_message(filters.command("set_log"))
async def set_log(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(message.text.split()) == 1:
        await message.reply(
            "<b><u>ɪɴᴠᴀɪʟᴅ ꜰᴏʀᴍᴀᴛ!!</u>\n\nᴜsᴇ ʟɪᴋᴇ ᴛʜɪs -\n`/log -100xxxxxxxx`</b>"
        )
        return
    sts = await message.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        log = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text(
            "<b><u>ɪɴᴠᴀɪʟᴅ ꜰᴏʀᴍᴀᴛ!!</u>\n\nᴜsᴇ ʟɪᴋᴇ ᴛʜɪs -\n`/log -100xxxxxxxx`</b>"
        )
    except ValueError:
        return await message.reply_text("<b>ᴍᴀᴋᴇ sᴜʀᴇ ɪᴅ ɪs ɪɴᴛᴇɢᴇʀ...</b>")
    try:
        t = await client.send_message(chat_id=log, text="<b>ʜᴇʏ ᴡʜᴀᴛ's ᴜᴘ!!</b>")
        await asyncio.sleep(3)
        await t.delete()
    except Exception as e:
        return await message.reply_text(
            f"<b><u>😐 ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜɪs ʙᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ...</u>\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>"
        )
    await save_group_settings(grp_id, "log", log)
    await message.reply_text(
        f"<b>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\nɪᴅ `{log}`</b>",
        disable_web_page_preview=True,
    )
    user_id = message.from_user.id
    user_info = (
        f"@{message.from_user.username}" if message.from_user.username else f"{message.from_user.mention}"
    )
    link = (await client.get_chat(message.chat.id)).invite_link
    grp_link = f"[{message.chat.title}]({link})"
    log_message = f"#New_Log_Channel_Set\n\nName - {user_info}\nId - `{user_id}`\n\nLog channel id - `{log}`\nGroup link - {grp_link}"
    await client.send_message(
        LOG_API_CHANNEL, log_message, disable_web_page_preview=True
    )


@Client.on_message(filters.command("details"))
async def all_settings(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    settings = await get_settings(grp_id)
    text = f"""<b><u>⚙️ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ -</u> {title}

<u>✅️ 1sᴛ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings["shortner"]}`
ᴀᴘɪ - `{settings["api"]}`

<u>✅️ 2ɴᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings["shortner_two"]}`
ᴀᴘɪ - `{settings["api_two"]}`

<u>✅️ 3ʀᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings["shortner_three"]}`
ᴀᴘɪ - `{settings["api_three"]}`

🧭 𝟸ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - `{settings['verify_time']}`

🧭 𝟹ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - `{settings['third_verify_time']}`

📝 ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ - `{settings['log']}`

🌀 ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ ɪᴅ - `{settings['fsub_id']}`

📍1 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ - {settings['tutorial']}

📍2 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ - {settings['tutorial_2']}

📍3 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ - {settings['tutorial_3']}

🎯 ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ - `{settings['template']}`

📂 ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ - `{settings['caption']}`</b>"""

    btn = [
        [InlineKeyboardButton("ʀᴇꜱᴇᴛ ᴅᴀᴛᴀ", callback_data="reset_grp_data")],
        [InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_data")],
    ]
    reply_markup = InlineKeyboardMarkup(btn)
    dlt = await message.reply_text(
        text, reply_markup=reply_markup, disable_web_page_preview=True
    )
    await asyncio.sleep(300)
    await dlt.delete()


@Client.on_message(filters.command("set_time_2"))
async def set_time_2(client, message):
    userid = message.from_user.id if message.from_user else None
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    if not userid:
        return await message.reply("<b>ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        time = int(message.text.split(" ", 1)[1])
    except:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, "verify_time", time)
    await message.reply_text(
        f"Successfully set 1st verify time for {title}\n\nTime is - <code>{time}</code>"
    )


@Client.on_message(filters.command("set_time_3"))
async def set_time_3(client, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("<b>ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ...</b>")
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        time = int(message.text.split(" ", 1)[1])
    except:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, "third_verify_time", time)
    await message.reply_text(
        f"Successfully set 1st verify time for {title}\n\nTime is - <code>{time}</code>"
    )


@Client.on_callback_query(filters.regex("mostsearch"))
@_debug_handler
async def most(client, callback_query):
    def is_alphanumeric(string):
        return bool(re.match("^[a-zA-Z0-9 ]*$", string))

    limit = 20
    top_messages = await mdb.get_top_messages(limit)
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        msg_lower = msg.lower()
        if msg_lower not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg_lower)

            if len(msg) > 35:
                truncated_messages.append(msg[:32] + "...")
            else:
                truncated_messages.append(msg)

    keyboard = [
        truncated_messages[i : i + 2] for i in range(0, len(truncated_messages), 2)
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        one_time_keyboard=True,
        resize_keyboard=True,
        placeholder="Most searches of the day",
    )

    await callback_query.message.reply_text(
        "<b>Hᴇʀᴇ ɪꜱ ᴛʜᴇ ᴍᴏꜱᴛ ꜱᴇᴀʀᴄʜᴇꜱ ʟɪꜱᴛ 👇</b>", reply_markup=reply_markup
    )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^trending$"))
@_debug_handler
async def top(client, query):
    movie_series_names = await movie_series_db.get_movie_series_names(1)
    if not movie_series_names:
        await query.message.reply(
            "Tʜᴇʀᴇ ᴀʀᴇ ɴᴏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs ɴᴀᴍᴇs ᴀᴠᴀɪʟᴀʙʟᴇ ғᴏʀ ᴛʜᴇ ᴛᴏᴘ sᴇᴀʀᴄʜᴇs."
        )
        return
    buttons = [
        movie_series_names[i : i + 2] for i in range(0, len(movie_series_names), 2)
    ]
    spika = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await query.message.reply(
        "<b>Here Is The Top Trending List 👇</b>", reply_markup=spika
    )


@Client.on_message(filters.command("refer"))
async def refer(bot, message):
    btn = [
        [
            InlineKeyboardButton(
                "• ɪɴᴠɪᴛᴇ ʟɪɴᴋ •",
                url=f"https://telegram.me/share/url?url=https://telegram.dog/{bot.me.username}?start=reff_{message.from_user.id}&text=Hello%21%20Experience%20a%20bot%20that%20offers%20a%20vast%20library%20of%20unlimited%20movies%20and%20series.%20%F0%9F%98%83",
            ),
            InlineKeyboardButton(
                f"⏳ {referdb.get_refer_points(message.from_user.id)}",
                callback_data="ref_point",
            ),
            InlineKeyboardButton("• ᴄʟᴏsᴇ •", callback_data="close_data"),
        ]
    ]
    m = await message.reply_sticker(
        "CAACAgQAAxkBAAEkt_Rl_7138tgHJdEsqSNzO5mPWioZDgACGRAAAudLcFGAbsHU3KNJUx4E"
    )
    await m.delete()
    reply_markup = InlineKeyboardMarkup(btn)
    await message.reply_photo(
        photo=random.choice(REFER_PICS),
        caption=f"👋Hay {message.from_user.mention},\n\nHᴇʀᴇ ɪꜱ ʏᴏᴜʀ ʀᴇғғᴇʀᴀʟ ʟɪɴᴋ:\nhttps://telegram.dog/{bot.me.username}?start=reff_{message.from_user.id}\n\nShare this link with your friends, Each time they join,  you will get 10 refferal points and after 100 points you will get 1 month premium subscription.",
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("pm_search_on"))
async def set_pm_search_on(client, message):
    user_id = message.from_user.id
    bot_id = client.me.id
    if user_id not in ADMINS:
        await message.delete()
        return

    await db.update_pm_search_status(bot_id, enable=True)
    await message.reply_text(
        "<b><i>✅️ ᴘᴍ ꜱᴇᴀʀᴄʜ ᴇɴᴀʙʟᴇᴅ, ꜰʀᴏᴍ ɴᴏᴡ ᴜꜱᴇʀꜱ ᴀʙʟᴇ ᴛᴏ ꜱᴇᴀʀᴄʜ ᴍᴏᴠɪᴇ ɪɴ ʙᴏᴛ ᴘᴍ.</i></b>"
    )


@Client.on_message(filters.private & filters.command("pm_search_off"))
async def set_pm_search_off(client, message):
    user_id = message.from_user.id
    bot_id = client.me.id
    if user_id not in ADMINS:
        await message.delete()
        return

    await db.update_pm_search_status(bot_id, enable=False)
    await message.reply_text(
        "<b><i>❌️ ᴘᴍ ꜱᴇᴀʀᴄʜ ᴅɪꜱᴀʙʟᴇᴅ, ꜰʀᴏᴍ ɴᴏᴡ ɴᴏ ᴏɴᴇ ᴄᴀɴ ᴀʙʟᴇ ᴛᴏ ꜱᴇᴀʀᴄʜ ᴍᴏᴠɪᴇ ɪɴ ʙᴏᴛ ᴘᴍ.</i></b>"
    )


@Client.on_message(filters.private & filters.command("movie_update_on"))
async def set_send_movie_on(client, message):
    user_id = message.from_user.id
    bot_id = client.me.id
    if user_id not in ADMINS:
        await message.delete()
        return
    await db.update_send_movie_update_status(bot_id, enable=True)
    await message.reply_text("<b><i>✅️ ꜱᴇɴᴅ ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ᴇɴᴀʙʟᴇᴅ.</i></b>")


@Client.on_message(filters.private & filters.command("movie_update_off"))
async def set_send_movie_update_off(client, message):
    user_id = message.from_user.id
    bot_id = client.me.id
    if user_id not in ADMINS:
        await message.delete()
        return
    await db.update_send_movie_update_status(bot_id, enable=False)
    await message.reply_text("<b><i>❌️ ꜱᴇɴᴅ ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ᴅɪꜱᴀʙʟᴇᴅ.</i></b>")


@Client.on_message(filters.command("verifyoff") & filters.user(ADMINS))
async def verifyoff(bot, message):
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ᴏɴʟʏ ɪɴ ɢʀᴏᴜᴘꜱ !")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    await save_group_settings(grpid, "is_verify", False)
    return await message.reply_text("✓ ᴠᴇʀɪꜰʏ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅɪꜱᴀʙʟᴇᴅ.")


@Client.on_message(filters.command("verifyon") & filters.user(ADMINS))
async def verifyon(bot, message):
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ᴏɴʟʏ ɪɴ ɢʀᴏᴜᴘꜱ !")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    await save_group_settings(grpid, "is_verify", True)
    return await message.reply_text("✗ ᴠᴇʀɪꜰʏ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴇɴᴀʙʟᴇᴅ.")


@Client.on_message(filters.command("set_fsub"))
async def set_fsub(client, message):
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        channel_id = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text(
            "<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nꜱᴇɴᴅ ᴍᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴡɪᴛʜ ᴄᴏᴍᴍᴀɴᴅ, ʟɪᴋᴇ <code>/set_fsub -100******</code></b>"
        )
    except ValueError:
        return await message.reply_text("<b>ᴍᴀᴋᴇ ꜱᴜʀᴇ ᴛʜᴇ ɪᴅ ɪꜱ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>")
    try:
        chat = await client.get_chat(channel_id)
    except Exception as e:
        return await message.reply_text(
            f"<b><code>{channel_id}</code> ɪꜱ ɪɴᴠᴀʟɪᴅ. ᴍᴀᴋᴇ ꜱᴜʀᴇ <a href=https://t.me/{temp.B_LINK} ʙᴏᴛ</a> ɪꜱ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ\n\n<code>{e}</code></b>"
        )
    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply_text(
            f"🫥 <code>{channel_id}</code> ᴛʜɪꜱ ɪꜱ ɴᴏᴛ ᴄʜᴀɴɴᴇʟ, ꜱᴇɴᴅ ᴍᴇ ᴏɴʟʏ ᴄʜᴀɴɴᴇʟ ɪᴅ ɴᴏᴛ ɢʀᴏᴜᴘ ɪᴅ</b>"
        )
    await save_group_settings(grp_id, "fsub_id", channel_id)
    mention = message.from_user.mention
    await client.send_message(
        LOG_API_CHANNEL,
        f"#Fsub_Channel_set\n\nᴜꜱᴇʀ - {mention} ꜱᴇᴛ ᴛʜᴇ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}:\n\nꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ - {chat.title}\nɪᴅ - `{channel_id}`",
    )
    await message.reply_text(
        f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\nᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ - {chat.title}\nɪᴅ - <code>{channel_id}</code></b>"
    )


@Client.on_message(filters.command("remove_fsub"))
async def remove_fsub(client, message):
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    settings = await get_settings(grp_id)
    if settings["fsub_id"] == AUTH_CHANNEL:
        await message.reply_text(
            "<b>ᴄᴜʀʀᴇɴᴛʟʏ ɴᴏ ᴀɴʏ ғᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ.... <code>[ᴅᴇғᴀᴜʟᴛ ᴀᴄᴛɪᴠᴀᴛᴇ]</code></b>"
        )
    else:
        await save_group_settings(grp_id, "fsub_id", AUTH_CHANNEL)
        mention = message.from_user.mention
        await client.send_message(
            LOG_API_CHANNEL,
            f"#Remove_Fsub_Channel\n\nᴜꜱᴇʀ - {mention} ʀᴇᴍᴏᴠᴇ ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ ꜰʀᴏᴍ {title}",
        )
        await message.reply_text("<b>✅ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ꜰᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ.</b>")


@Client.on_message(filters.command("reset_group"))
async def reset_group_command(client, message):
    grp_id = message.chat.id
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    sts = await message.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    btn = [[InlineKeyboardButton("🚫 ᴄʟᴏsᴇ 🚫", callback_data="close_data")]]
    reply_markup = InlineKeyboardMarkup(btn)
    await save_default_settings(grp_id)
    await message.reply_text("ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ...")


@Client.on_chat_member_updated()
async def track_private_block_unblock(client, update):
    """Track users blocking/unblocking the bot in LOG_VR_CHANNEL."""
    try:
        chat = update.chat
        old_member = update.old_chat_member
        new_member = update.new_chat_member
        if not chat or chat.type != enums.ChatType.PRIVATE:
            return
        # In a private chat, the bot's membership changes when the user blocks
        # or unblocks it. LEFT/BANNED are treated as blocked; MEMBER as unblocked.
        old_status = getattr(old_member, "status", None)
        new_status = getattr(new_member, "status", None)
        blocked_statuses = {
            enums.ChatMemberStatus.LEFT,
            enums.ChatMemberStatus.BANNED,
        }
        if new_status in blocked_statuses and old_status not in blocked_statuses:
            event = "🚫 USER BLOCKED BOT"
        elif new_status == enums.ChatMemberStatus.MEMBER and old_status in blocked_statuses:
            event = "✅ USER UNBLOCKED BOT"
        else:
            return

        user = getattr(new_member, "user", None) or getattr(old_member, "user", None)
        if not user:
            return
        now = _ist_now()
        await client.send_message(
            LOG_VR_CHANNEL,
            "\n".join([
                f"<b>{event}</b>",
                f"👤 User: {user.mention} [ <code>{user.id}</code> ]",
                f"🔗 Username: @{user.username}" if user.username else "🔗 Username: —",
                f"📆 Time: {now.strftime('%-d %B %Y %I:%M%p %A')}",
            ]),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Could not track private block/unblock event")
