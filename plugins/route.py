from aiohttp import web
from pyrogram import enums
import re
import math
import logging
import secrets
import mimetypes
from aiohttp.http_exceptions import BadStatusLine
from Jisshu.bot import JisshuBot, multi_clients, work_loads
from Jisshu.server.exceptions import FIleNotFound, InvalidHash
from Jisshu.util.custom_dl import ByteStreamer
from Jisshu.util.render_template import render_page
from info import *


routes = web.RouteTableDef()


@routes.get(r"/verify-click/{token}")
async def verification_click_tracker(request: web.Request):
    """Record the user's shortener-button click, then return to the bot."""
    token = str(request.match_info.get("token") or "").strip()
    if not token:
        raise web.HTTPNotFound(text="Invalid verification link")

    from database.users_chats_db import db
    from utils import temp
    import pytz
    from datetime import datetime

    record = await db.get_verify_id_by_return_token(token)
    if not record or record.get("verified"):
        raise web.HTTPGone(text="Verification link expired")

    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    already_clicked = bool(record.get("shortlink_clicked_at"))
    await db.update_verify_id_info(
        int(record.get("user_id")),
        str(record.get("hash")),
        {"shortlink_clicked": True, "shortlink_clicked_at": now},
    )

    owner_tracking = False
    try:
        owner_tracking = bool(record.get("owner_shortener", False)) and int(record.get("owner_id")) == int(OWNER_ID)
    except (TypeError, ValueError):
        owner_tracking = False

    if not already_clicked and owner_tracking:
        try:
            user = await JisshuBot.get_users(int(record.get("user_id")))
            group_id = int(record.get("group_id") or 0)
            group_name = "DIRECT PM"
            group_link = "—"
            if group_id:
                try:
                    chat = await JisshuBot.get_chat(group_id)
                    group_name = chat.title or str(group_id)
                    group_link = (
                        f"https://t.me/{chat.username}"
                        if chat.username else getattr(chat, "invite_link", None) or "Private / Invite link unavailable"
                    )
                except Exception:
                    group_name = str(group_id)
                    group_link = "Unavailable"

            await JisshuBot.send_message(
                (LINK_TRACK_CHANNEL or LOG_VR_CHANNEL),
                "\n".join([
                    "<b>🔎 SHORTENER TRACK — SHORTLINK_CLICKED</b>",
                    f"👤 ᴜꜱᴇʀ: {user.mention} [ {user.id} ]",
                    f"📊 ꜱᴛᴀᴛᴜꜱ: {int(record.get('step') or 1)}/3",
                    f"📆 ᴅᴀᴛᴇ: {now.strftime('%-d %B %Y time %-I:%M%p %A')}",
                    f"🤖 Bot: {getattr(JisshuBot, 'username', '')}",
                    f"🏷️ Group Name: {group_name}",
                    f"🔗 Group Link: {group_link}",
                    f"Group: {group_id}",
                    f"Mode: {record.get('mode', 'file')}",
                    f"Domain: {record.get('shortener_domain', 'unknown')}",
                    f"ShortURL: {str(record.get('shortlink') or '')[:700]}",
                ]),
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            logging.exception("Could not write shortlink click tracking log")

    # temp.U_NAME is populated from the same bot account used by commands.py
    # when the shortlink was created. Prefer it over a possibly stale class
    # attribute on the aiohttp-side client.
    bot_username = str(getattr(temp, "U_NAME", "") or getattr(JisshuBot, "username", "") or "").lstrip("@")
    if not bot_username:
        logging.error("Verification redirect failed: bot username is unavailable for token %s", token)
        raise web.HTTPServiceUnavailable(text="Bot is starting")
    redirect_url = f"https://t.me/{bot_username}?start=vr_{token}"
    logging.info("Verification shortlink clicked; redirecting token %s to %s", token, redirect_url)
    raise web.HTTPFound(redirect_url)


@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("InfinityBotzz ~ EDITH")


@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return web.Response(
            text=await render_page(id, secure_hash), content_type="text/html"
        )
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


class_cache = {}


async def media_streamer(request: web.Request, id: int, secure_hash: str):
    range_header = request.headers.get("Range", 0)

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
    logging.debug("before calling get_file_properties")
    file_id = await tg_connect.get_file_properties(id)
    logging.debug("after calling get_file_properties")

    if file_id.unique_id[:6] != secure_hash:
        logging.debug(f"Invalid hash for message with ID {id}")
        raise InvalidHash

    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_id.file_name)
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )
