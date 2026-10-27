# Tradeveo Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a usable local Tradeveo trading journal with SQLite persistence, trade CRUD, accurate currency-aware analytics, calendar, validated CSV exchange, and recoverable backup/restore.

**Architecture:** A Vite React + TypeScript frontend is served locally and talks to a FastAPI backend on 127.0.0.1. FastAPI validates requests and owns SQLite persistence, analytics, CSV, and backups; the database lives below `%LOCALAPPDATA%\Tradeveo`, not in the repository or web build. AI adapters and provider configuration are deliberately deferred to a separately implemented Milestone 2.

**Tech Stack:** Python 3.14 available on the target machine; FastAPI, Pydantic, SQLAlchemy 2, Alembic, pytest, SQLite; Node.js 24 and npm available; React, TypeScript, Vite, Vitest, React Testing Library, Playwright for browser acceptance. Pin mutually compatible dependency versions in the project manifests/lockfiles during the bootstrap task and preserve locks thereafter. Provide a development-mode startup command and a production mode that serves prebuilt frontend assets from FastAPI.

## Global Constraints

- Product name is `Tradeveo`.
- Initial runtime is a local Windows web app, accessible in a browser on the same PC.
- Backend binds to loopback `127.0.0.1` only by default.
- Journal works offline and without AI credentials.
- Persisted financial values use decimal-safe arithmetic (Python `Decimal`; SQLite decimal strings or fixed-scale integer storage), not binary floating point.
- Store timestamps in UTC and render in local time.
- Keep different currencies separate in every aggregate.
- Do not implement broker connections, market feeds, order execution, cloud sync, billing, or AI providers in Milestone 1.
- Keep database files, backups, user CSVs, and any future secrets out of source control and frontend public/build assets.
- Mutation routes must require a browser `Origin` matching the configured local UI origin and reject `Sec-Fetch-Site: cross-site`; accept only loopback Host names (`localhost` or `127.0.0.1`), bind the API to `127.0.0.1`, and configure no permissive CORS. Missing/mismatched Origin or cross-site fetch metadata is rejected.
- `Tradeveo_TIMEZONE` is an IANA timezone setting used for local calendar grouping and defaults to the operating system timezone resolved with the `tzlocal` package; analytics date filters apply to `closed_at` (UTC instant) and journal-list `from`/`to` filters apply to `opened_at`.
- No commit is required by this plan; the shared Git root has unrelated user changes. If a future user explicitly asks to commit, stage only files inside `Tradeveo` after reviewing status.
- Follow the approved design spec: `docs/superpowers/specs/2026-10-21-tradeveo-design.md`.

---

## Project file map

```text
Tradeveo/
  .gitignore
  README.md
  pyproject.toml
  package.json
  package-lock.json
  index.html
  vite.config.ts
  tsconfig.json
  backend/
    app/__init__.py
    app/main.py                 FastAPI app factory, API router mounting, SPA/static fallback
    app/config.py               loopback defaults and local app-data path
    app/database.py             engine/session and migration startup
    app/models.py               SQLAlchemy table definitions
    app/schemas.py              Pydantic input/output schemas
    app/services/trades.py      validation and CRUD service
    app/services/analytics.py   decimal/currency-aware summary and calendar functions
    app/services/csv_io.py      safe preview, mapping, atomic commit, export
    app/services/backups.py     consistent backup, validation and restore
    app/api/trades.py           trade API routes
    app/api/analytics.py        dashboard and calendar routes
    app/api/import_export.py    CSV routes
    app/api/backups.py          backup routes
    migrations/env.py           Alembic migration setup
    migrations/versions/0001_initial.py
    tests/conftest.py
    tests/test_trades.py
    tests/test_analytics.py
    tests/test_csv_io.py
    tests/test_backups.py
  frontend/
    src/main.tsx
    src/App.tsx
    src/styles.css
    src/api/client.ts           typed API client and error conversion
    src/api/types.ts            stable client-side DTOs matching API schemas
    src/components/AppShell.tsx navigation and shell
    src/components/TradeForm.tsx accessible create/edit form
    src/components/TradeTable.tsx searchable/filterable journal table
    src/components/MetricSummary.tsx currency-grouped metrics
    src/components/EquityTimeline.tsx cumulative realized series visualization
    src/components/TradeCalendar.tsx monthly calendar
    src/components/CsvImport.tsx preview/map/validate/confirm workflow
    src/components/BackupControls.tsx backup and restore actions
    src/pages/DashboardPage.tsx
    src/pages/JournalPage.tsx
    src/pages/AnalyticsPage.tsx
    src/pages/ImportExportPage.tsx
    src/pages/SettingsPage.tsx local data path, backup and app info (no AI in M1)
    src/test/setup.ts
    src/**/*.test.tsx
  tests/e2e/journal.spec.ts
  docs/CSV-FORMAT.md
  docs/USER-GUIDE.md
  start.bat
  stop.bat
```

The initial implementation may consolidate only truly trivial files (such as AppShell navigation) but must keep persistence, calculation, CSV, and backup services isolated. Do not build the app as an unrelated multi-user framework. Backend page routes `/`, `/journal`, `/analytics`, `/import-export`, and `/settings` return the same SPA entry document; the frontend router renders the corresponding page and unknown routes show a not-found state.

## Locked data/API interfaces

### Trade JSON

`TradeCreate` accepts exactly these fields (unknown fields rejected):

```json
{
  "instrument": "EURUSD",
  "market": "forex",
  "direction": "long",
  "opened_at": "2026-10-21T09:30:00Z",
  "closed_at": "2026-10-21T10:00:00Z",
  "entry_price": "1.08000",
  "exit_price": "1.08100",
  "size": "100000",
  "multiplier": "1",
  "fees": "2.50",
  "currency": "USD",
  "realized_pnl_override": null,
  "strategy": "London breakout",
  "tags": ["breakout", "london"],
  "notes": "Optional journal note"
}
```

- Decimal inputs/outputs are JSON strings with plain decimal notation and no exponent.
- `market` is one of `equities`, `forex`, `futures`, `options`, `crypto`, `other`, or null.
- `direction` is `long` or `short`.
- `opened_at` is required timezone-aware ISO-8601; `closed_at` is null or timezone-aware ISO-8601.
- `entry_price` and `size` are positive; `exit_price` is positive or null; `multiplier` is positive and defaults to `"1"`; `fees` is non-negative and defaults to `"0"`.
- Currency is three uppercase ASCII letters. This validates representation but does not assert that every possible code is an assigned currency.
- An open position has `closed_at=null` and `exit_price=null`; these must either both be set or both be null.
- `realized_pnl_override` is optional decimal gross realized P&L; fees are subtracted afterward. Override is only valid on a closed trade.
- `tags` is a list of unique trimmed strings (each <= 40 characters; maximum 20 tags); `strategy`, `notes`, and `instrument` have explicit max lengths of 120, 4000, and 40 respectively (strategy and notes may be null). `market` is nullable and, when set, must be one of the listed values.
- `TradeRead` adds `id` (UUID string), `created_at`, `updated_at`, `gross_pnl`, and `net_pnl`; `gross_pnl` and `net_pnl` are null on open trades.
- Create: `POST /api/trades` (201); get: `GET /api/trades/{id}` (200/404); update: `PUT /api/trades/{id}` (200, full replacement); delete: `DELETE /api/trades/{id}` (204/404).
- List: `GET /api/trades?search=&instrument=&market=&direction=&strategy=&from=&to=&status=&currency=&sort=opened_at&order=desc&limit=50&offset=0`, returns `{ "items": TradeRead[], "total": integer, "limit": integer, "offset": integer }`. Clamp `limit` to integer values 1 through 200; allow only `opened_at`, `closed_at`, `instrument`, `currency`, `direction`, and `net_pnl` for sort; allow only `asc`/`desc` order and `open`/`closed` status; return 422 for invalid values; never interpolate SQL identifiers from the request.

### Analytics interfaces

- `GET /api/analytics/summary?from=&to=&instrument=&market=&strategy=` returns `{ "currencies": [{ "currency": "USD", "closed_count": 0, "wins": 0, "losses": 0, "breakeven": 0, "win_rate": "0", "net_pnl": "0", "average_win": null, "average_loss": null, "profit_factor": null }], "equity": [{ "currency": "USD", "at": "2026-10-21T10:00:00Z", "net_pnl": "10", "cumulative_pnl": "10" }], "open_count": 0 }`.
- Group each closed-trade aggregate and each equity series by currency. `win_rate` is decimal fraction in [0,1] as a string and null if closed_count is zero; average win/loss are null if no corresponding trades exist; profit factor is the sum of positive net P&L divided by the absolute sum of negative net P&L, null if total losses are zero. A breakeven is net P&L exactly zero. Sort equity points by close timestamp, then trade UUID for deterministic same-time ordering. `open_count` is calculated after applying date, instrument, market, and strategy filters to positions with `closed_at=null`.
- `GET /api/calendar?year=2026&month=10&currency=USD&instrument=EURUSD&market=forex&strategy=London%20breakout` returns `{ "year": 2026, "month": 10, "days": [{ "date": "2026-10-21", "currency": "USD", "closed_count": 1, "net_pnl": "10" }] }`. A day can have multiple currency rows; never aggregate across currencies. Year/month are required and validated; currency, instrument, market, and strategy filters are optional.

### CSV interfaces

Canonical CSV columns, in order:

`instrument,market,direction,opened_at,closed_at,entry_price,exit_price,size,multiplier,fees,currency,realized_pnl_override,strategy,tags,notes`

- Timestamps are UTC ISO-8601 strings ending `Z`; decimal values are plain decimal; `tags` is a JSON array encoded as CSV text (for example `"[\"breakout\",\"london\"]"`) and parser accepts only a JSON array in this field.
- Preview: `POST /api/import/preview` multipart file + mapping JSON, max file size 10 MiB and max 20,000 rows; returns an opaque preview token bound to an in-memory parsed payload for 15 minutes plus detected headers, row count, valid rows, and row-specific validation errors. Never persist any row during preview. If server restarts or token expires, user previews again.
- Mapping is a JSON object from canonical field name to source column name; missing required mappings are validation errors. Auto-detect exact canonical headers, case-insensitive.
- Commit: `POST /api/import/commit` JSON `{ "preview_token": "...", "confirm_valid_rows": true }`; reject absent confirmation, expired/unknown token, or a preview containing errors unless the request explicitly confirms valid rows only. Import all accepted valid rows in one database transaction; on failure roll back all rows and report no rows created. Return `{ "created": integer, "skipped_invalid": integer }`.
- Export: `GET /api/export.csv` with same supported filters as list. Correctly quote CSV. Prefix spreadsheet-dangerous textual cells beginning (after leading spaces, tabs, CR, or LF) with `=`, `+`, `-`, or `@` using a leading apostrophe. Do not modify typed numeric values or timestamps. Document that protection in CSV-FORMAT.md.

### Backup interfaces

- `POST /api/backups` creates a versioned ZIP archive under `%LOCALAPPDATA%\Tradeveo\backups\tradeveo-<UTC timestamp>-<UUID>.zip` containing `manifest.json` (`format_version`, `schema_version`, `created_at`, `trade_count`) and a consistent SQLite snapshot `journal.sqlite3`; response includes opaque backup id, timestamp, and byte size, never arbitrary filesystem paths supplied by client.
- `GET /api/backups` lists app-managed backup ids and manifest metadata only.
- `POST /api/backups/restore` accepts `{ "backup_id": "<UUID>", "confirm": true }`; reject if false, verify archive member allowlist and size limits, manifest versions, SQLite schema, and `PRAGMA integrity_check`; create an automatic pre-restore ZIP snapshot; atomically replace database with rollback-safe filesystem swap, reconnect engine, and return restored trade count and pre-restore backup id.
- No route accepts caller-selected arbitrary filesystem paths.

## Task 1: Project bootstrap and local runtime contract

**Files:** Create root `.gitignore`, `pyproject.toml`, `package.json`, `package-lock.json`, `index.html`, `vite.config.ts`, `tsconfig.json`; create `backend/app/{__init__.py,main.py,config.py,database.py}` and `backend/tests/conftest.py`; create `frontend/src/{main.tsx,App.tsx,styles.css}`; create `start.bat`, `stop.bat`, `README.md`.

**Interfaces:**
- `create_app(database_url: str | None = None) -> FastAPI` supports isolated tests and runtime.
- `GET /api/health -> { "status": "ok", "schema_version": "0001" }` after migrations.
- Vite serves React in development; production build is served by FastAPI from a dedicated frontend build directory. Backend listens on 127.0.0.1 only.

- [ ] **Step 1: Define failing startup tests** in `backend/tests/test_health.py` for app health, loopback default config, and CORS/origin behavior; add frontend smoke test that renders “Tradeveo”.
- [ ] **Step 2: Run focused tests** with `python -m pytest backend/tests/test_health.py -q` and `npm test -- --run`; expect failure until setup exists.
- [ ] **Step 3: Add pinned dependency manifests** with a compatible FastAPI/Pydantic/SQLAlchemy/Alembic/pytest/tzlocal stack and React/TypeScript/Vite/Vitest/Playwright; create lockfile with `npm install --package-lock-only` and verify `python -m pip install -e ".[dev]"` in the project-local environment.
- [ ] **Step 4: Implement app factory, runtime config, database path, health route, minimal responsive shell, Vite dev proxy, production static mounting, and Windows scripts.** Use `%LOCALAPPDATA%\Tradeveo\journal.sqlite3`; never default database to project root. `start.bat` starts the backend at `127.0.0.1:8000` and frontend dev server at `127.0.0.1:5173` for development; production start serves compiled assets from backend. Do not background a shell child process in tests.
- [ ] **Step 5: Verify bootstrap** with `python -m pytest backend/tests/test_health.py -q`, `npm ci`, `npm test -- --run`, `npm run typecheck`, and `npm run build`; inspect `backend` and `dist` to assert the SQLite file is not in either tree. `pyproject.toml` configures pytest `testpaths = ["backend/tests"]` and the setuptools package root so `python -m pytest -q` imports `backend/app` consistently.

## Task 2: Trade schema, migration, validation, CRUD, and P&L

**Files:** Create `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/trades.py`, `backend/app/api/trades.py`, Alembic migration files, `backend/tests/test_trades.py`; modify database/app wiring.

**Interfaces:** Consume `create_app` and database session from Task 1. Produce all Trade JSON interfaces above, plus pure helpers `calculate_gross_pnl(trade: TradeCreate | TradeRead) -> Decimal | None` and `calculate_net_pnl(...) -> Decimal | None`.

- [ ] **Step 1: Write tests first** for exact Decimal long/short examples, fees, multiplier, override, open-position null P&L, timezone validation, invalid close pairing, immutable UUID, create/list/get/full-update/delete, filters, pagination, deterministic sort, and SQL-injection-shaped sort input rejection.
- [ ] **Step 2: Run `python -m pytest backend/tests/test_trades.py -q` and confirm the new cases fail for missing models/routes.**
- [ ] **Step 3: Implement strict Pydantic DTOs and pure P&L helpers.** Example assertions: long entry `100`, exit `105`, size `2`, multiplier `10`, fees `1` yields gross `100`, net `99`; short entry `105`, exit `100`, size `2`, multiplier `10`, fees `1` yields net `99`; open returns `None`; override `-8` minus fee `1` yields `-9`.
- [ ] **Step 4: Implement SQLAlchemy model with a `TypeDecorator` that stores `Decimal` values as canonical fixed-point TEXT and reconstructs `Decimal` on read (never SQLite REAL); create Alembic migration `0001_initial.py`; ensure migration is explicit and app startup only applies known migrations.**
- [ ] **Step 5: Implement CRUD service and routes using bound parameters and allow-listed sort columns; serialize decimals to plain strings and timestamps as UTC ISO text.**
- [ ] **Step 6: Run focused and full backend tests; verify second app instance against same test DB can read committed trade, proving persistence boundary.**

## Task 3: Currency-separated analytics and calendar

**Files:** Create `backend/app/services/analytics.py`, `backend/app/api/analytics.py`, `backend/tests/test_analytics.py`; modify app router wiring and `backend/app/config.py` for `Tradeveo_TIMEZONE`.

**Interfaces:** Consume validated trade records and filters. Produce summary and calendar response shapes defined above. `build_summary(session, filters) -> SummaryRead`; `build_calendar(session, year, month, currency=None, instrument=None, market=None, strategy=None) -> CalendarRead`.

- [ ] **Step 1: Write tests** covering two currencies, open positions excluded from closed totals, exact win/loss/breakeven counts, win rate, averages, null profit factor when no losses, realized override, date filters using close timestamps, summary and calendar instrument/market/strategy filters, deterministic equity order for equal timestamps, leap-year/month bounds, operating-system timezone/DST conversion, and a day containing multiple currencies.
- [ ] **Step 2: Run focused tests and confirm expected missing endpoint/service failures.**
- [ ] **Step 3: Implement analytics with Decimal accumulation in Python; group all metrics/equity/day totals by currency. Analytics date filters compare `closed_at` UTC instants; calendar converts `closed_at` into the configured `Tradeveo_TIMEZONE` before grouping by date. Define profit factor as positive net-P&L sum divided by absolute negative net-P&L sum, null when there are no losses; average loss is the signed (negative) arithmetic mean of losing net P&Ls.**
- [ ] **Step 4: Implement routes and Pydantic output models.**
- [ ] **Step 5: Verify exact fixture values by hand in assertions and run `python -m pytest backend/tests/test_analytics.py -q` and all backend tests.**

## Task 4: CSV preview, mapping, atomic import, safe export

**Files:** Create `backend/app/services/csv_io.py`, `backend/app/api/import_export.py`, `backend/tests/test_csv_io.py`, `docs/CSV-FORMAT.md`; modify application route wiring.

**Interfaces:** `preview_csv(contents: bytes, mapping: dict[str,str]) -> PreviewRead`; `commit_preview(token: str, confirm_valid_rows: bool) -> ImportResult`; `export_csv(trades: Sequence[TradeRead]) -> bytes`. Routes and DTOs match CSV interfaces above.

- [ ] **Step 1: Write tests** for canonical and case-insensitive auto-mapping, user mapping, malformed encoding/CSV, missing headers, invalid decimals/timestamps, invalid-only file, valid+invalid rows, row indices, 10 MiB/20k row limits, no DB mutation on preview, token expiry/unknown token, confirmation requirement, transactional rollback on simulated DB failure, CSV round-trip of all supported fields, RFC-style quoting, and spreadsheet injection in text fields without corrupting numeric values.
- [ ] **Step 2: Run focused CSV tests and confirm failure before implementation.**
- [ ] **Step 3: Enforce the 10 MiB request limit before fully buffering, including chunked uploads; implement strict bounded CSV parsing and typed mapping; retain at most 10 preview sessions in server memory with 15-minute expiry and random opaque tokens; consume preview tokens once at commit; do not expose private preview payloads in logs.**
- [ ] **Step 4: Implement atomic insert of reviewed valid rows and safe canonical export.**
- [ ] **Step 5: Document canonical CSV and formula mitigation; run `python -m pytest backend/tests/test_csv_io.py -q` plus all backend tests.**

## Task 5: Local snapshot backup and safe restore

**Files:** Create `backend/app/services/backups.py`, `backend/app/api/backups.py`, `backend/tests/test_backups.py`; modify runtime configuration, database lifecycle, and app router wiring.

**Interfaces:** `create_backup() -> BackupRead`; `list_backups() -> list[BackupRead]`; `restore_backup(backup_id: UUID, confirm: bool) -> RestoreRead`. API matches backup interfaces above.

- [ ] **Step 1: Write tests** for a consistent backup containing committed records, listing only managed backups, refusing false confirmation, unknown IDs, corrupted and incompatible SQLite backups, safe pre-restore snapshot, recovery from atomic-swap failure, engine reconnection, and restored row count/data integrity.
- [ ] **Step 2: Run focused tests and confirm missing route/service failures.**
- [ ] **Step 3: Use SQLite backup API into an app-managed temp file, then package it with a versioned JSON manifest in a ZIP archive; fsync where practical; cap archive size at 512 MiB and uncompressed database member at 1 GiB; reject absolute paths, `..`, symlinks, duplicate members, unexpected archive entries, and suspicious compression ratios; validate schema and run `PRAGMA integrity_check` before restore.**
- [ ] **Step 4: Implement confirmed restore: create pre-restore snapshot; close sessions/engine connections and checkpoint/close SQLite WAL state; stage the verified database; atomically replace the DB; reopen engine; restore prior DB if replacement fails. Never accept filesystem paths from clients.**
- [ ] **Step 5: Run backup tests and full backend suite against Windows-compatible temp paths and file locking behavior.**

## Task 6: Journal and trade-entry browser workflows

**Files:** Create typed API client and DTO files; create `TradeForm`, `TradeTable`, `JournalPage`; modify `App.tsx`, `AppShell.tsx`, CSS, and frontend tests.

**Interfaces:** API client exposes `listTrades(filters): Promise<TradeListRead>`, `createTrade(input): Promise<TradeRead>`, `updateTrade(id,input): Promise<TradeRead>`, and `deleteTrade(id): Promise<void>`. `TradeForm` accepts `initialValue?: TradeRead`, `onSave(value)`, and `onCancel()`; `TradeTable` accepts `items`, `onEdit`, `onDelete`.

- [ ] **Step 1: Write component tests** for labeled form validation, decimal text inputs preserving exact values, create/edit submission, server validation display, table search/filter/sort/paging, empty state, loading/error/retry, delete confirmation, and keyboard-only interaction.
- [ ] **Step 2: Run `npm test -- --run` and confirm failures for missing components.**
- [ ] **Step 3: Implement typed API client using fetch, `credentials: "same-origin"`, no provider calls, and readable API error types.**
- [ ] **Step 4: Implement responsive, semantic trade form and table; use text inputs with decimal input hints rather than JS floating-point conversion; confirm before deletion.**
- [ ] **Step 5: Run focused component tests, `npm run typecheck`, and full frontend tests.**

## Task 7: Dashboard, analytics, timeline, calendar

**Files:** Create `MetricSummary`, `EquityTimeline`, `TradeCalendar`, `DashboardPage`, `AnalyticsPage`; modify app navigation and styling; add page tests.

**Interfaces:** Components take typed analytics DTOs. Filters use `{ from?: string; to?: string; instrument?: string; market?: Market | ""; strategy?: string }`. Each currency renders a separate metric group and equity line.

- [ ] **Step 1: Write tests** for summaries per currency, null/zero-data states, open-count distinction, equity series ordering, month navigation, positive/negative/breakeven days across currencies, filter changes updating API arguments, accessible chart summary/table alternative, and responsive no-overflow layout.
- [ ] **Step 2: Run tests and confirm expected failures.**
- [ ] **Step 3: Implement compact dashboard cards and a purpose-built SVG equity timeline with axis labels and accessible textual/table summary. Do not add an unverified chart dependency.**
- [ ] **Step 4: Implement month calendar with local date labels while consuming backend UTC-derived local date aggregation using configured `Tradeveo_TIMEZONE`; add a configuration helper and a test-fixed timezone.**
- [ ] **Step 5: Verify currency cannot be visually or programmatically merged, then run frontend tests and typecheck.**

## Task 8: Import/export and backup user workflows

**Files:** Create `CsvImport.tsx`, `BackupControls.tsx`, `ImportExportPage.tsx`, `SettingsPage.tsx`; modify API client/types and navigation; create browser acceptance tests.

**Interfaces:** `previewImport(file,mapping) -> PreviewRead`; `commitImport(token,confirmValidRows) -> ImportResult`; `downloadExport(filters) -> Blob`; `createBackup() -> BackupRead`; `listBackups() -> BackupRead[]`; `restoreBackup(id,confirm) -> RestoreRead`.

- [ ] **Step 1: Write tests** for CSV header mapping, preview row errors, exact confirmed count, refusal to commit unconfirmed preview, stale-token recovery, download response, backup creation/list/restore, pre-restore display, and cancellation behavior.
- [ ] **Step 2: Run tests and confirm missing workflows fail.**
- [ ] **Step 3: Implement multi-step import UI: choose file, map columns, preview valid/errors, require explicit valid-row confirmation, commit, then refresh list/metrics. Never render uploaded CSV text as HTML.**
- [ ] **Step 4: Implement export download and accessible backup controls; restore requires typed confirmation phrase `RESTORE` plus a native/accessible confirmation dialog and describes the automatic pre-restore snapshot.**
- [ ] **Step 5: Run frontend tests and typecheck, then run backend tests for route integration.**

## Task 9: Windows run guide, end-to-end acceptance, and final review

**Files:** Complete `README.md`, `docs/USER-GUIDE.md`, `start.bat`, `stop.bat`, E2E suite, final `.gitignore`; do not modify files outside project root.

**Interfaces:** A fresh user can follow README exactly to install dependencies, start local dev mode, build production assets, and open the browser URL. Production is a single backend serving prebuilt static assets.

- [ ] **Step 1: Add Playwright as a pinned development dependency, generate its lock entry, and install the Chromium browser only when not already cached; include browser installation in the documented development bootstrap command.**
- [ ] **Step 2: Write E2E scenario** creating two sample trades (one long USD win and one short EUR loss), verify dashboard shows distinct currency sections, edit a note, filter list, export CSV, import it into a clean test database, create backup, delete a trade, restore backup, and verify both records return.
- [ ] **Step 3: Run full verification**: `python -m pytest -q`; `npm test -- --run`; `npm run typecheck`; `npm run build`; E2E against actual local UI. Preserve exit status for any output filtering. Test preview/no-mutation/commit by API and user flow; test backup/restore via the browser interface. Use the configured local test database rather than production user data.
- [ ] **Step 4: Inspect browser console/network errors, responsive width at desktop and 375px mobile, keyboard navigation, focus visibility, reduced-motion setting, API listener loopback address, and frontend build for accidental database/secret files.**
- [ ] **Step 5: Review `git status --short -- Tradeveo` (or the corresponding exact root-relative path) only; leave unrelated parent-root changes untouched. Report any environment/setup blocker; do not call missing external AI integration a pass.**

## Milestone 1 completion gate

Do not call Milestone 1 complete unless all nine acceptance criteria in the approved design spec are checked, including the browser workflow and backup restore test. Any missing requirement is reported as outstanding work, not implied complete. AI-provider connections remain explicitly not implemented in this milestone.
