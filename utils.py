import logging
from pyrogram.errors import (
    InputUserDeactivated,
    UserNotParticipant,
    FloodWait,
    UserIsBlocked,
    PeerIdInvalid,
)
from info import AUTH_CHANNEL, LONG_IMDB_DESCRIPTION, START_IMG
from imdb import Cinemagoer
import asyncio
import aiohttp
from pyrogram.types import Message
from pyrogram import enums
import pytz
import re
import os
from urllib.parse import urlparse
from shortzy import Shortzy
from datetime import datetime
from typing import Any
from database.users_chats_db import db


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BANNED = {}
imdb = Cinemagoer()


class temp(object):
    ME = None
    CURRENT = int(os.environ.get("SKIP", 2))
    CANCEL = False
    U_NAME = None
    B_NAME = None
    B_LINK = None
    SETTINGS = {}
    FILES_ID = {}
    USERS_CANCEL = False
    GROUPS_CANCEL = False
    CHAT = {}
    BANNED_USERS = []
    BANNED_CHATS = []


def formate_file_name(file_name):
    file_name = " ".join(
        filter(
            lambda x: not x.startswith("[")
            and not x.startswith("@")
            and not x.startswith("www."),
            file_name.split(),
        )
    )
    return file_name


async def is_req_subscribed(bot, query):
    if await db.find_join_req(query.from_user.id):
        return True
    try:
        user = await bot.get_chat_member(AUTH_CHANNEL, query.from_user.id)
    except UserNotParticipant:
        pass
    except Exception as e:
        print(e)
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False


async def is_subscribed(bot, user_id, channel_id):
    try:
        user = await bot.get_chat_member(channel_id, user_id)
    except UserNotParticipant:
        pass
    except Exception:
        pass
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False


async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = re.findall(r"[1-2]\d{3}$", query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = re.findall(r"[1-2]\d{3}", file, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None
        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None
        if year:
            filtered = list(filter(lambda k: str(k.get("year")) == str(year), movieid))
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid = list(
            filter(lambda k: k.get("kind") in ["movie", "tv series"], filtered)
        )
        if not movieid:
            movieid = filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"
    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get("plot")
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = movie.get("plot outline")
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."

    return {
        "title": movie.get("title"),
        "votes": movie.get("votes"),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "box_office": movie.get("box office"),
        "localized_title": movie.get("localized title"),
        "kind": movie.get("kind"),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")),
        "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_str(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "writer": list_to_str(movie.get("writer")),
        "producer": list_to_str(movie.get("producer")),
        "composer": list_to_str(movie.get("composer")),
        "cinematographer": list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        "release_date": date,
        "year": movie.get("year"),
        "genres": list_to_str(movie.get("genres")),
        "poster": movie.get("full-size cover url", START_IMG),
        "plot": plot,
        "rating": str(movie.get("rating")),
        "url": f"https://www.imdb.com/title/tt{movieid}",
    }


async def users_broadcast(user_id, message, is_pin):
    try:
        m = await message.copy(chat_id=user_id)
        if is_pin:
            await m.pin(both_sides=True)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await users_broadcast(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - Removed from Database, since Blocked the bot.")
        await db.delete_user(user_id)
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception:
        return False, "Error"


async def groups_broadcast(chat_id, message, is_pin):
    try:
        m = await message.copy(chat_id=chat_id)
        if is_pin:
            try:
                await m.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await groups_broadcast(chat_id, message)
    except Exception:
        await db.delete_chat(chat_id)
        logging.info(f"{chat_id}-Removed from Database.")
        return "Error"


async def get_settings(group_id):
    settings = await db.get_settings(int(group_id))
    return settings


async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    await db.update_settings(group_id, current)


def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])


def get_name(name):
    regex = re.sub(r"@\w+", "", name)
    return regex


def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    else:
        return ", ".join(str(item) for item in k)


def normalize_shortener_domain(site):
    """Normalize a configured shortener URL/domain for provider matching."""
    value = str(site or "").strip().rstrip("/")
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    value = value.split("/", 1)[0].strip().rstrip(".").lower()
    if value.startswith("www."):
        value = value[4:]
    return value


async def create_shortlink(link, api, site):
    """Create a short URL using provider-specific APIs where required.

    LinkCut has a dedicated GET endpoint and JSON response schema. Other
    providers continue to use the existing Shortzy conversion and quick-link
    fallback paths.
    """
    raw_site = str(site or "").strip()
    domain = normalize_shortener_domain(raw_site)
    api = str(api or "").strip()
    if not domain or not api or not link:
        logger.warning("Shortener not configured: domain_present=%s api_present=%s link_present=%s",
                       bool(domain), bool(api), bool(link))
        return None

    logger.info("Shortener provider selected: %s", domain)
    if domain == "linkcut.org":
        timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://linkcut.org/api",
                    params={"api": api, "url": str(link)},
                    headers={"Accept": "application/json", "User-Agent": "IMDXBot/1.0"},
                ) as response:
                    body = await response.text()
                    content_type = str(response.headers.get("Content-Type", "")).lower()
                    if response.status < 200 or response.status >= 300:
                        logger.warning("LinkCut API HTTP failure: status=%s content_type=%s",
                                       response.status, content_type)
                        return None
                    if not body.strip():
                        logger.warning("LinkCut API returned an empty response: status=%s content_type=%s",
                                       response.status, content_type)
                        return None
                    try:
                        payload = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        logger.warning("LinkCut API returned invalid JSON: status=%s content_type=%s",
                                       response.status, content_type)
                        return None
                    if not isinstance(payload, dict):
                        logger.warning("LinkCut API returned unexpected JSON type: %s", type(payload).__name__)
                        return None
                    short_url = payload.get("shortenedUrl")
                    if str(payload.get("status", "")).lower() == "success" and isinstance(short_url, str):
                        short_url = short_url.strip()
                        parsed = urlparse(short_url)
                        if parsed.scheme in {"https", "http"} and parsed.netloc:
                            return short_url
                        logger.warning("LinkCut API success response had an invalid shortenedUrl")
                        return None
                    logger.warning("LinkCut API reported failure: status=%r", payload.get("status"))
                    if not short_url:
                        logger.warning("LinkCut API response did not include shortenedUrl")
                    return None
        except asyncio.TimeoutError:
            logger.warning("LinkCut API request timed out")
            return None
        except Exception as exc:
            logger.warning("LinkCut API request failed: error_type=%s", type(exc).__name__)
            return None

    # Preserve the exact configured provider value for legacy Shortzy providers.
    shortzy = Shortzy(api, raw_site)
    try:
        result = await shortzy.convert(link)
        if result:
            return str(result)
    except Exception as exc:
        logger.warning("Shortener conversion failed for provider %s: error_type=%s", domain, type(exc).__name__)
    try:
        result = await shortzy.get_quick_link(link)
        return str(result) if result else None
    except Exception as exc:
        logger.warning("Shortener quick-link fallback failed for provider %s: error_type=%s", domain, type(exc).__name__)
        return None


async def get_shortlink(
    link, grp_id, is_second_shortener=False, is_third_shortener=False
):
    settings = await get_settings(grp_id)
    if is_third_shortener:
        api, site = settings["api_three"], settings["shortner_three"]
    elif is_second_shortener:
        api, site = settings["api_two"], settings["shortner_two"]
    else:
        api, site = settings["api"], settings["shortner"]
    return await create_shortlink(link, api, site)


def get_file_id(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    if message.media:
        for attr in media_types:
            media = getattr(message, attr, None)
            if media:
                setattr(media, "message_type", attr)
                return media


# def get_hash(media_msg: Message) -> str:
#    media = get_file_id(media_msg)
#   return getattr(media, "file_unique_id", "")[:6]


def get_status():
    tz = pytz.timezone("Asia/Colombo")
    hour = datetime.now(tz).time().hour
    if 5 <= hour < 12:
        sts = "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ"
    elif 12 <= hour < 18:
        sts = "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏɴ"
    else:
        sts = "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ"
    return sts


async def is_check_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ]
    except:
        return False


async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""
        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1
        unit = ts[index:].lstrip()
        if value:
            value = int(value)
        return value, unit

    value, unit = extract_value_and_unit(time_string)
    if unit == "s":
        return value
    elif unit == "min":
        return value * 60
    elif unit == "hour":
        return value * 3600
    elif unit == "day":
        return value * 86400
    elif unit == "month":
        return value * 86400 * 30
    elif unit == "year":
        return value * 86400 * 365
    else:
        return 0


def get_readable_time(seconds):
    periods = [("days", 86400), ("hour", 3600), ("min", 60), ("sec", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result


async def save_default_settings(id):
    await db.reset_group_settings(id)
    current = await db.get_settings(id)
    temp.SETTINGS.update({id: current})
