# TRYEDVEO UAT Report

**Date:** 2026-10-21  
**Environment:** Windows local workspace; React/Vite at `127.0.0.1:5173`, FastAPI at `127.0.0.1:8010`, SQLite on the local machine.  
**Status:** Core journal + analytics/calendar + CSV/backup flows verified; product is not feature-complete overall.

## Executive result

The original journal flow was working, but UAT exposed major unfinished areas: Analytics and Calendar were navigation placeholders, CSV and backup routes did not exist in the running API, and the local API process was stale. Those gaps have now been addressed for the local journal milestone: the two review pages are functional, settings provides CSV and backup workflows, and the current API process responds on the added routes.

This is a usable local trading journal—not a broker, live-trading terminal, or AI-enabled analysis product. OpenAI, Claude, Ollama, and custom LLM configuration and analysis remain unimplemented. Therefore the broader product request is still in staged delivery and is not being reported as “100% complete.”

## User journey exercised

| Journey step | Result | Evidence |
|---|---|---|
| Open local app and load saved journal | Pass | Browser shows existing EURUSD entry and persisted result. |
| Search and status-filter journal | Pass | Browser returned the closed EURUSD row for `EURUSD` + Closed. |
| Review realized analytics | Pass | Summary displayed USD $123.00 and 100% win rate; exact-decimal totals originate from the server. |
| Review monthly calendar | Pass | October 21 cell showed the closed trade result; mobile page width stayed 375px at a 375px viewport. |
| Export CSV through UI | Pass | Browser downloaded `tryedveo-trades.csv`. |
| Preview/import CSV through UI | Pass | One valid row previewed; user confirmation imported it. |
| Create backup through UI | Pass | Backup appeared in the available backup list. |
| Backup/restore lifecycle | Pass (isolated test DB) | API test created a snapshot, deleted the record, restored it, and verified the record and generated pre-restore snapshot. |
| Reopen current API | Pass | The stale identified TRYEDVEO API process was restarted; health, CSV export, backups, and calendar routes returned success. |

## Findings and changes

1. **Analytics/Calendar were non-functional placeholders.** Added real analytics metrics, filters, currency-separated cumulative P&L history, month navigation, local-time-zone day summaries, and instrument/currency filters.
2. **Portability tools were missing.** Added canonical CSV export, UTF-8 CSV preview/validation, confirmed transactional import, plus local versioned ZIP backups and a confirmed restore that creates a pre-restore snapshot.
3. **Formula injection and data round-trip were considered.** Export protects formula-leading text cells; tags round-trip as JSON arrays in the CSV field. CSV accepts canonical headers and reports row-level validation errors.
4. **Live service did not match source.** The API already listening at 8010 was stale and returned 404 for new routes. After verifying its command line belonged to TRYEDVEO, restarted that process and confirmed the current API served the new endpoints.
5. **Windows SQLite handle behavior surfaced in backup verification.** A file handle remained open in the backup temporary directory; connection cleanup was corrected, and the backup/restore journey passed afterward.

## Verification performed

- `python -m pytest -q`: **9 passed** (one Starlette/httpx deprecation warning remains).
- `npm run typecheck`: **passed**.
- `npm test -- --run`: **6 passed**.
- `npm run build`: **passed**.
- Browser automation: analytics and calendar rendered with real API data; settings export produced a download; import preview/confirmation and backup creation worked; 375px viewport had no horizontal document overflow; no page/console errors or HTTP errors in the final run.
- Isolated backend data-portability journey: CSV export → preview → commit → backup → delete → restore passed with two records restored. The user’s default journal was not used for this destructive test.

## Known limitations / release blockers

- **AI integration is not implemented:** no provider settings, secure key storage, connection checks, or analysis panels for OpenAI, Anthropic Claude, Ollama, or custom OpenAI-compatible endpoints. This was explicitly identified in project scope as a later milestone.
- **CSV mapping is not in the current UI.** The backend currently imports the canonical TRYEDVEO column format; arbitrary broker CSV column mapping is still outstanding.
- **Calendar filters currently expose instrument and currency only.** Backend also supports market and strategy filters, but the UI does not surface them yet.
- **Database schema uses `create_all` and a reported schema version, not a real Alembic migration chain.** Robust versioned migrations are still needed before distributing upgrades to a real user database.
- **Restore safety needs additional fault-injection coverage.** The happy path and confirmation guard pass; simulate process failure/restart during replacement and test malformed ZIP, incompatible schema, and oversized/compression-abuse archives before calling restore hardened.
- **Lifecycle browser testing:** earlier UAT verified create/edit/close and showed `$123.00`, but the final regression run focused on analytics, calendar, search/filter, and portability rather than repeating every create/edit/delete action in the browser.
- **No packaged installer or end-user backup/restore guide has been UATed.** Current validated interface is the local development workflow.

## Recommended next milestones

1. Add robust Alembic migration flow, startup diagnostics, and a Windows-safe packaged launch/upgrade procedure.
2. Implement CSV column mapping, richer invalid-row preview, empty-file and malformed-file UX, and import limits enforced while streaming.
3. Harden backup restore with archive limits, atomic swap/rollback fault injection, and a user-facing restore drill.
4. Complete an end-to-end fresh-start browser journey including create open trade → edit/close → analytics/calendar change → delete confirmation → restart persistence.
5. Implement optional AI as a separate milestone: first choose the credential-store approach, then add OpenAI, Anthropic, Ollama, and custom OpenAI-compatible adapters with explicit data disclosure and no plaintext key fallback. Verify against actual configured provider credentials / local Ollama before calling it functional.
6. Add accessibility review, test the keyboard-only flow, and verify app behavior fully offline (including removing the external Google Fonts dependency).

## UAT conclusion

TRYEDVEO now serves the basic local-journal purpose with working review and data portability functions, and the tested code passes current typecheck, unit, build, and backend suite. It is suitable for continued local milestone work, but should not be marketed as a complete trading platform or as having AI support until the outstanding items above are implemented and independently verified.
