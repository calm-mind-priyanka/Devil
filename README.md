# Devil — IMDX feature integration

This is the Devil project updated using IMDX as the reference implementation, with the exclusions requested by the user applied.

## Preserved configuration and storage

- Keep Devil's existing `BOT_TOKEN`, `API_ID`, `API_HASH`, `PAYMENT_BOT_TOKEN`, `DATABASE_URI`, `DATABASE_NAME`, `FILES_DATABASE`, `COLLECTION_NAME`, and existing shortener API/domain environment variables.
- The original Devil movie-index storage/fallback code is retained. IMDX's separate `DATABASE_URI2` / `MULTIPLE_DB` movie database architecture and its general-data failover wrapper are not included.
- Devil's existing poster/metadata code and Jisshu template colour settings are retained. IMDX's poster changes and automatic inline-button colour feature are excluded.
- No automatic verification-reminder message is sent to users. The existing verification process and existing Premium expiry reminder are retained.

## New IMDX-referenced features

- Three-step shortener workflow, with per-group step domains, API keys, tutorial URLs, step gaps, and IST calendar-day state.
- Expanded advanced settings and group-specific force-subscription settings.
- Shortener return-token validation and link/click tracking.
- Language picker and localized three-step shortener prompts.
- Premium plan persistence and additional payment workflow improvements.
- Additional owner/admin utilities and index-write failure notifications.

## Run checks

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

These checks do not replace live testing with a staging Telegram bot, MongoDB database, and configured shortener providers.
