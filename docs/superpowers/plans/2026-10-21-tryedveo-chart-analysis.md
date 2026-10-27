# TRYEDVEO Chart-First Screenshot Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make screenshot-driven, structured chart analysis TRYEDVEO's primary user journey using an explicitly invoked hosted OpenAI vision request, without deleting existing journal data.

**Architecture:** React accepts PNG/JPEG screenshots by paste, drop, or file picker and renders a local preview; only after explicit user action and disclosure does it upload to a same-origin FastAPI endpoint. The backend validates and bounds image input, uses a provider adapter to call OpenAI's Responses API with an in-memory Base64 image and schema-constrained output, validates the result, and returns it without storing it. API keys come from a verified Windows Credential Manager backend or explicitly configured environment variable; no key or chart is persisted by TRYEDVEO.

**Tech Stack:** Existing React 19 + TypeScript + Vite; FastAPI + Pydantic v2; OpenAI Python SDK (async client); Pillow for safe image decode/dimension checks; `keyring` only if its actual Windows backend can be verified; pytest/FastAPI TestClient; Vitest/Testing Library; existing Playwright for real browser tests. Pin dependencies through `pyproject.toml` and lock files only after checking compatible current versions and official API/model support.

## Global Constraints

- Product name remains `TRYEDVEO`.
- The primary home route `/` is chart analysis; journal stays secondary and existing records must not be deleted or migrated destructively.
- Accept one PNG/JPEG image, maximum 10 MiB, plus configured pixel/dimension bounds; do not save chart data to the journal DB, backups, local storage, IndexedDB, logs, or disk temp files.
- A user must explicitly consent to send the image to OpenAI and press Analyze; no network request before that action.
- A hosted provider may retain API data under current OpenAI policies. Copy must not claim provider-side zero retention; link to current official OpenAI data policy.
- API keys never enter browser storage, JS bundles, source files, logs, responses, or project files. Environment key is read only by local backend; credential-store path must fail closed unless its Windows OS backend is verified.
- Signal decisions are `LONG`, `SHORT`, or `NO_TRADE`; all quoted levels must be grounded in visible readable prices. If unclear, return NO_TRADE/insufficient information rather than infer exact prices.
- Confidence is model-estimated and uncalibrated; do not render as probability or success likelihood.
- No broker, order, execution, profit guarantee, or automatic analysis functionality.
- Bind the API to loopback and preserve/strengthen host/origin guards; CORS alone is not authentication.
- External OpenAI API facts and selected model support must be rechecked against official docs during implementation; never treat mock-provider tests as real-model validation.
- Do not commit unless separately requested. Stage/inspect only project-local files if any later commit request occurs.

---

## Project file map

```text
backend/app/
  main.py                              Existing routes, app factory, same-origin guard, static fallback
  config.py                            Existing local configuration and app-data paths
  services/chart_analysis.py           Image limits/decode, result validation, prompt and orchestration
  services/chart_providers.py          OpenAI adapter and provider protocol
  services/credentials.py              Env/verified Windows credential-store read/write/delete
  schemas/chart_analysis.py             Typed request/result Pydantic models
  api/chart_analysis.py                 Analyze and provider-status/credential routes
  tests/test_chart_analysis.py          Validation, consent, result and storage/security regressions
  tests/test_chart_provider.py          Mock OpenAI adapter contract and redaction tests
  tests/test_credentials.py             Environment precedence, secure-store and fail-closed tests
  tests/test_chart_routes.py            HTTP boundary, origin, status, upload and error tests
frontend/src/
  App.tsx                               Route chart-first home and preserve secondary legacy pages
  components/AppShell.tsx               Rename navigation/brand caption to analysis-first workspace
  api/client.ts                         Chart analysis and AI status/settings calls
  api/types.ts                          Signal result and status DTOs
  pages/ChartAnalysisPage.tsx            Paste/drop/upload preview, consent and request UX
  components/ChartSignalResult.tsx       Accessible typed signal / NO TRADE result panel
  pages/SettingsPage.tsx                 OpenAI key configuration and status, no secret echo
  styles.css                             Responsive image intake and result layout
  App.test.tsx                          Chart workspace and navigation tests
  pages/ChartAnalysisPage.test.tsx       Paste/upload/consent/request/result tests
  pages/SettingsPage.test.tsx            Secret-free settings tests

docs/
  superpowers/specs/2026-10-21-tryedveo-chart-analysis-design.md
  superpowers/plans/2026-10-21-tryedveo-chart-analysis.md
  uat/2026-10-21-tryedveo-uat-report.md   Update with chart-pivot UAT at completion
README.md                                  Correct product-first description and privacy/setup docs
pyproject.toml                             Add pinned-compatible backend dependencies
package-lock.json                           Preserve existing frontend dependency lock
```

## Locked interfaces

### Analysis result schema

- `ChartAnalysisResult`: `{decision: 'LONG'|'SHORT'|'NO_TRADE', symbol: string|null, timeframe: string|null, setup_type: string|null, entry: {low:number|null, high:number|null, basis:string|null}|null, stop_loss:{price:number,basis:string}|null, targets:Array<{price:number,basis:string}>, confidence:'low'|'medium'|'high', confidence_note:string, observations:string[], rationale:string, invalidation:string|null, warnings:string[]}`.
- Pydantic validators: finite price values; bounded field/array lengths; if entry low/high both exist, low <= high; if NO_TRADE, no actionable entry/stop/targets; cap targets and list sizes; trim/disallow empty text where required. Never render result fields as HTML.

### HTTP API

- `POST /api/chart-analysis` multipart `image` plus explicit form field `consent=true`; return `ChartAnalysisResult`. Error responses: 400 missing consent, 413 over-size/pixel bounds, 415 unsupported/mismatched type, 422 corrupt image/schema issue, 503 missing provider configuration, 502 provider refusal/failure with safe generic detail, 504 timeout.
- `GET /api/ai/status` returns only `{provider:'openai', configured:boolean, model:string|null, credential_source:'environment'|'credential_manager'|'none'}`.
- `PUT /api/ai/credential` body `{api_key:string}` over same-origin loopback; saves through verified Credential Manager backend, returns `{configured:true, credential_source:'credential_manager'}` only. If secure backend is absent/unverified, return actionable error and do not save anywhere else.
- `DELETE /api/ai/credential` clears the saved credential and returns only `{configured:boolean}`.
- Environment variable `OPENAI_API_KEY` may configure the local backend. Precedence: explicit environment variable first, otherwise Windows Credential Manager; report source name only.
- First version does not expose arbitrary API base URL or support user-defined prompt.

### Provider protocol

`async def analyze_chart(image_data_url: str, *, model: str, timeout_seconds: float) -> ChartAnalysisResult`

Adapter requirements: use official OpenAI Python async client; HTTPS default endpoint; Responses API vision input; schema-constrained structured response; no Files API; no stored app response state; bounded output tokens; explicit timeout; catch refusal/incomplete/malformed cases; never include API key or screenshot data in logged exceptions.

## Task 1: Dependency/config and schema boundary

**Files:** Modify `pyproject.toml`, `backend/app/config.py`; create `backend/app/schemas/chart_analysis.py`; create schema/config tests.

**Interfaces:** `ChartAnalysisResult`; `openai_api_key() -> tuple[str|None, Literal['environment','credential_manager','none']]`; constants `MAX_CHART_BYTES=10*1024*1024`, `MAX_CHART_PIXELS` (choose and document a defensible value, e.g. 25 million), `MAX_CHART_DIMENSION` (e.g. 10,000).

- [ ] **Step 1: Add failing schema/config tests.** Test enum validation, finite prices, entry ordering, NO_TRADE has no executable levels, bounded arrays/text, environment-key source, no configured-key source, and environment variable precedence. Assert serialized model response contains no secret field.
- [ ] **Step 2: Run `python -m pytest backend/tests/test_chart_analysis.py -q`;** expect import/attribute failures before implementation.
- [ ] **Step 3: Check current official OpenAI SDK / model documentation and compatible package versions.** Add `openai` and Pillow to project dependencies with compatible version bounds. Add `keyring` only after a tested Windows Credential Manager backend choice; document that backend verification is mandatory. Preserve package/lock behavior and do not install system-wide packages.
- [ ] **Step 4: Implement strict Pydantic result schema and configuration access.** Keep environment variable resolution server-side; no helper returns key in API DTO.
- [ ] **Step 5: Run focused schema/config tests and current backend suite.**

## Task 2: Safe credential storage service

**Files:** Create `backend/app/services/credentials.py`, `backend/tests/test_credentials.py`; modify configuration only where required.

**Interfaces:** `credential_store_available() -> bool`; `save_api_key(api_key: SecretStr) -> None`; `read_api_key() -> str|None`; `delete_api_key() -> None`; `resolve_api_key() -> tuple[str|None, Literal['environment','credential_manager','none']]`.

- [ ] **Step 1: Write tests with a fake credential backend.** Verify save/read/delete, env precedence, blank/malformed key rejection, status reveals only configured/source, secure backend unavailable fails closed, and exceptions never include test key value.
- [ ] **Step 2: Run focused tests and verify intended missing-service failures.**
- [ ] **Step 3: Implement verified backend selection.** Detect runtime backend identity; only allow a known Windows Credential Manager backend. If `keyring` selects plaintext/unsupported backend or raises, fail closed. Use a stable service/account name. No file fallback.
- [ ] **Step 4: Implement configuration precedence and secret-safe errors.** Environment variable override takes precedence; settings save edits Credential Manager only. Do not mutate `os.environ` or persist keys in config/database.
- [ ] **Step 5: Run focused and backend tests.** If this environment is not Windows or secure backend cannot be verified, report real credential-storage integration as blocked; mocked behavior does not count as live verification.

## Task 3: Image validation and provider adapter

**Files:** Create `backend/app/services/chart_analysis.py`, `backend/app/services/chart_providers.py`, `backend/tests/test_chart_provider.py`; modify dependency manifest only if required.

**Interfaces:** `validate_chart_image(data: bytes, claimed_type: str) -> tuple[str, str]` returns verified MIME and Base64 data URL; `ChartProvider` protocol; `OpenAIChartProvider.analyze(...) -> ChartAnalysisResult`; `analyze_chart(data, content_type, provider) -> ChartAnalysisResult`.

- [ ] **Step 1: Write image tests.** Test valid small PNG/JPEG, forged MIME/content mismatch, extension irrelevant to backend, corrupt image, zero bytes, >10 MiB, excessive dimensions/pixel count, decompression bomb, metadata handling, and ensure invalid images never invoke provider.
- [ ] **Step 2: Write mock-provider adapter tests.** Assert in-memory Base64 data URL is passed, selected model/schema/timeout are used, no Files API/storage request is made, and NO_TRADE parsed output survives unchanged. Test provider refusal, incomplete/malformed JSON, timeout, 429, 5xx, exceptions containing secrets, and ensure public errors/logs redact key and image.
- [ ] **Step 3: Run focused tests to see validation/adapter tests fail.**
- [ ] **Step 4: Implement bounded image validation using Pillow.** Verify actual file format after decode, cap dimensions/pixels before conversion, reject animation, and do not write temporary image files. Return a MIME-matched Base64 data URL.
- [ ] **Step 5: Implement system instruction and OpenAI adapter.** Instruct the model to distinguish visible observation from inference, return NO_TRADE when labels/context do not support exact levels, never invent symbol/timeframe/price, and keep all output within schema. Use official current Responses API schema mechanism and a model ID checked to support image input + structured outputs; keep model configurable via server config, not arbitrary browser input.
- [ ] **Step 6: Run provider/image tests.** These are mocked; do not report live model accuracy from them.

## Task 4: FastAPI routes and upload boundary

**Files:** Create `backend/app/api/chart_analysis.py`, `backend/tests/test_chart_routes.py`; modify `backend/app/main.py` to include router and initialize status/config services; adjust CORS allowed headers only as needed.

**Interfaces:** `POST /api/chart-analysis`; `GET /api/ai/status`; `PUT /api/ai/credential`; `DELETE /api/ai/credential` exactly as locked above.

- [ ] **Step 1: Write route tests.** Verify missing consent => 400 and provider not called; valid consent invokes mock once; unsupported type => 415; oversized bytes/pixel limits => 413; corrupt image => 422; missing key => 503; provider timeout => 504; other provider failure => safe 502; status never leaks key; credential save/clear never echoes key; cross-origin/invalid host blocked.
- [ ] **Step 2: Run route tests expecting not-found/failure cases.**
- [ ] **Step 3: Implement upload size enforcement.** Read at most limit+1 bytes (or bounded chunks if request stream handler allows); reject chunked over-limit before loading the whole body; close UploadFile in `finally`; prevent request validation errors from logging input content.
- [ ] **Step 4: Implement routes with dependency-injected provider and key resolver.** No screenshot storage, database session, or backup calls. Do not keep preview/request state after response.
- [ ] **Step 5: Run chart route tests and full backend suite.**

## Task 5: Chart-first React intake and result UI

**Files:** Create `frontend/src/pages/ChartAnalysisPage.tsx`, `frontend/src/components/ChartSignalResult.tsx`, and tests; modify `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/styles.css`.

**Interfaces:** `analyzeChart(file: File, consent: true): Promise<ChartAnalysisResult>`; `getAiStatus(): Promise<AiStatus>`; credential save/clear calls; `ChartAnalysisPage` owns transient image state only.

- [ ] **Step 1: Write tests** for initial chart-first route, PNG/JPEG upload preview, file replace/remove, unsupported/oversize rejection, clipboard image paste via user event, upload fallback, disclosure visibility, no API call until Analyze with consent, loading/single submit, result rendering, NO_TRADE prominent state, error retry, and clearing image/result releases object URL.
- [ ] **Step 2: Run frontend tests and confirm missing page/API exports fail.**
- [ ] **Step 3: Implement API DTOs and same-origin fetch client** using FormData, no browser key, no manual Content-Type for multipart. Include explicit consent field.
- [ ] **Step 4: Implement chart input UI** with a keyboard operable paste target and `onPaste` reading only image clipboard items; file input; drag/drop; local image preview using a revocable object URL; no automatic upload or clipboard polling. Accept PNG/JPEG up to 10 MiB; disclose accepted formats/cap.
- [ ] **Step 5: Implement explicit hosted-data disclosure and consent UI.** Keep Analyze disabled until image selected and user has explicitly accepted. UI states that screenshot is sent to OpenAI and provider retention policies may apply. No API call on mere selection/paste/preview.
- [ ] **Step 6: Render validated structured result semantically.** Show decision first, entry/stop/targets with basis, symbol/timeframe when known, rationale, observations, invalidation, warnings, confidence label with “uncalibrated model estimate,” and informational/no-guarantee caveat. Render no HTML from model. NO_TRADE has clear non-actionable styling.
- [ ] **Step 7: Make home route chart-first and move Overview/Journal/Analytics/Calendar/Import to secondary navigation.** Preserve all existing journal data and routes; do not migrate/delete.
- [ ] **Step 8: Run frontend tests, typecheck, and production build.**

## Task 6: OpenAI Settings UX and docs

**Files:** Create `frontend/src/pages/SettingsPage.tsx` and tests; modify `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, API client/types, `README.md`, and `.env.example` only if a safe non-secret template is needed.

**Interfaces:** Settings displays `AiStatus` only; `saveAiCredential(apiKey)` and `clearAiCredential()` return non-secret status.

- [ ] **Step 1: Write tests** for configured/unconfigured source labels, password-field key entry, save/clear, key never rendered after save, no key in storage APIs, environment-source display, secure-store failure message, and provider connection test copy distinction.
- [ ] **Step 2: Run focused tests and confirm fail-before-implementation.**
- [ ] **Step 3: Implement key form with password input** and clear/replace operations. Clear local input after request; do not put secret in route state, Redux/store, URL, persisted browser state, analytics, logs, or error strings. Show configured state/source only.
- [ ] **Step 4: Document OpenAI API setup, environment variable override, Windows Credential Manager save, data disclosure, provider retention caveat, image limits, and unconfigured behavior.** Never put actual key value in docs or `.env.example`.
- [ ] **Step 5: Run Settings/UI suite, typecheck, build.**

## Task 7: Browser UAT and final report

**Files:** Update `docs/uat/2026-10-21-tryedveo-uat-report.md`; use existing browser/e2e tooling without storing real private chart images as fixtures.

- [ ] **Step 1: Verify server processes and ports** before using browser; reuse healthy local app and do not stop unrelated processes.
- [ ] **Step 2: Mock-provider UAT:** open chart-first home; test file picker, paste, preview, consent disclosure, explicit Analyze; capture the mocked structured result; test NO_TRADE and provider failure; test clear/replace and keyboard route. Confirm no provider network call occurs pre-consent.
- [ ] **Step 3: Backend data-boundary UAT:** verify image absent from DB, app files, backups, logs, and browser persistent storage; verify request limits and secret redaction.
- [ ] **Step 4: Settings UAT:** environment-key status without value; Credential Manager save/clear only on a verified supported Windows runtime. In environments without verified Windows Credential Manager, report this capability blocked, never use plaintext fallback.
- [ ] **Step 5: Optional real-provider UAT:** only if user has configured a valid OpenAI key through TRYEDVEO Settings or process environment and is actively supplying a screenshot. Reconfirm outbound image disclosure. Do not ask user to paste key into chat. Record model/provider outcome, not the sensitive image.
- [ ] **Step 6: Regression checks:** `python -m pytest -q`; `npm run typecheck`; `npm test -- --run`; `npm run build`; browser console/network; desktop and 375px viewport; journal routes and existing records remain intact.
- [ ] **Step 7: Update report** to distinguish mocked success from live-provider result, list any checks blocked by credentials/OS environment, and state plainly whether the system now serves the chart-signal purpose.

## Self-review checklist

- [x] Spec sections mapped to Tasks 1–7.
- [x] No task deletes or rewrites existing user journal records.
- [x] Every external provider call is explicitly user-initiated and consent-gated.
- [x] No OpenAI key enters browser storage or is returned by API.
- [x] Real-provider verification is distinguished from deterministic mock tests.
- [x] Credential-store limitations and fail-closed condition are addressed.
- [x] Tests cover invalid image, unsafe output, provider errors, and no-trade cases.
- [x] Scope remains v1 OpenAI chart screenshots; other providers and broker connections are deferred.
