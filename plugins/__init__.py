from aiohttp import web
from .route import routes
from database.users_chats_db import db
from info import LOG_CHANNEL


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app


async def check_expired_premium(client):
    from .premium_payments import premium_expiry_worker
    await premium_expiry_worker(client)
