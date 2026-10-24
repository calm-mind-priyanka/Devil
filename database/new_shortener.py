"""Independent three-step shortener state with an Asia/Kolkata calendar-day boundary.

This module intentionally stores state in the existing general-data MongoDB
(`misc` collection); it does not create another database or persistent store.
"""
from datetime import datetime, timedelta
from secrets import token_urlsafe
import pytz

IST = pytz.timezone("Asia/Kolkata")


def current_ist_date(now=None):
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = pytz.UTC.localize(now)
    return now.astimezone(IST).date().isoformat()


def state_key(user_id, group_id):
    return f"new_shortener:{int(group_id)}:{int(user_id)}"


async def get_state(user_id, group_id, now=None):
    """Return today's state; stale progress is logically expired on read."""
    from database.users_chats_db import db
    key = state_key(user_id, group_id)
    today = current_ist_date(now)
    row = await db.misc.find_one({"_id": key})
    if not row or row.get("ist_date") != today:
        # Persist the date transition lazily on the first relevant request. This
        # works after downtime/redeployments and does not depend on a timer.
        fresh = {"_id": key, "user_id": int(user_id), "group_id": int(group_id),
                 "ist_date": today, "completed_step": 0, "attempt_token": None,
                 "attempt_step": None, "completed": False}
        await db.misc.update_one(
            {"_id": key}, {"$set": {k: v for k, v in fresh.items() if k != "_id"}},
            upsert=True,
        )
        return fresh
    return row


async def begin_step(user_id, group_id, step, now=None):
    """Create a date-bound attempt only for the next required step."""
    step = int(step)
    if step not in (1, 2, 3):
        raise ValueError("step must be 1, 2, or 3")
    state = await get_state(user_id, group_id, now)
    completed_step = int(state.get("completed_step", 0))
    if (state.get("completed") or step != completed_step + 1
            or state.get("attempt_token")):
        # Do not invalidate an already-issued link when users double-click or
        # request multiple files concurrently before completing the current step.
        return None
    from database.users_chats_db import db
    token = token_urlsafe(12)
    today = current_ist_date(now)
    result = await db.misc.update_one(
        {"_id": state["_id"], "ist_date": today, "completed_step": completed_step,
         "completed": False, "$or": [{"attempt_token": None}, {"attempt_token": {"$exists": False}}]},
        {"$set": {"user_id": int(user_id), "group_id": int(group_id),
                  "ist_date": today, "attempt_step": step, "attempt_token": token,
                  "completed": False}},
    )
    return token if getattr(result, "modified_count", 0) == 1 else None


async def accept_step(user_id, group_id, step, token, enabled=True, gap_seconds=0, now=None):
    """Accept a callback only for its user/group/date/token and next ordered step."""
    if not enabled:
        return False
    from database.users_chats_db import db
    step = int(step)
    state = await get_state(user_id, group_id, now)
    if state.get("completed") or state.get("ist_date") != current_ist_date(now):
        return False
    if int(state.get("attempt_step") or 0) != step:
        return False
    if int(state.get("completed_step", 0)) + 1 != step:
        return False
    if not token or token != state.get("attempt_token"):
        return False
    new_completed = step
    completed_at = datetime.now(IST) if now is None else now
    if completed_at.tzinfo is None:
        completed_at = pytz.UTC.localize(completed_at).astimezone(IST)
    else:
        completed_at = completed_at.astimezone(IST)
    gap_expires_at = completed_at + timedelta(seconds=max(0, int(gap_seconds or 0)) if step < 3 else 0)
    result = await db.misc.update_one(
        {"_id": state["_id"], "ist_date": current_ist_date(now),
         "attempt_token": token, "attempt_step": step,
         "completed_step": step - 1},
        {"$set": {"completed_step": new_completed, "completed": step == 3,
                  "last_completed_at": completed_at,
                  "gap_expires_at": gap_expires_at if step < 3 else None,
                  "attempt_token": None, "attempt_step": None}},
    )
    # A repeated/stale callback must not be reported as newly accepted.
    return bool(getattr(result, "modified_count", 0) == 1)

async def save_attempt(token, user_id, group_id, step, delivery_key, mode, now=None):
    """Persist one opaque, user/group/date-bound shortener return attempt."""
    from database.users_chats_db import db
    today = current_ist_date(now)
    key = f"new_shortener_attempt:{token}"
    await db.misc.update_one(
        {"_id": key},
        {"$set": {"token": str(token), "user_id": int(user_id),
                   "group_id": int(group_id), "step": int(step),
                   "delivery_key": str(delivery_key), "mode": str(mode),
                   "ist_date": today, "used": False}},
        upsert=True,
    )
    return key


async def get_attempt(token):
    from database.users_chats_db import db
    return await db.misc.find_one({"_id": f"new_shortener_attempt:{token}"})


async def consume_attempt(token, user_id, group_id, step, now=None):
    """Consume a valid attempt exactly once; return its record or None."""
    from database.users_chats_db import db
    today = current_ist_date(now)
    key = f"new_shortener_attempt:{token}"
    row = await db.misc.find_one({"_id": key, "user_id": int(user_id),
                                   "group_id": int(group_id), "step": int(step),
                                   "ist_date": today, "used": False})
    if not row:
        return None
    result = await db.misc.update_one(
        {"_id": key, "user_id": int(user_id), "group_id": int(group_id),
         "step": int(step), "ist_date": today, "used": False},
        {"$set": {"used": True}},
    )
    return row if getattr(result, "modified_count", 0) == 1 else None


async def find_active_gap_for_user(user_id, now=None):
    """Find an unexpired Step 1/2 access window for a PM request.

    Settings/state are group-scoped, but users often request the next file in
    the bot's private chat. A valid active gap from the originating group must
    also grant that user direct access in PM until the stored expiry.
    """
    from database.users_chats_db import db
    today = current_ist_date(now)
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = pytz.UTC.localize(current).astimezone(IST)
    else:
        current = current.astimezone(IST)
    return await db.misc.find_one({
        "_id": {"$regex": rf"^new_shortener:-?\d+:{int(user_id)}$"},
        "ist_date": today,
        "completed_step": {"$in": [1, 2]},
        "completed": False,
        "gap_expires_at": {"$gt": current},
    })


async def find_latest_state_for_user(user_id, now=None):
    """Find the latest same-day three-step state when a request starts in PM.

    A user's current group may not be known from a private-chat search. This
    lets the handler continue Step 2/3 after a gap expires, or honor Step 3
    completion, without treating PM's group_id=0 as a separate verification.
    """
    from database.users_chats_db import db
    today = current_ist_date(now)
    return await db.misc.find_one(
        {"_id": {"$regex": rf"^new_shortener:-?\d+:{int(user_id)}$"},
         "ist_date": today,
         "completed_step": {"$in": [1, 2, 3]},
         "last_completed_at": {"$exists": True}},
        sort=[("last_completed_at", -1)],
    )


async def cancel_step(user_id, group_id, step, token):
    """Release a claimed step if link generation fails before a URL is sent."""
    from database.users_chats_db import db
    key = state_key(user_id, group_id)
    result = await db.misc.update_one(
        {"_id": key, "attempt_token": token, "attempt_step": int(step)},
        {"$set": {"attempt_token": None, "attempt_step": None}},
    )
    return bool(getattr(result, "modified_count", 0) == 1)
