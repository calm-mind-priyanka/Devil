"""
Premium plan selection, payment screenshot intake, subscription lifecycle and
admin controls. This module is intentionally additive: it uses the bot's
existing users collection and db.has_premium_access/remove_premium_access.
"""
import asyncio
import datetime
import hashlib
import io
import logging
import re
from html import escape

import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image, ImageOps, ImageFilter
import pytesseract

from info import (
    ADMINS,
    LOG_CHANNEL,
    PAYMENT_BOT_TOKEN,
    PAYMENT_BOT_USERNAME,
    PAYMENT_ADMIN_IDS,
    PREMIUM_PLANS,
    PAYMENT_OCR_ENABLED,
    PAYMENT_MAX_DELAY_MINUTES,
    PAYMENT_FUTURE_TOLERANCE_MINUTES,
    API_ID,
    API_HASH,
)
from database.users_chats_db import db

LOGGER = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")
UTC = datetime.timezone.utc
LIFETIME_EXPIRY = datetime.datetime(9999, 12, 31, 23, 59, 59)
PAYMENT_VERIFIER_VERSION = "2026-08-28-v4"


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



def _money_number(value):
    """Normalize a displayed amount to numeric rupees.

    Currency symbols and leading zeroes are formatting, not value.  Thus
    ₹23, ₹23.00, Rs 23, INR 23 and ₹023 all normalize to 23.00.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    text = re.sub(r"(?i)(?:₹|rs\.?|inr)\s*", "", text)
    m = re.search(r"(?<!\d)(\d+(?:[.]\d{1,2})?)(?!\d)", text)
    if not m:
        return None
    try:
        return round(float(m.group(1)), 2)
    except ValueError:
        return None


def _expected_amount(plan_price):
    return _money_number(plan_price)


def _extract_amount(text, expected):
    """Extract the payment amount from varied OCR output.

    Accepts currency-labelled and bare amounts. OCR often changes the rupee
    sign (₹) into ¥ or drops it completely, so context and the pending order
    amount are used to select the candidate rather than requiring one format.
    """
    if not text:
        return None
    expected = _money_number(expected)
    normalized = (text or "").replace("\u00a0", " ")
    lines = [re.sub(r"\s+", " ", x.strip()) for x in normalized.splitlines() if x.strip()]
    candidates = []

    def add(value, score):
        if value is None or value < 0 or value >= 10000000:
            return
        candidates.append((round(float(value), 2), score))

    # Currency symbols and common OCR substitutions: ₹, ¥, Rs, INR.
    currency_patterns = [
        r"(?:₹|¥|rs\.?|inr)\s*([0-9][0-9,]*(?:[.,][0-9]{1,2})?)",
        r"(?:amount\s*(?:paid|sent|debited|received)?|paid\s*(?:amount)?|sent\s*amount|total|payment)\D{0,50}([0-9][0-9,]*(?:[.,][0-9]{1,2})?)",
    ]
    for line in lines:
        for pat in currency_patterns:
            for m in re.finditer(pat, line, re.I):
                add(_money_number(m.group(1).replace(',', '')), 110)

    # Standalone amount line, including OCR forms such as <23:00 or ¥23.00.
    for line in lines:
        stripped = line.strip()
        m = re.fullmatch(r"[^0-9]{0,12}(\d{1,7})(?:[.,:]([0-9]{1,2}))?[^0-9]{0,12}", stripped)
        if m:
            whole, frac = m.groups()
            value = float(f"{whole}.{frac}") if frac is not None else float(whole)
            add(value, 95)

    # Bare amount next to payment-related words.
    flat = re.sub(r"\s+", " ", normalized)
    for pat in currency_patterns:
        for m in re.finditer(pat, flat, re.I):
            add(_money_number(m.group(1).replace(',', '')), 105)

    if expected is not None:
        matches = [c for c in candidates if abs(c[0] - expected) <= 0.01]
        if matches:
            return max(matches, key=lambda c: c[1])[0]
        return None
    return max(candidates, key=lambda c: c[1])[0] if candidates else None


def _parse_transaction_datetime(text, reference, expected_amount=None):
    """Extract transaction date/time from flexible payment-app formats."""
    if not text:
        return None, False
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()
    ref_ist = _aware_ist(reference) or reference
    expected = _money_number(expected_amount)
    date_candidates = []

    # Numeric dates: 28/08/2026, 28-08-2026, 28.08.2026.
    for pat in (r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", r"\b(\d{1,2})[.](\d{1,2})[.](\d{2,4})\b"):
        for m in re.finditer(pat, cleaned):
            d, mo, y = map(int, m.groups())
            if y < 100: y += 2000
            try: date_candidates.append((datetime.date(y, mo, d), m.start()))
            except ValueError: pass

    months = {name.lower(): i for i, name in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"), 1)}
    for i, name in enumerate(("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"), 1):
        months[name.lower()] = i
    month_re = r"January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    for pat in (
        rf"\b(\d{{1,2}})\s*,?\s*({month_re})\s*,?\s*(\d{{2,4}})?\b",
        rf"\b({month_re})\s*,?\s*(\d{{1,2}})\s*,?\s*(\d{{2,4}})?\b",
    ):
        for m in re.finditer(pat, cleaned, re.I):
            if m.group(1).isdigit(): d, mon, year = int(m.group(1)), m.group(2), m.group(3)
            else: mon, d, year = m.group(1), int(m.group(2)), m.group(3)
            y = int(year) if year else ref_ist.year
            if y < 100: y += 2000
            try: date_candidates.append((datetime.date(y, months[mon.lower().replace('sept','sep') if mon.lower() != 'sept' else 'sep'], d), m.start()))
            except (ValueError, KeyError): pass

    for word, delta in (("today", 0), ("yesterday", 1)):
        m = re.search(rf"\b{word}\b", cleaned, re.I)
        if m: date_candidates.append((ref_ist.date() - datetime.timedelta(days=delta), m.start()))

    time_candidates = []
    time_re = re.compile(r"(?<!\d)(\d{1,2})\s*[:.]\s*(\d{2})(?:\s*[:.]\s*(\d{2}))?\s*(AM|PM|A\.M\.|P\.M\.)?(?!\d)", re.I)
    for m in time_re.finditer(cleaned):
        hour, minute = int(m.group(1)), int(m.group(2)); second = int(m.group(3) or 0)
        ap = (m.group(4) or '').upper().replace('.', '')
        if ap:
            if hour > 12: continue
            if hour == 12: hour = 0
            if ap == 'PM': hour += 12
        if hour > 23 or minute > 59 or second > 59: continue
        # A bare HH:MM equal to the expected amount is likely OCR of the amount.
        likely_amount = expected is not None and abs(hour - expected) <= 0.01 and not ap and m.group(3) is None
        time_candidates.append((datetime.time(hour, minute, second), m.start(), bool(ap), likely_amount))

    if not date_candidates or not time_candidates:
        return None, False

    best = None
    for t, tpos, explicit_ap, likely_amount in time_candidates:
        date, dpos = min(date_candidates, key=lambda x: abs(x[1] - tpos))
        score = (1000 if explicit_ap else 700) - min(abs(dpos - tpos), 1000) * 0.5
        if likely_amount: score -= 600
        cand = (score, date, t)
        if best is None or cand[0] > best[0]: best = cand
    _, date, time = best
    return datetime.datetime.combine(date, time), True


def _payment_success_signal(text):
    lower = (text or "").lower()
    negative = ["failed", "declined", "reversed", "cancelled", "canceled", "pending"]
    if any(word in lower for word in negative):
        return False
    positive = ["payment successful", "paid successfully", "transaction successful", "payment complete", "success", "paid", "sent"]
    return any(word in lower for word in positive)


def _payment_match_result(order, ocr_text, received_at):
    expected = _expected_amount(order.get("plan_price"))
    found = _extract_amount(ocr_text, expected)
    amount_match = found is not None and expected is not None and abs(found - expected) < 0.01
    tx_dt = _parse_transaction_datetime(ocr_text, received_at, expected)
    time_match = None
    time_note = "Transaction date/time could not be read."
    if tx_dt:
        tx_dt = IST.localize(tx_dt).astimezone(UTC).replace(tzinfo=None)
        # The screenshot transaction must belong to this exact payment attempt:
        # from plan selection time through the configured automatic-approval window.
        # Do not allow a transaction timestamp from before the plan was selected.
        lower = _naive_utc(order.get("order_created_at")) or received_at
        upper = lower + datetime.timedelta(minutes=PAYMENT_MAX_DELAY_MINUTES)
        time_match = lower <= tx_dt <= upper
        time_note = f"Transaction time: {_fmt_dt(tx_dt)}"

    success_signal = _payment_success_signal(ocr_text)
    if not PAYMENT_OCR_ENABLED:
        return True, {"ocr_status": "disabled", "amount_found": found, "amount_match": None,
                      "transaction_at": tx_dt, "time_match": None, "success_signal": None,
                      "confidence": 0, "time_note": "OCR checks disabled; sender/order matching used."}

    # Hard rejects: a readable wrong amount or a readable old/out-of-window time
    # must never be auto-approved. Missing optional evidence is handled by confidence.
    hard_fail = amount_match is False or time_match is False
    score = 0
    if amount_match: score += 55
    if time_match: score += 25
    if success_signal: score += 10
    if tx_dt is not None: score += 5
    if re.search(r"(?:utr|rrn|transaction\s*(?:id|no)|reference\s*(?:id|no))\D{0,10}[A-Z0-9-]{6,}", ocr_text or "", re.I):
        score += 5
    passed = (not hard_fail) and amount_match is True and time_match is True and score >= 80
    return passed, {
        "ocr_status": "matched" if passed else "manual_review",
        "amount_found": found, "amount_match": amount_match,
        "transaction_at": tx_dt, "time_match": time_match,
        "success_signal": success_signal, "confidence": score,
        "time_note": time_note,
    }


async def _ocr_payment_message(payment_client, message):
    if not PAYMENT_OCR_ENABLED:
        return "", "disabled", None, None
    try:
        raw = await payment_client.download_media(message, in_memory=True)
        if raw is None:
            return "", "download_failed", None, None
        raw.seek(0)
        blob = raw.read()
        sha256 = hashlib.sha256(blob).hexdigest()
        image = Image.open(io.BytesIO(blob)).convert("RGB")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2600, 2600))
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        gray = gray.filter(ImageFilter.SHARPEN)
        variants = [gray, ImageOps.invert(gray)]
        texts = []
        for variant in variants:
            for psm in (6, 11, 12):
                try:
                    value = pytesseract.image_to_string(variant, config=f"--psm {psm}", timeout=12)
                    if value and value.strip():
                        texts.append(value.strip())
                except Exception:
                    continue
        # Keep unique OCR outputs together so different layout modes can complement each other.
        text = "\n".join(dict.fromkeys(texts))[:12000]
        small = ImageOps.fit(gray, (32, 32))
        pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if px >= avg else '0' for px in pixels)
        perceptual = hex(int(bits, 2))[2:].zfill(256)
        return text, "ok", sha256, perceptual
    except Exception:
        LOGGER.exception("Payment screenshot OCR failed.")
        return "", "ocr_failed", None, None


async def _activate_order(client, order, screenshot_message_id):
    """Grant Premium using the exact plan stored on the payment order.

    Older orders may contain a display name (for example ``01 WEEK``) instead
    of the internal plan key (``week``), so resolve both forms before touching
    the user or order. This prevents manual approval from falsely failing.
    """
    user_id = int(order["user_id"])
    now = _now()

    raw_plan = str(order.get("selected_plan") or "").strip()
    plan_key = _plan_key(raw_plan)
    if not plan_key:
        raw_lower = raw_plan.lower()
        for key, item in PREMIUM_PLANS.items():
            if raw_lower == str(item.get("name", "")).lower():
                plan_key = key
                break
    if not plan_key:
        # Final compatibility fallback for records that only preserved duration.
        raw_duration = str(order.get("plan_duration") or "").lower().strip()
        for key, item in PREMIUM_PLANS.items():
            if raw_duration == str(item.get("duration", "")).lower().strip():
                plan_key = key
                break
    if not plan_key or plan_key not in PREMIUM_PLANS:
        raise RuntimeError(f"Unknown Premium plan on payment order: {raw_plan or order.get('plan_duration')!r}")

    # Renewal rule: preserve remaining time. If current Premium is active,
    # add the selected duration to its existing expiry instead of overwriting it.
    current = await db.get_user(user_id)
    current_expiry = _naive_utc(current.get("expiry_time")) if current else None
    if isinstance(current_expiry, datetime.datetime) and current_expiry > now:
        base = current_expiry
    else:
        base = now

    new_expiry = _expiry_from(base, plan_key)

    # This is the existing Premium access store used by the rest of the bot.
    await db.update_user({
        "id": user_id,
        "expiry_time": new_expiry,
        "premium_plan": plan_key,
        "premium_plan_name": order["plan_duration"],
        "premium_price": order["plan_price"],
    })

    await db.set_order_activation(user_id, now, new_expiry)
    await db.premium_orders.update_one(
        {"user_id": user_id},
        {"$set": {
            "screenshot_message_id": int(screenshot_message_id),
            "selected_plan": plan_key,
            "payment_status": "manually_verified",
            "premium_status": "active",
        }},
    )

    is_renewal = isinstance(current_expiry, datetime.datetime) and current_expiry > now
    plan = PREMIUM_PLANS[plan_key]
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
            f"Payment status: <code>manually_verified</code>\n"
            f"Premium status: <code>active</code>\n"
            f"Expires: {_fmt_dt(new_expiry)}\n\n"
            "⚠️ Screenshot is a payment submission only. Manual transaction "
            "verification is still required.",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as exc:
        LOGGER.warning("Could not write payment log: %s", exc)


async def process_payment_submission(payment_client, message):
    """Handle a screenshot, verify sender/order and perform a soft OCR check."""
    sender = message.from_user
    if not sender:
        return

    user_id = int(sender.id)
    received_at = _now()
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
        "full_name": (sender.first_name or "") + ((" " + sender.last_name) if sender.last_name else ""),
        "payment_bot_message_id": int(message.id),
        "payment_chat_id": int(message.chat.id),
        "media_type": media_kind,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "caption": message.caption or "",
        "received_at": received_at,
        "matched_order": bool(order),
        "status": "matched" if order else "unmatched",
        "review_status": "pending" if order else "not_required",
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

    ocr_text, ocr_status, file_sha256, perceptual_hash = await _ocr_payment_message(payment_client, message)
    duplicate = await db.find_duplicate_payment_submission(file_sha256, perceptual_hash, user_id, message.id)
    passed, check = _payment_match_result(order, ocr_text, received_at)
    if duplicate:
        passed = False
        check["duplicate_suspected"] = True
    else:
        check["duplicate_suspected"] = False
    await db.update_payment_submission(
        user_id,
        message.id,
        {
            "ocr_status": check["ocr_status"],
            "ocr_text": ocr_text[:4000],
            "amount_found": check["amount_found"],
            "amount_match": check["amount_match"],
            "transaction_at": check["transaction_at"],
            "time_match": check["time_match"],
            "ocr_engine_status": ocr_status,
            "file_sha256": file_sha256,
            "perceptual_hash": perceptual_hash,
            "confidence": check.get("confidence"),
            "success_signal": check.get("success_signal"),
            "duplicate_suspected": check.get("duplicate_suspected", False),
        },
    )

    if not passed:
        await db.update_payment_submission(
            user_id, message.id,
            {"review_status": "manual_review_required"}
        )
        await db.update_order_payment_review(user_id, message.id, check)
        # Build an admin-only verification report. Keep the exact technical reason
        # visible to reviewers so they can understand why auto-approval stopped.
        reason = []
        if check["amount_match"] is False:
            reason.append("Amount does not match the selected plan.")
        elif check["amount_match"] is None:
            reason.append("Payment amount could not be read confidently.")
        if check["time_match"] is False:
            reason.append("Transaction date/time is outside the allowed 10-minute window.")
        elif check["time_match"] is None:
            reason.append("Transaction date/time could not be read confidently.")
        
        if check.get("duplicate_suspected"):
            reason.append("The same or a very similar screenshot was already submitted.")
        if check.get("ocr_status") == "disabled":
            reason.append("OCR verification is disabled, so automatic evidence checks were unavailable.")
        elif ocr_status == "download_failed":
            reason.append("The screenshot could not be downloaded for analysis.")
        elif ocr_status == "ocr_failed":
            reason.append("OCR analysis failed while reading this screenshot.")
        elif not reason:
            reason.append("The available evidence did not reach the automatic approval threshold.")

        lower = _naive_utc(order.get("order_created_at")) or received_at
        upper = lower + datetime.timedelta(minutes=PAYMENT_MAX_DELAY_MINUTES)
        amount_found = check.get("amount_found")
        tx_at = check.get("transaction_at")
        amount_result = "Matched" if check.get("amount_match") is True else ("Not matched" if check.get("amount_match") is False else "Not confidently detected")
        time_result = "Within allowed window" if check.get("time_match") is True else ("Outside allowed window" if check.get("time_match") is False else "Not confidently detected")
        success_result = "Detected" if check.get("success_signal") is True else ("Not detected" if check.get("success_signal") is False else "Not available")
        duplicate_result = "Suspected duplicate" if check.get("duplicate_suspected") else "No duplicate detected"
        ocr_result = str(ocr_status or "unknown").replace("_", " ").title()
        confidence = check.get("confidence")
        confidence_text = f"{confidence}%" if isinstance(confidence, (int, float)) else "N/A"
        reasons_block = "\n".join(f"• {item}" for item in reason)

        sender_name = " ".join(part for part in [sender.first_name, sender.last_name] if part) or "Unknown"
        sender_username = f"@{sender.username}" if sender.username else "none"
        review_text = (
            "🟡 <b>Payment screenshot needs manual review</b>\n\n"
            f"👤 User: {escape(sender_name)}\n"
            f"🔗 Username: {escape(sender_username)}\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"📦 Plan: {escape(str(order.get('plan_duration', 'N/A')))}\n"
            f"💰 Expected amount: {escape(str(order.get('plan_price', 'N/A')))}\n"
            f"🆔 Screenshot message: <code>{message.id}</code>\n\n"
            "<b>🔎 Automatic analysis report</b>\n"
            f"• Verifier version: {PAYMENT_VERIFIER_VERSION}\n"
            f"• OCR status: {escape(ocr_result)}\n"
            f"• Amount found: {escape(str(amount_found) if amount_found is not None else 'Not detected')}\n"
            f"• Amount check: {escape(amount_result)}\n"
            f"• Transaction date/time: {escape(_fmt_dt(tx_at) if tx_at else 'Not detected')}\n"
            f"• Time check: {escape(time_result)}\n"
            f"• Allowed window: {_fmt_dt(lower)} → {_fmt_dt(upper)} ({PAYMENT_MAX_DELAY_MINUTES} min)\n"
            f"• Payment-success signal: {escape(success_result)}\n"
            f"• Duplicate check: {escape(duplicate_result)}\n"
            f"• Verification confidence: {escape(confidence_text)}\n\n"
            "<b>⚠️ Exact reason(s) for manual review</b>\n"
            f"{escape(reasons_block)}\n\n"
            "Premium was <b>not</b> activated automatically. Please review the screenshot and choose Approve or Reject."
        )
        review_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ APPROVE PAYMENT", callback_data=f"payapprove:{user_id}:{message.id}"),
                InlineKeyboardButton("❌ REJECT PAYMENT", callback_data=f"payreject:{user_id}:{message.id}"),
            ]
        ])
        for admin_id in _admins():
            try:
                await payment_client.send_message(
                    admin_id,
                    review_text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=review_buttons,
                )
                await payment_client.copy_message(
                    admin_id,
                    message.chat.id,
                    message.id,
                )
            except Exception as exc:
                LOGGER.warning("Could not send manual payment review to %s: %s", admin_id, exc)
        try:
            await message.reply_text(
                "🟡 <b>Payment screenshot received successfully.</b>\n\n"
                "Your payment verification is currently being completed. Please wait for the result. ⏳"
            )
        except Exception:
            pass
        return

    await db.update_payment_submission(
        user_id, message.id,
        {"review_status": "auto_approved"}
    )
    claimed = await db.activate_premium_order(user_id, message.id)
    if not claimed:
        await db.update_payment_submission(
            user_id, message.id, {"status": "duplicate_after_activation"}
        )
        return

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
        plan_key,
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
    async for order in db.get_pending_manual_verifications():
        rows.append(
            f"👤 <code>{order['user_id']}</code> | "
            f"{escape(order.get('username') or 'no username')}\n"
            f"📦 {escape(order.get('plan_duration', 'N/A'))} | "
            f"💰 {escape(order.get('plan_price', 'N/A'))}\n"
            f"💳 Status: <code>{escape(order.get('payment_status', 'N/A'))}</code>\n"
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

    screenshot_id = order.get("screenshot_message_id")
    if not screenshot_id:
        return await message.reply_text("No payment screenshot is attached to this order.")
    approved = await db.approve_manual_payment(user_id, screenshot_id)
    if not approved.modified_count:
        return await message.reply_text("This payment is not waiting for manual approval.")
    try:
        fresh = await db.get_premium_order(user_id)
        await _activate_order(client, fresh, screenshot_id)
    except Exception as exc:
        LOGGER.exception("Command approval activation failed for %s", user_id)
        await db.premium_orders.update_one({"user_id": user_id, "screenshot_message_id": screenshot_id}, {"$set": {"payment_status": "manual_review_required", "premium_status": "inactive"}})
        return await message.reply_text("Premium activation failed; the review was restored to pending.")
    await message.reply_text(f"✅ Payment approved and Premium activated for <code>{user_id}</code>.", parse_mode=enums.ParseMode.HTML)


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
    @payment_client.on_callback_query(filters.regex(r"^pay(approve|reject):"))
    async def manual_payment_review_callback(client, query):
        if not query.from_user or query.from_user.id not in _admins():
            return await query.answer("You are not authorized.", show_alert=True)

        parts = query.data.split(":")
        try:
            action = parts[0]
            user_id = int(parts[1])
            screenshot_message_id = int(parts[2]) if len(parts) > 2 else None
        except (ValueError, IndexError):
            return await query.answer("Invalid payment request.", show_alert=True)

        submission = await db.get_payment_submission(user_id, screenshot_message_id)
        if not submission:
            return await query.answer("This payment screenshot was not found.", show_alert=True)

        if action == "payapprove":
            # Lock this exact screenshot while activation is running. Do NOT mark
            # it approved until Premium access and the user notification succeed.
            result = await db.claim_payment_review(user_id, screenshot_message_id, "processing")
            if not result.modified_count:
                current = await db.get_payment_submission(user_id, screenshot_message_id)
                status = ((current or {}).get("review_status") or "processed").replace("_", " ")
                return await query.answer(f"This screenshot is already {status}.", show_alert=True)

            order = await db.get_premium_order(user_id)
            if not order or int(order.get("screenshot_message_id") or -1) != screenshot_message_id:
                await db.update_payment_submission(
                    user_id, screenshot_message_id, {"review_status": "manual_review_required"}
                )
                return await query.answer("The matching payment order changed. Review was kept pending.", show_alert=True)

            # The exact screenshot must still belong to a pending manual-review
            # order. Activate Premium first; only then finalize the review as approved.
            approved = await db.approve_manual_payment(user_id, screenshot_message_id)
            if not approved.modified_count:
                await db.update_payment_submission(
                    user_id, screenshot_message_id, {"review_status": "manual_review_required"}
                )
                return await query.answer("The order could not be approved. Review is still pending.", show_alert=True)

            try:
                order = await db.get_premium_order(user_id)
                if not order:
                    raise RuntimeError("Premium order disappeared during approval")
                await _activate_order(client, order, screenshot_message_id)
            except Exception as exc:
                LOGGER.exception("Manual Premium activation failed for %s", user_id)
                # Never leave a review falsely approved when activation failed.
                await db.premium_orders.update_one(
                    {"user_id": user_id, "screenshot_message_id": screenshot_message_id},
                    {"$set": {
                        "payment_status": "manual_review_required",
                        "premium_status": "inactive",
                    }},
                )
                await db.update_payment_submission(
                    user_id, screenshot_message_id,
                    {"review_status": "manual_review_required", "approval_error": str(exc)[:500]},
                )
                return await query.answer("Premium activation failed. Review was restored to pending.", show_alert=True)

            await db.update_payment_submission(
                user_id, screenshot_message_id,
                {"review_status": "approved", "approval_error": None},
            )
            text = (
                f"✅ <b>Payment approved</b>\n\n"
                f"User ID: <code>{user_id}</code>\n"
                "Premium has been activated successfully."
            )
        else:
            result = await db.claim_payment_review(user_id, screenshot_message_id, "rejected")
            if not result.modified_count:
                status = (submission.get("review_status") or "processed").replace("_", " ")
                return await query.answer(f"This screenshot was already {status}.", show_alert=True)

            # Reject the exact screenshot. Only mark the order rejected when it
            # is still pointing at this same screenshot.
            order = await db.get_premium_order(user_id)
            if order and int(order.get("screenshot_message_id") or -1) == screenshot_message_id:
                await db.reject_manual_payment(user_id, screenshot_message_id)
            try:
                await client.send_message(
                    user_id,
                    "❌ <b>Your payment screenshot was rejected after manual review.</b>\n"
                    "Please contact the admin if you think this is a mistake.",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                pass
            text = (
                f"❌ <b>Payment rejected</b>\n\n"
                f"User ID: <code>{user_id}</code>"
            )

        await query.answer("Payment review completed.")
        try:
            await query.message.edit_text(
                text,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

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
