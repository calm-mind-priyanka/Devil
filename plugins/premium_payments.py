"""
Premium plan selection, payment screenshot intake, subscription lifecycle and
admin controls. This module is intentionally additive: it uses the bot's
existing users collection and db.has_premium_access/remove_premium_access.
"""
import asyncio
import datetime
import logging
from html import escape

import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import (
    ADMINS,
    LOG_CHANNEL,
    PAYMENT_BOT_TOKEN,
    PAYMENT_BOT_USERNAME,
    PAYMENT_ADMIN_IDS,
    PREMIUM_PLANS,
    API_ID,
    API_HASH,
)
from database.users_chats_db import db

LOGGER = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")
UTC = datetime.timezone.utc
LIFETIME_EXPIRY = datetime.datetime(9999, 12, 31, 23, 59, 59)


def _now():
    # Existing Premium code stores naive datetimes in MongoDB. Keep the same
    # convention for compatibility, representing UTC.
    return datetime.datetime.utcnow()




def _naive_utc(value):
    if not isinstance(value, datetime.datetime):
        return value
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value

def _aware_ist(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(IST)


def _fmt_dt(value):
    value = _aware_ist(value)
    return value.strftime("%d %b %Y %I:%M %p") if value else "N/A"


def _admins():
    return set(ADMINS) | set(PAYMENT_ADMIN_IDS)


def _plan_key(value):
    value = str(value).lower().strip()
    aliases = {
        "7": "week", "7day": "week", "7days": "week", "week": "week",
        "30": "month", "30day": "month", "30days": "month", "month": "month",
        "90": "3month", "3month": "3month", "3months": "3month",
        "180": "6month", "6month": "6month", "6months": "6month",
        "365": "year", "1year": "year", "year": "year", "12month": "year",
        "lifetime": "lifetime", "life": "lifetime",
    }
    return aliases.get(value, value if value in PREMIUM_PLANS else None)


def _expiry_from(base, plan):
    days = PREMIUM_PLANS[plan]["days"]
    if days is None:
        return LIFETIME_EXPIRY
    return base + datetime.timedelta(days=days)


def _remaining_label(expires_at):
    seconds = max(0, int((expires_at - _now()).total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


async def _activate_order(client, order, screenshot_message_id):
    """Grant existing Premium access from a claimed payment order."""
    user_id = int(order["user_id"])
    now = _now()

    # Renewal rule: preserve remaining time. If current Premium is active,
    # add the selected duration to its existing expiry instead of overwriting it.
    current = await db.get_user(user_id)
    current_expiry = _naive_utc(current.get("expiry_time")) if current else None
    if isinstance(current_expiry, datetime.datetime) and current_expiry > now:
        base = current_expiry
    else:
        base = now

    new_expiry = _expiry_from(base, order["selected_plan"])

    # This is the existing Premium access store used by the rest of the bot.
    await db.update_user({
        "id": user_id,
        "expiry_time": new_expiry,
        "premium_plan": order["selected_plan"],
        "premium_plan_name": order["plan_duration"],
        "premium_price": order["plan_price"],
    })

    await db.set_order_activation(user_id, now, new_expiry)
    await db.premium_orders.update_one(
        {"user_id": user_id},
        {"$set": {
            "screenshot_message_id": int(screenshot_message_id),
            "payment_status": "pending_manual_verification",
            "premium_status": "active",
        }},
    )

    is_renewal = isinstance(current_expiry, datetime.datetime) and current_expiry > now
    plan = PREMIUM_PLANS[order["selected_plan"]]
    if is_renewal:
        text = (
            "♻️ <b>Premium Renewed Successfully!</b>\n\n"
            f"📦 Plan: {escape(plan['name'])}\n"
            f"⏳ Added: {escape(plan['duration'])}\n"
            f"📅 New Expiry: {_fmt_dt(new_expiry)}\n"
            "🟢 Status: Active\n\n"
            "Thank you for renewing Premium!"
        )
    else:
        text = (
            "✅ <b>Premium Activated Successfully!</b>\n\n"
            f"📦 Plan: {escape(plan['name'])}\n"
            f"⏳ Duration: {escape(plan['duration'])}\n"
            f"📅 Activated: {_fmt_dt(now)}\n"
            f"⏳ Expires: {_fmt_dt(new_expiry)}\n"
            "🟢 Status: Active\n\n"
            "Thank you for purchasing Premium!"
        )
    try:
        await client.send_message(user_id, text, parse_mode=enums.ParseMode.HTML)
    except Exception as exc:
        LOGGER.warning("Could not send Premium activation to %s: %s", user_id, exc)

    try:
        await client.send_message(
            LOG_CHANNEL,
            f"#PREMIUM_PAYMENT_SUBMITTED\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Plan: {escape(plan['name'])}\n"
            f"Price: {escape(plan['price'])}\n"
            f"Screenshot message: <code>{screenshot_message_id}</code>\n"
            f"Payment status: <code>pending_manual_verification</code>\n"
            f"Premium status: <code>active</code>\n"
            f"Expires: {_fmt_dt(new_expiry)}\n\n"
            "⚠️ Screenshot is a payment submission only. Manual transaction "
            "verification is still required.",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as exc:
        LOGGER.warning("Could not write payment log: %s", exc)


async def process_payment_submission(payment_client, message):
    """Handle a photo/image sent to the dedicated payment bot."""
    sender = message.from_user
    if not sender:
        return

    user_id = int(sender.id)
    received_at = _now()

    # Store every submission first, including unmatched submissions.
    media_kind = "photo" if message.photo else "document"
    file_id = None
    file_unique_id = None
    if message.photo:
        file_id = message.photo.file_id
        file_unique_id = message.photo.file_unique_id
    elif message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id

    order = await db.get_pending_premium_order(user_id)

    submission = {
        "user_id": user_id,
        "username": sender.username or "",
        "payment_bot_message_id": int(message.id),
        "payment_chat_id": int(message.chat.id),
        "media_type": media_kind,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "caption": message.caption or "",
        "received_at": received_at,
        "matched_order": bool(order),
        "status": "matched" if order else "unmatched",
    }
    await db.record_payment_submission(submission)

    if not order:
        await _notify_admins(
            payment_client,
            "⚠️ <b>Unmatched payment screenshot</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"👤 Username: @{escape(sender.username) if sender.username else 'none'}\n"
            f"🆔 Message ID: <code>{message.id}</code>\n\n"
            "No pending Premium order was found. Premium was <b>not</b> activated."
        )
        try:
            await message.reply_text(
                "⚠️ No pending Premium order was found for your Telegram account.\n"
                "Premium was not activated. Please select a Premium plan first."
            )
        except Exception:
            pass
        return

    # Claim only the waiting order. A second screenshot cannot activate it twice.
    claimed = await db.activate_premium_order(user_id, message.id)
    if not claimed:
        # It was already processed by another update; retain this submission
        # as a duplicate for manual review.
        await db.payment_submissions.update_one(
            {"user_id": user_id, "payment_bot_message_id": int(message.id)},
            {"$set": {"status": "duplicate_after_activation"}},
        )
        return

    # Preserve a reviewable copy in the existing log channel when possible.
    try:
        await payment_client.copy_message(
            chat_id=LOG_CHANNEL,
            from_chat_id=message.chat.id,
            message_id=message.id,
        )
    except Exception as exc:
        LOGGER.warning("Could not copy payment screenshot to LOG_CHANNEL: %s", exc)

    await _activate_order(payment_client, claimed, message.id)


async def _notify_admins(client, text):
    for admin_id in _admins():
        try:
            await client.send_message(admin_id, text, parse_mode=enums.ParseMode.HTML)
        except Exception as exc:
            LOGGER.warning("Could not notify admin %s: %s", admin_id, exc)


@Client.on_callback_query(filters.regex(r"^buyplan_"), group=1)
async def select_premium_plan(client, query):
    plan_key = _plan_key(query.data.split("_", 1)[1])
    if not plan_key:
        return await query.answer("Invalid Premium plan.", show_alert=True)

    plan = PREMIUM_PLANS[plan_key]
    user = query.from_user
    order = await db.create_or_update_premium_order(
        user.id,
        user.username,
        plan["name"],
        plan["duration"],
        plan["price"],
    )

    buttons = []
    if PAYMENT_BOT_USERNAME:
        buttons.append([
            InlineKeyboardButton(
                "📸 SEND PAYMENT SCREENSHOT",
                url=f"https://t.me/{PAYMENT_BOT_USERNAME}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("• ʙᴀᴄᴋ ᴛᴏ ᴘʟᴀɴꜱ •", callback_data="free"),
        InlineKeyboardButton("• ᴄʟᴏꜱᴇ •", callback_data="close_data"),
    ])

    payment_text = (
        "💳 <b>Premium Order Created</b>\n\n"
        f"📦 Plan: <b>{escape(plan['name'])}</b>\n"
        f"⏳ Duration: <b>{escape(plan['duration'])}</b>\n"
        f"💰 Price: <b>{escape(plan['price'])}</b>\n"
        f"🆔 Order User ID: <code>{user.id}</code>\n"
        "🟡 Payment status: <code>waiting_for_payment</code>\n\n"
        "Complete the payment using the existing payment instructions, then "
        "send the payment screenshot to the dedicated payment bot.\n\n"
        "⚠️ Your screenshot is treated only as a payment submission. "
        "The transaction will still be manually checked by the admin."
    )
    await query.message.edit_text(
        payment_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML,
    )
    await query.answer("Premium plan selected.")


@Client.on_message(filters.command("pending"))
async def pending_payments(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")

    rows = []
    async for order in await db.get_pending_manual_verifications():
        rows.append(
            f"👤 <code>{order['user_id']}</code> | "
            f"{escape(order.get('username') or 'no username')}\n"
            f"📦 {escape(order.get('plan_duration', 'N/A'))} | "
            f"💰 {escape(order.get('plan_price', 'N/A'))}\n"
            f"🖼️ Screenshot: <code>{order.get('screenshot_message_id', 'N/A')}</code>\n"
            f"⏳ Expires: {_fmt_dt(order.get('expires_at'))}\n"
        )
    if not rows:
        return await message.reply_text("No Premium payments are waiting for manual verification.")
    text = "🧾 <b>Pending Manual Payment Verification</b>\n\n" + "\n".join(rows)
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("premium"))
async def premium_details(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /premium USER_ID")

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    order = await db.get_premium_order(user_id)
    user = await db.get_user(user_id)
    if not order and not user:
        return await message.reply_text("User was not found.")

    expiry = _naive_utc(user.get("expiry_time")) if user else None
    active = isinstance(expiry, datetime.datetime) and expiry > _now()
    text = (
        "👤 <b>Premium Details</b>\n\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"👤 Username: @{escape((order or {}).get('username') or 'unknown')}\n"
        f"📦 Plan: {escape((order or {}).get('plan_duration') or user.get('premium_plan_name', 'N/A'))}\n"
        f"💰 Price: {escape((order or {}).get('plan_price') or str(user.get('premium_price', 'N/A')))}\n"
        f"🟢 Premium: {'Active' if active else 'Expired/Inactive'}\n"
        f"📅 Activated: {_fmt_dt((order or {}).get('activated_at'))}\n"
        f"⏳ Expires: {_fmt_dt(expiry)}\n"
        f"💳 Payment: {escape((order or {}).get('payment_status', 'N/A'))}\n"
        f"🔎 Manually verified: {bool((order or {}).get('manually_verified', False))}\n"
        f"🖼️ Screenshot message: {escape(str((order or {}).get('screenshot_message_id', 'N/A')))}"
    )
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("approve"))
async def approve_payment(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /approve USER_ID")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    order = await db.get_premium_order(user_id)
    if not order:
        return await message.reply_text("No Premium payment record found for this user.")

    await db.mark_payment_verified(user_id)
    await message.reply_text(
        f"✅ Payment for <code>{user_id}</code> marked as manually verified.\n"
        "Premium access was not changed.",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command("remove"))
async def remove_premium_payment(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /remove USER_ID")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    result = await db.remove_premium_access(user_id)
    if not result:
        return await message.reply_text("Premium user was not found.")
    await db.set_subscription_expired(user_id)
    await message.reply_text(f"❌ Premium access removed for <code>{user_id}</code>.", parse_mode=enums.ParseMode.HTML)
    try:
        await client.send_message(
            user_id,
            "❌ <b>Premium Plan Removed</b>\n\n"
            "Your Premium access has been removed by an administrator.\n"
            "If this was related to payment verification, please contact the admin.",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        pass


@Client.on_message(filters.command("expire"))
async def expire_now(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    await run_expiry_check(client, notify=True)
    await message.reply_text("✅ Premium expiry check completed.")


@Client.on_message(filters.command("renew"))
async def manual_renew(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 3:
        return await message.reply_text(
            "Usage: /renew USER_ID PLAN\n"
            "PLAN: week, month, 3month, 6month, year, lifetime"
        )
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")
    plan_key = _plan_key(message.command[2])
    if not plan_key:
        return await message.reply_text("Unknown plan.")

    now = _now()
    user = await db.get_user(user_id)
    current = _naive_utc(user.get("expiry_time")) if user else None
    if not isinstance(current, datetime.datetime) or current <= now:
        base = now
    else:
        base = current
    new_expiry = _expiry_from(base, plan_key)
    plan = PREMIUM_PLANS[plan_key]

    await db.update_user({
        "id": user_id,
        "expiry_time": new_expiry,
        "premium_plan": plan_key,
        "premium_plan_name": plan["duration"],
        "premium_price": plan["price"],
    })
    await db.premium_orders.update_one(
        {"user_id": user_id},
        {"$set": {
            "selected_plan": plan_key,
            "plan_duration": plan["duration"],
            "plan_price": plan["price"],
            "premium_status": "active",
            "payment_status": "manually_renewed",
            "activated_at": now,
            "expires_at": new_expiry,
            "reminder_sent": False,
            "manually_verified": True,
            "manually_verified_at": now,
        }},
        upsert=True,
    )
    await message.reply_text(
        f"♻️ Premium renewed for <code>{user_id}</code>.\n"
        f"📦 Plan: {escape(plan['name'])}\n"
        f"⏳ New expiry: {_fmt_dt(new_expiry)}",
        parse_mode=enums.ParseMode.HTML,
    )


async def run_expiry_check(client, notify=True):
    now = _now()

    # New payment/subscription records.
    cursor = db.premium_orders.find({
        "premium_status": "active",
        "expires_at": {"$lte": now},
    })
    async for order in cursor:
        user_id = int(order["user_id"])
        await db.remove_premium_access(user_id)
        await db.set_subscription_expired(user_id, order.get("expires_at") or now)
        if notify:
            try:
                await client.send_message(
                    user_id,
                    "❌ <b>Premium Plan Expired</b>\n\n"
                    f"📦 Plan: {escape(order.get('plan_duration', 'Premium'))}\n"
                    f"📅 Expired: {_fmt_dt(order.get('expires_at') or now)}\n"
                    "🔴 Status: Expired\n\n"
                    "Your Premium access has ended.\n\n"
                    "🔄 Purchase a new Premium plan to continue.",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send expiry notice to %s: %s", user_id, exc)

    # Four-day reminder. On restart, a missed exact moment is recovered by
    # sending once while the subscription is still active and inside the window.
    four_days = datetime.timedelta(days=4)
    cursor = db.premium_orders.find({
        "premium_status": "active",
        "reminder_sent": {"$ne": True},
        "expires_at": {"$gt": now},
    })
    async for order in cursor:
        expires_at = _naive_utc(order.get("expires_at"))
        if not isinstance(expires_at, datetime.datetime):
            continue
        if expires_at - now <= four_days:
            user_id = int(order["user_id"])
            try:
                await client.send_message(
                    user_id,
                    "⚠️ <b>Premium Expiring Soon</b>\n\n"
                    f"📦 Plan: {escape(order.get('plan_duration', 'Premium'))}\n"
                    "⏳ Remaining: 4 Days or less\n"
                    f"📅 Expiry: {_fmt_dt(expires_at)}\n\n"
                    "Renew your Premium plan to continue using the service.",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send 4-day reminder to %s: %s", user_id, exc)
            await db.mark_reminder_sent(user_id)

    # Legacy/manual Premium records not created through the payment flow.
    # This keeps the existing /add_premium feature working exactly as before.
    legacy = await db.get_expired(now)
    for user in legacy:
        user_id = int(user["id"])
        current = await db.get_premium_order(user_id)
        # Don't overwrite a newer active payment subscription.
        if current and current.get("premium_status") == "active":
            continue
        expiry = _naive_utc(user.get("expiry_time"))
        await db.remove_premium_access(user_id)
        if notify:
            try:
                target = await client.get_users(user_id)
                await client.send_message(
                    user_id,
                    f"<b>ʜᴇʏ {target.mention},\n\n"
                    "ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ, "
                    "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇ 😊\n\n"
                    "ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ᴛʜᴇ ᴘʀᴇᴍɪᴜᴍ ᴀɢᴀɪɴ, "
                    "ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ /plan ꜰᴏʀ ᴛʜᴇ ᴅᴇᴛᴀɪʟs ᴏꜰ ᴛʜᴇ ᴘʟᴀɴs...</b>",
                    parse_mode=enums.ParseMode.HTML,
                )
                await client.send_message(
                    LOG_CHANNEL,
                    f"<b>#Premium_Expire\n\nUser name: {target.mention}\n"
                    f"User id: <code>{user_id}</code></b>",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send legacy expiry notice for %s: %s", user_id, exc)


async def premium_expiry_worker(client):
    while True:
        try:
            await run_expiry_check(client, notify=True)
        except Exception:
            LOGGER.exception("Premium expiry checker failed; retrying.")
        await asyncio.sleep(10)


def register_payment_bot_handlers(payment_client):
    @payment_client.on_message(
        filters.private & (filters.photo | filters.document)
    )
    async def payment_screenshot_handler(client, message):
        if message.document and not (
            (message.document.mime_type or "").lower().startswith("image/")
        ):
            return
        try:
            await process_payment_submission(client, message)
        except Exception:
            LOGGER.exception("Payment screenshot processing failed.")
            try:
                await message.reply_text(
                    "⚠️ Your screenshot was received, but processing failed temporarily. "
                    "Please contact the admin."
                )
            except Exception:
                pass
