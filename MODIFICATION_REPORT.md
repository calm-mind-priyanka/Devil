# Devil / IMDX integration — follow-up implementation

Base project: Devil. Reference project: IMDX-main.zip.

## Fixes in this archive

### Startup and global language
- `/start` reactions are best-effort, so a Telegram reaction failure cannot abort normal startup or deep-link processing.
- First-time private `/start` shows the language picker even if the user-record initialization write fails; the write error is logged instead of blocking the picker.
- The global language callback validates the selected language, persists it before editing the UI, reports a database write failure to the user, and refreshes the home menu after a successful save.
- The language callback handles text and media-caption messages and tolerates `MessageNotModified`.
- Private text searches require a saved global language before starting a movie search; slash commands and deep-links are left to their dedicated handlers.

### Search and filters
- Search-history analytics writes are best-effort and do not stop private or group movie searches when analytics storage fails.
- RapidFuzz is used for title matching rather than the slower FuzzyWuzzy implementation. IMDb spelling lookup is moved off the asyncio event loop and has explicit error handling.
- Search result Language / Quality / Season / Send All controls use the user's saved UI language where those controls are built.
- Language, Quality, and Season picker headings use the language helper, with a safe English fallback when a translation is unavailable.
- Devil's existing primary/fallback movie database design is preserved. Its primary and fallback reads and count operations run concurrently.

## Validation performed
- `python -m compileall -q .`: passed.
- `python -m unittest discover -s tests -v`: 5 existing tests passed.
- Static assertions for the language callback and search changes: passed.

## Not claimed
- Live Telegram `/start` and callback interactions were not run because no bot token/session was available.
- MongoDB read/write behaviour and actual end-to-end search latency were not benchmarked because no live database connection was available.
- All UI strings are not translated into every language; missing strings use the existing English fallback.
- This is a targeted, compatibility-preserving port of selected IMDX behaviour, not a wholesale replacement of Devil's command, storage, or shortener architecture.
