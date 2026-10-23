# Devil / IMDX integration review — follow-up fix

Base: original Devil project. IMDX is the reference.

## Follow-up issues identified in the previously supplied ZIP

- `plugins/pm_filter.py` had not been merged from IMDX; the previous archive retained Devil's older PM-search path. This meant the global-language onboarding behaviour from IMDX was missing in PM searches.
- The `/start` handler attempted a Telegram message reaction before processing any payload. If Telegram rejected that reaction, the handler could stop before handling a normal start, file deep-link, or shortener return.

## Changes in this follow-up archive

- Added the global language-selection gate to ordinary private-message searches, using the existing `language.py` and Devil database facade. Commands and `/start` deep-links remain handled by their dedicated handlers.
- Made the `/start` reaction best-effort, so reaction failures cannot block the start/verification/file-delivery flow.
- Kept Devil's original database and MongoDB configuration. No second-database/failover architecture was added.
- Kept Devil's original poster implementation and colour configuration; no automatic verification-reminder messages were added.

## Checks

- `python -m compileall -q .`: passed.
- `python -m unittest discover -s tests -v`: 5 tests passed.
- Live Telegram, MongoDB, and third-party shortener round trips were not available in this environment, so the end-to-end runtime fix must still be verified against a staging bot.

## Important scope note

This follow-up fixes the confirmed `/start` reaction-abort risk and PM global-language onboarding gap. It does not claim that every IMDX performance/search implementation detail has been ported; `plugins/pm_filter.py` still differs from IMDX in other areas, including IMDX-specific spelling-correction and search enhancements. The three-step shortener flow remains separate from Devil's legacy shortener flow.
