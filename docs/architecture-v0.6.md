# Toyoko Chan v0.6 Architecture

## Current boundaries

- `app.py`: Flask routes, local-request protection, security headers, instance registration, and startup.
- `runtime.py`: scan orchestration and WebUI handlers. New persistence or provider logic should not be added here.
- `parsing.py`: pure HTML/API parsing and room filters.
- `renderer.py`: Playwright lifecycle and rendered-page acquisition.
- `notifications.py`: notification channels and availability transition state.
- `models.py`: typed runtime configuration and result models.
- `settings.py`: defaults and platform-specific data paths.
- `static/`: browser-side UI and styling.

## Storage migration target

The current atomic JSON files remain compatible for v0.6. A future schema migration should introduce `toyoko.db` with:

- `schema_meta(version, migrated_at)`
- `search_history(id, signature, created_at, payload_json)`
- `availability_events(id, hotel_code, start_date, end_date, appeared_at, disappeared_at, price, room_type, room_count)`
- `hotel_coordinates(hotel_code, latitude, longitude, source, confidence, updated_at)`

Migration must be idempotent: import existing JSON once, verify row counts, then retain the JSON files as rollback backups. Notification credentials must never be placed in SQLite.

## Secret storage target

For macOS, move Bark, Telegram, ServerChan, and SMTP credentials to Keychain. The WebUI should receive only `configured: true/false`; a blank input keeps the existing credential, while an explicit clear action removes it.

## Hotel coordinate target

Ship a versioned coordinate snapshot with releases. Refresh stale or missing hotels incrementally in the background, record the source and confidence, and respect geocoder rate limits. A radius request must never trigger a full synchronous rebuild.

## Internationalization target

Move frontend `UI18N` and backend notification labels into one versioned catalog. CI should verify that every supported language has the same keys and that all primary-language strings include an English counterpart.
