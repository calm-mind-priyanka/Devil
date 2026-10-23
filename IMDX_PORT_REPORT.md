# IMDX spelling/search port report

This build starts from the combined Devil build that already contains the dynamic Premium plan-price buttons and the prior `/start`/language/filter fixes. It ports/adapts IMDX's IMDbKit + RapidFuzz spelling-correction flow rather than replacing Devil's whole filter module.

## Source changes in this build relative to `Devil-IMDX-price-fast-spell-search.zip`

1. `plugins/pm_filter.py`
   - `ai_spell_check` now follows IMDX's ranked IMDb-title loop: request IMDbKit titles, rank with RapidFuzz WRatio, try up to five high-confidence candidates, and accept only if Devil's own movie DB finds a file.
   - IMDbKit's synchronous network call runs in `asyncio.to_thread` with an 8-second timeout so it does not block the bot event loop.
   - Retains a bounded local filename-candidate fallback if IMDbKit returns no usable match.
   - Adds Koyeb log lines for IMDb results/failure, each candidate score, DB confirmation, and no-match outcomes.
   - The call site passes the chat ID to the checker, as IMDX does; Devil's `get_search_results` signature is intentionally used because Devil's database layer differs from IMDX's.

2. `database/ia_filterdb.py`
   - Keeps Devil's separate primary/fallback movie stores.
   - Candidate lookup fetches a bounded number of filenames from both stores concurrently, deduplicates candidates, and reports store failures in logs.
   - Main search remains bounded and concurrent; it does not call `count_documents()` for each search.

## Preserved from the combined build

- Dynamic Premium plan buttons use the `PREMIUM_PLANS` mapping, so labels use the configured plan name and price.
- Previous `/start`, global-language, filter debug/fixes, and other Devil code are retained.

## Validation

- Python `compileall` passed for the extracted project.
- ZIP integrity test passed after packaging.
- This is static validation only: live IMDbKit access, Koyeb behavior, and the configured MongoDB databases were not available for end-to-end testing.
