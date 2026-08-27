from aiohttp import web
from .route import routes
from asyncio import sleep
from datetime import datetime
from database.users_chats_db import db
from info import LOG_CHANNEL


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app


async def check_expired_premium(client):
    # Timestamp-based checker: it survives bot/server restarts and never relies
    # on an in-memory timer for subscription expiry.
    from .premium_payments import premium_expiry_worker
    await premium_expiry_worker(client)
