from pyrogram import idle
import logging
import logging.config
from pathlib import Path

# Get logging configurations
logging.config.fileConfig(str(Path(__file__).with_name("logging.conf")))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)


from pyrogram import __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import *
from utils import temp
from Script import script
from datetime import date, datetime
import pytz
from aiohttp import web
from plugins import web_server, check_expired_premium
import pyrogram.utils
import asyncio
from Jisshu.bot import JisshuBot
from Jisshu.util.keepalive import ping_server
from Jisshu.bot.clients import initialize_clients

JisshuBot.start()
loop = asyncio.get_event_loop()

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647


async def Jisshu_start():
    print("\n")
    print("Credit - Telegram @JISSHU_BOTS")
    bot_info = await JisshuBot.get_me()
    JisshuBot.username = bot_info.username
    await initialize_clients()
    # Plugins are already loaded by Pyrogram via plugins={"root": "plugins"}.
    # Do not manually import them again: duplicate handlers break callbacks.
    if ON_HEROKU:
        asyncio.create_task(ping_server())
    b_users, b_chats = await db.get_banned()
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    await Media.ensure_indexes()
    me = await JisshuBot.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    temp.B_LINK = me.mention
    JisshuBot.username = "@" + me.username
    JisshuBot.loop.create_task(check_expired_premium(JisshuBot))
    logging.info(
        f"{me.first_name} with for Pyrogram v{__version__} (Layer {layer}) started on {me.username}."
    )
    logging.info(script.LOGO)
    tz = pytz.timezone("Asia/Kolkata")
    today = date.today()
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    await JisshuBot.send_message(
        chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(me.mention, today, time)
    )
    await JisshuBot.send_message(
        chat_id=SUPPORT_GROUP, text=f"<b>{me.mention} ʀᴇsᴛᴀʀᴛᴇᴅ 🤖</b>"
    )
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()
    await idle()


if __name__ == "__main__":
    try:
        loop.run_until_complete(Jisshu_start())
    except KeyboardInterrupt:
        logging.info("Service Stopped Bye 👋")
