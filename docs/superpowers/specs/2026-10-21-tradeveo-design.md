# Tradeveo — Product and Architecture Design

**Date:** 2026-10-21  
**Status:** Approved by user  
**Product name:** Tradeveo

## Product goal

Tradeveo is a private, local-first trading journal and review workspace for an individual trader. Its first release supports manual trade entry and CSV exchange, reliable trade history, calendar and performance review, local backups, and optional user-directed AI analysis. It does not place orders or claim to be an investment adviser.

## Confirmed user decisions

- Product direction: trading journal and analytics, inspired by (not a literal replica of) TradVio.
- Initial runtime: local web application on Windows, accessible in a browser on the same PC.
- Initial markets: all markets represented by a position record; manual entry and CSV import/export.
- Initial trading actions: journal and analysis only; no paper or live broker execution.
- Persistence: local SQLite managed by a local API service.
- Frontend/backend: React + TypeScript frontend and local Python API.
- Custom LLM support: native OpenAI, Anthropic Claude, and Ollama providers, plus custom OpenAI-compatible endpoint/model. Arbitrary HTTP template authoring is not in the first release.
- AI calls: explicit user action; never needed to use the journal; explain when trade summaries leave the PC for a hosted provider.
- AI credentials: Windows Credential Manager via an OS credential-store integration, not localStorage, browser state, or a plaintext settings file. If secure storage is unavailable, do not silently persist a key; tell the user and allow other app features to continue.
- Analytics: do not add different currencies together; show separate currency totals unless the user explicitly converts them in a later feature.
- User-approved first-release scope: dashboard; trade create/edit/delete/list/filter; calendar and performance breakdowns; CSV import with mapping and validation plus export; local backup/restore; AI provider settings and analysis.
- Explicitly out of scope for first release: broker synchronization, live market feeds, order placement, multi-user accounts, cloud synchronization, billing, and automatic currency conversion.
- Visual direction: a distinctive, readable instrument-panel journal, warm white workspace, dark ink text, restrained teal positive and rust negative accents, compact monospaced data labels, and a timeline/equity curve as a signature. Avoid copying TradVio's design or creating a noisy terminal aesthetic. Support keyboard focus and reduced motion.

## Delivery strategy

Build and verify the product incrementally. The initial implementation plan should deliver **Milestone 1: local journal core** as an independently usable vertical slice. It includes the local app shell, SQLite persistence, trade CRUD, core P&L calculations, useful dashboard/analytics, calendar, validated CSV round-trip, and backup/restore. **Milestone 2: AI integration** adds secure provider configuration, connection tests, and explicitly invoked analysis. Provider calls must not be represented as functional until tested against real configured credentials or a reachable Ollama server. Additional broker, cloud, and live-market features require separately reviewed designs.

Each milestone must be demonstrable through the actual local browser UI, not only unit tests or a successful build. Do not imply the whole product is complete until every in-scope milestone is implemented and verified.

## Architecture

```text
Browser on this PC
  React + TypeScript + Vite
          │ same-origin/local API
          ▼
FastAPI on loopback only
  validation · analytics · CSV · backup · optional AI adapters
          │
          ├── SQLite database under the user's local application-data directory
          ├── Windows Credential Manager for provider secrets
          └── Explicit outbound requests to the selected AI provider only
```

- The local API binds to loopback (127.0.0.1), not all network interfaces, by default.
- The browser never connects directly to AI providers and never receives provider secrets.
- SQLite is the source of truth. Store timestamps in UTC and display in the user's local time zone. Store money/price/size values in decimal-safe representation; do not use binary floating-point for persisted financial amounts.
- Use a schema migration mechanism from the first database version.
- The app remains fully useful when internet access and every AI provider are unavailable.
- Use explicit, narrow request validation, same-origin protections for mutations, and no wildcard CORS.
- Local database/backups must not be placed in public frontend build output or committed to source control.

## Trade record and calculations

One row represents one position; it may be open or closed. Fields:

- `id`: generated stable identifier.
- `instrument`: required, user-visible market symbol/name.
- `market`: optional category (for example equities, FX, futures, options, crypto, other).
- `direction`: `long` or `short`.
- `opened_at`: required timestamp.
- `closed_at`: optional timestamp; its presence means closed.
- `entry_price`: required decimal.
- `exit_price`: optional decimal.
- `size`: required positive decimal.
- `multiplier`: positive decimal, default 1.
- `fees`: non-negative decimal, default 0.
- `currency`: required ISO-style currency code chosen by the user.
- `realized_pnl_override`: optional decimal for products/records that cannot be faithfully represented by a simple round trip.
- `strategy`, `tags`, `notes`: optional user journaling fields.
- `created_at`, `updated_at`: UTC timestamps.

For a closed position with no override, gross P&L is `(exit_price - entry_price) × direction_sign × size × multiplier`, where `direction_sign` is `+1` for long and `-1` for short. Net P&L is gross P&L minus fees. When `realized_pnl_override` is set, net P&L equals the override minus fees. Open positions have no realized P&L and are excluded from closed-trade win/loss totals. Validate exit time is not before entry time, prices are positive where supplied, and size/multiplier are positive. Use decimal-safe arithmetic and round only for display or export formatting.

Core analytics: closed trade count, wins, losses, breakeven count, win rate, net P&L, average win/loss, profit factor (explicitly undefined when there are no losses), and cumulative realized equity series. All aggregates are filtered by date/instrument/strategy where applicable and grouped by currency. Do not imply return-on-capital or risk-adjusted measures without a defined capital/risk input.

## User-facing areas

- **Dashboard:** date range and currency-aware performance summary, recent trades, cumulative realized P&L visualization, and links to add/import trades.
- **Journal:** searchable/filterable/sortable trade list and accessible create/edit/delete flow. Confirm destructive deletion.
- **Calendar:** local-time-zone monthly calendar showing closed-trade net P&L by day and trade count, grouped by currency.
- **Analytics:** date, instrument, market, and strategy filters; clear zero-data, open-trade, and undefined-metric states.
- **Import:** upload a CSV; preview rows; map recognized or custom source headings to canonical fields; validate required fields and row-level errors; show the exact create count; require confirmation; do not silently discard invalid rows. Import must be atomic for the confirmed set, with row-specific errors and no misleading success report.
- **Export:** export selected/all journal records to a documented canonical CSV format. Escape CSV correctly and prevent spreadsheet-formula execution from user-provided text fields.
- **Backup:** create a timestamped local backup containing a consistent SQLite snapshot and versioned metadata. Restore only after a clear confirmation and validation; retain/offer a pre-restore backup so a mistaken restore is recoverable.
- **AI settings and analysis (Milestone 2):** provider selection, base URL/model, connection test, saved-secret status without displaying the secret, explicit test/clear/replace actions, clear local-vs-hosted data disclosure, and a user-triggered analysis panel. Analysis is advisory and cannot place or simulate orders.

## API boundaries (initial shape)

Exact schemas and route names are locked in the Milestone 1 plan and tests; the API must provide equivalent functionality to:

- `GET /api/health` — local service readiness and schema version, no private trade data.
- `GET /api/trades` — paginated/filterable list.
- `POST /api/trades` — validate and create a trade.
- `GET /api/trades/{id}` — retrieve a trade.
- `PUT /api/trades/{id}` — validate and update a trade.
- `DELETE /api/trades/{id}` — delete after UI confirmation.
- `GET /api/analytics/summary` — filtered, currency-grouped metrics and cumulative series.
- `GET /api/calendar` — filtered day totals and counts.
- `POST /api/import/preview` — parse/map/validate uploaded CSV without changing the database.
- `POST /api/import/commit` — commit a user-confirmed valid import atomically.
- `GET /api/export.csv` — downloadable canonical CSV for requested filters.
- `POST /api/backups` and `POST /api/backups/restore` — local backup and confirmed restore.
- Milestone 2 adds provider configuration/test and a user-triggered analysis endpoint; secrets are handled server-side and never returned in responses.

## Error handling and privacy

- Return actionable validation errors with field/row references; do not claim persistence when a transaction rolls back.
- Never log provider API keys, prompts containing full journals, or unredacted provider errors that might include secrets.
- Show provider/network errors and let users retry; do not fabricate analysis or silently fall back to a different provider.
- Before hosted analysis, identify the selected provider and the categories of trade data being sent, and require an explicit analyze action. Ollama is local only when its configured endpoint resolves to the local machine; show the endpoint.
- Restrict supported URL schemes and validate configured endpoints. Treat custom endpoints as untrusted; never expose provider credentials to the browser.
- Make clear that AI output may be inaccurate and is for journal review, not financial advice.

## Verification and acceptance criteria

### Milestone 1 acceptance

1. From the documented Windows setup/start command, a user can open Tradeveo in a browser and create a local journal without accounts or internet access.
2. Trade create/read/update/delete works across app restarts with validation and clear errors.
3. Hand-calculated long and short test examples (including fees, multipliers, override, open positions, and multiple currencies) match server analytics exactly using decimal-safe math.
4. Dashboard, journal filters, calendar, and analytics reflect the same persisted records; no cross-currency summing occurs.
5. CSV preview catches malformed/missing data before mutation; confirmed import commits only valid reviewed rows atomically; export can be re-imported without loss of supported journal fields; spreadsheet-formula content is safe on export.
6. Backup can be restored to reproduce prior records; invalid backup or cancelled restore does not destroy existing data.
7. No database, secret, or journal export is included in frontend/public assets or source control.
8. UI is usable at desktop and narrow/mobile widths, by keyboard, has visible focus, semantic labels and table/form structure, and respects reduced-motion preference.
9. Backend tests, frontend typecheck/tests, and production build pass; exercise trade import/export/backup through the browser interface.

### Milestone 2 acceptance

1. Provider secrets are persisted only through the OS credential store; absence of secure storage fails safely without plaintext fallback.
2. OpenAI, Anthropic Claude, Ollama, and custom OpenAI-compatible provider configuration is supported by distinct adapters, with tested current request/response contracts.
3. Connection testing produces truthful success/error state and never leaks secrets in API responses, logs, or UI.
4. User-triggered analysis works with configured reachable services, clearly discloses outbound data, and fails usefully when credentials/service are missing.
5. All core journal flows remain operational with AI unconfigured, offline, or failing.

## Risks and explicit limitations

- “All features” cannot be guaranteed by reverse engineering a website from a public landing page or minified assets. This is an original local-first product informed by the user's approved goals, not a claim of feature parity with a private authenticated TradVio application.
- User-specific broker CSV formats vary. CSV mapping and a canonical template address this first; broker APIs and preset-specific formats are follow-on work.
- A simple position formula cannot represent every derivatives strategy, partial close, funding payment, or tax lot. Manual realized-P&L override covers initial exceptions; multi-leg/partial-fill accounting needs a separate design.
- Hosted AI requires the user's own valid credentials and network access. No provider or credential is provisioned by this project.
- A local app is not automatically private if the computer or its user account is compromised; Windows account/device security and backups remain the user's responsibility.
- Current provider API contracts and exact dependency versions must be checked against official documentation when implementing the AI milestone.

## Review checklist

- [x] Product goal and intended audience are explicit.
- [x] Initial platform and architecture match the user's decisions.
- [x] First-release scope and exclusions are explicit.
- [x] P&L definition and currency behavior are unambiguous.
- [x] AI provider coverage and secret/data flow are explicit.
- [x] Incremental deliverables and verifiable acceptance criteria are defined.
- [x] Scope limitations are stated instead of promising literal 100% parity.
