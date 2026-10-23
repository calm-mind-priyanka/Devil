import unittest
from datetime import datetime
import pytz
from database.new_shortener import current_ist_date

class CalendarBoundaryTests(unittest.TestCase):
    def test_utc_timestamp_maps_to_ist_day(self):
        # 18:30 UTC is exactly midnight on the following IST calendar day.
        utc = pytz.UTC.localize(datetime(2026, 1, 1, 18, 30, 0))
        self.assertEqual(current_ist_date(utc), "2026-01-02")

    def test_just_before_midnight_ist(self):
        ist = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 1, 1, 23, 59, 59))
        self.assertEqual(current_ist_date(ist), "2026-01-01")

    def test_exact_midnight_ist(self):
        ist = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 1, 2, 0, 0, 0))
        self.assertEqual(current_ist_date(ist), "2026-01-02")

if __name__ == "__main__":
    unittest.main()

class _FakeUpdateResult:
    def __init__(self, modified_count=1):
        self.modified_count = modified_count

class _FakeMisc:
    def __init__(self):
        self.rows = {}
    async def find_one(self, query):
        return self.rows.get(query.get("_id"))
    async def update_one(self, query, update, upsert=False):
        key = query.get("_id")
        row = self.rows.get(key)
        conditions_match = row is not None
        for field in ("ist_date", "attempt_token", "attempt_step", "completed_step"):
            if field in query and (not row or row.get(field) != query[field]):
                conditions_match = False
        if not conditions_match and not upsert:
            return _FakeUpdateResult(0)
        if row is None:
            row = {"_id": key}
            self.rows[key] = row
        row.update(update.get("$set", {}))
        return _FakeUpdateResult(1)

class _FakeDB:
    def __init__(self):
        self.misc = _FakeMisc()

class ShortenerStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import patch
        self.db = _FakeDB()
        import sys, types
        fake_module = types.ModuleType("database.users_chats_db")
        fake_module.db = self.db
        self.patch = patch.dict(sys.modules, {"database.users_chats_db": fake_module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def test_steps_must_be_ordered_and_group_user_scoped(self):
        from database.new_shortener import begin_step, accept_step, get_state
        now = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 2, 3, 12, 0))
        self.assertIsNone(await begin_step(10, -1001, 2, now))
        token1 = await begin_step(10, -1001, 1, now)
        self.assertTrue(token1)
        self.assertFalse(await accept_step(10, -1001, 2, token1, now=now))
        self.assertFalse(await accept_step(11, -1001, 1, token1, now=now))
        self.assertTrue(await accept_step(10, -1001, 1, token1, now=now))
        token2 = await begin_step(10, -1001, 2, now)
        self.assertTrue(token2)
        self.assertTrue(await accept_step(10, -1001, 2, token2, now=now))
        token3 = await begin_step(10, -1001, 3, now)
        self.assertTrue(await accept_step(10, -1001, 3, token3, now=now))
        self.assertTrue((await get_state(10, -1001, now))["completed"])
        self.assertEqual((await get_state(10, -1002, now))["completed_step"], 0)
        self.assertEqual((await get_state(11, -1001, now))["completed_step"], 0)

    async def test_old_day_progress_is_persistently_reset(self):
        from database.new_shortener import begin_step, accept_step, get_state
        ist = pytz.timezone("Asia/Kolkata")
        day1 = ist.localize(datetime(2026, 2, 3, 23, 59, 59))
        day2 = ist.localize(datetime(2026, 2, 4, 0, 0, 0))
        token = await begin_step(10, -1001, 1, day1)
        self.assertTrue(await accept_step(10, -1001, 1, token, now=day1))
        self.assertEqual((await get_state(10, -1001, day1))["completed_step"], 1)
        # A prior-day token cannot restore progress after the date boundary.
        self.assertFalse(await accept_step(10, -1001, 2, token, now=day2))
        state = await get_state(10, -1001, day2)
        self.assertEqual(state["completed_step"], 0)
        self.assertEqual(state["ist_date"], "2026-02-04")
