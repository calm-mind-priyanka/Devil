# Devil modification report

Base: `Devil-main.zip` supplied by the user. IMDX was used as the feature reference.

## Features brought over from IMDX
- Three-step shortener workflow with per-group settings, tutorial links, API/domain inputs, and IST calendar-day state.
- Expanded advanced settings UI, including group-specific force-subscription configuration and the new shortener settings.
- New shortener return-token validation and link/click tracking helpers.
- Updated start/language UI, global language selection, and localized three-step verification prompts.
- Premium-plan configuration persistence and IMDX's additional premium/payment workflow improvements.
- Additional owner/admin utilities and indexing failure notification support.

## Explicitly preserved from Devil
- Devil's original general-data MongoDB connection and collection layout (`DATABASE_URI`, `DATABASE_NAME`). No IMDX general-data secondary/failover wrapper is included.
- Devil's existing movie-index storage/fallback implementation in `database/ia_filterdb.py` (`FILES_DATABASE` with its existing `DATABASE_URI` fallback). IMDX's `DATABASE_URI2` / `MULTIPLE_DB` architecture is not included.
- Devil's existing MongoDB, Telegram bot, payment bot, and shortener API configuration variables and defaults in `info.py`.
- Devil's original poster/metadata implementation (`utils.py`, `plugins/pm_filter.py`, and `plugins/channel.py`). IMDX poster changes were not copied.
- Devil's original Jisshu template colour configuration. IMDX's automatic inline-button colour injection (`button_styles.py` and `sitecustomize.py`) was not copied.
- Existing premium-expiry reminders are retained. The new IMDX verification-recovery/reminder messages and related customer-care callbacks were excluded.

## Validation
- Static compilation and unit tests are run on the packaged source where dependencies available in this environment permit.
- Live Telegram, MongoDB, payment-bot, and shortener-provider integration checks require the user's deployment credentials and staging environment; they are not claimed as completed here.
