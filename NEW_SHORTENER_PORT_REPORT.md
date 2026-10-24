# New 3-Step Shortener Integration Fix

This patch targets the existing `/settings` -> **NEW 3-STEP SETTINGS** menu. The settings UI and callbacks were already present in the original Devil ZIP and match the IMDX reference, so they were preserved rather than duplicated or replaced by the legacy **Set Shortlink** menu.

## Modified files

- `plugins/commands.py`
  - When `new_shortener_enabled` is ON, the new 3-step state machine is now the exclusive shortener gate. A user inside Gap 1 or Gap 2 is no longer accidentally forced through Devil's legacy shortener; users who have completed Step 3 also bypass that legacy gate.
  - Successful shortener returns pass the configured gap duration to the state store.
  - Gap checking prefers the persisted `gap_expires_at` timestamp and retains a timestamp-based fallback for older records.
  - Existing provider URL generation, tutorial/premium buttons, protection setting, and configured auto-delete behavior remain in place.
- `database/new_shortener.py`
  - Successful Step 1/2 verification persists an explicit `gap_expires_at`; Step 3 marks the daily cycle complete.
  - `begin_step` uses a conditional database update and refuses to overwrite an in-progress attempt, protecting existing links against duplicate/concurrent requests.

## Settings

The existing `New 3-Step Settings` inline menu remains unchanged. It configures `new_shortener_enabled`, the three step URLs/API keys, tutorial URLs, and `new_shortener_gap1` / `new_shortener_gap2`. The old legacy `Set Shortlink` configuration remains separate and is used only when the new system is disabled.

## Validation

- `python -m compileall` passed for the project.
- A simulated database-state test passed for 300-second Gap 1 and Gap 2, the exact expiry boundary, ordered step progression, and duplicate attempt protection.
- ZIP integrity passed.
- Live Telegram callbacks, real MongoDB concurrency, and live shortener API calls could not be exercised in this environment because Pyrogram and production credentials/services are unavailable.
