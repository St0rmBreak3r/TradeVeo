# Tradeveo — Chart-First Analysis Product Design

**Date:** 2026-10-21  
**Status:** Approved direction for spec drafting; awaiting user review before planning implementation  
**Product:** Tradeveo

## Goal and product priority

Tradeveo's primary purpose is to accept a chart screenshot and return a grounded, structured trading setup or an explicit no-trade result. Trade journaling is secondary and must not dominate the home screen or block the chart-analysis journey. The initial app does not place orders, connect to a broker, or guarantee trading results.

## Confirmed user decisions

- Primary action: copy/paste or upload a chart screenshot for analysis.
- First vision provider: hosted OpenAI.
- First upload types: PNG and JPEG screenshots; no broker/chart integration in v1.
- Signal: structured setup with LONG, SHORT, or NO TRADE; entry area, stop, targets, rationale, and invalidation when supported by the image.
- Time horizon: use timeframe shown on chart; if unreadable, state uncertainty and do not invent one.
- Signal method: chart-structure only. Use visible price action, levels, and legible indicators; do not fabricate exact prices when axis/labels are unreadable. Return NO TRADE / insufficient information for a concrete setup when grounding fails.
- One explicitly requested analysis call per user action; no automatic uploads, scheduled processing, or trade execution.
- Hosted provider: OpenAI first. Keep the architecture provider-adaptable, but Claude, Ollama, and other providers are not required in the first chart-analysis milestone.
- API key setup supports both a user-configured environment variable and Settings entry saved through Windows Credential Manager. Fail closed when the secure store is unavailable; never silently store plaintext.
- The user must see clear disclosure that the image is sent to OpenAI and explicitly choose Analyze before any hosted request.
- App code must not retain chart screenshots after a request; do not save images to SQLite, app-managed files, backups, or frontend local storage.
- OpenAI API data is not used for model training by default, but provider abuse-monitoring or application-state retention can apply. Do not promise provider-side zero retention; disclose the provider's current policies and model limitations.
- Use the visible chart only; optional user-entered context is not part of v1 unless separately approved.

## Primary user flow

1. User opens Tradeveo and sees the chart-analysis workspace first.
2. User pastes a copied screenshot, selects a PNG/JPEG, or drops a screenshot into the upload area.
3. App validates file type, size, and decodability locally and shows a preview before analysis.
4. App displays a concise disclosure: image will be sent to OpenAI, subject to OpenAI API handling/retention; Tradeveo will not save it after analysis.
5. User deliberately presses **Analyze chart**.
6. Local FastAPI validates the request, reads the image in memory, sends it to a configured vision-capable OpenAI model, and validates the structured response.
7. UI renders the direction/setup, grounded levels, reasoning, invalidation, and uncertainty. If no actionable grounded setup can be supported, show **NO TRADE** and the reason.
8. User may clear the image/result or submit another screenshot. No chart history is persisted in v1.

The UI may provide local client-side image preview, but must not initiate upload/analysis until explicit submit. The image must be dropped from application references after clear, response, or failure handling; browser memory lifecycle cannot be guaranteed beyond the page/runtime process.

## Result contract

Backend response schema (Pydantic; API serializes JSON) is equivalent to:

```json
{
  "decision": "NO_TRADE",
  "symbol": null,
  "timeframe": null,
  "setup_type": null,
  "entry": {"low": null, "high": null, "basis": null},
  "stop_loss": {"price": null, "basis": null},
  "targets": [],
  "confidence": "low",
  "confidence_note": "The axis values and candles are too blurred to read reliably.",
  "observations": ["A short-term range is visible, but direction is not clear."],
  "rationale": "Insufficient chart resolution for a price-grounded setup.",
  "invalidation": null,
  "warnings": ["No entry, stop, or target should be inferred from this image."]
}
```

Contract requirements:

- `decision`: enum `LONG`, `SHORT`, `NO_TRADE`.
- `symbol`, `timeframe`, `setup_type`: nullable strings, never hallucinate unreadable values; set `null` when not discernible.
- `entry`: null or `{low: number|null, high: number|null, basis: string|null}`. Prices only when image labels make a level reasonably readable; otherwise entire entry can be null.
- `stop_loss`: null or `{price: number, basis: string}` when grounded and relevant. If no-trade, it can be null.
- `targets`: bounded list of `{price: number, basis: string}`; no target may be outside plausible scale indicated by chart without explanation.
- `confidence`: enum `low`, `medium`, `high`, explicitly model-estimated and not a calibrated probability or success likelihood.
- `confidence_note`: concise plain-language limitation/context.
- `observations`: short bounded list of visible features; separate observations from inference in wording.
- `rationale`: concise reasoning tied to visible structure.
- `invalidation`: null or a condition/level that invalidates the proposed setup.
- `warnings`: bounded list including relevant uncertainty; no guarantees, financial-advice claim, or execution instructions.
- If `decision=NO_TRADE`, entry/stop/targets should be null/empty unless included solely as observed levels and clearly described as non-actionable; v1 should prefer null/empty to avoid accidental signaling.
- Reject unexpected enum values, excessive text/array lengths, non-finite numbers, invalid image-derived level ordering, and malformed/incomplete provider responses. Do not render provider output as HTML.

A returned analysis is informational and inherently uncertain; it is not a recommendation guaranteed to perform. Avoid wording like “will profit,” “sure signal,” or calibrated probability unless independently calibrated by a validated methodology (not in v1).

## Architecture and boundaries

```text
Browser (local React/Vite)
  image selection / paste / preview / explicit consent and submit / result display
       │ same-origin upload after explicit user action
       ▼
FastAPI on loopback
  MIME + byte limit + image decode validation / auth-origin checks / prompt / schema validation
       │ HTTPS outbound only when user selects Analyze
       ▼
OpenAI Responses API + selected vision-capable model
```

- Browser must never hold or send the OpenAI API key to OpenAI directly. The local backend retrieves the key from the Windows credential store or runtime environment, uses it for the request, and never returns it.
- Default backend listener remains loopback. Protect sensitive local operations against browser-origin abuse; CORS is not authentication. Preserve/strengthen current same-origin and loopback Host checks for all mutation/upload endpoints, and use an app-level local authorization token if threat-model work shows origin validation alone is insufficient.
- Set outbound network timeouts and handle connect/read timeouts, rate limiting, provider refusal, invalid model, missing key, and provider 5xx without exposing secrets or raw untrusted provider output.
- Keep provider adapter and analysis orchestration separate from FastAPI route and frontend. First implementation can be OpenAI-only behind an interface for future adapters.
- Use OpenAI Responses API image input (base64 data URL for transient image, no Files API upload) and model-supported Structured Outputs / JSON schema. Do not assume a model ID remains current: make the selected model configurable and document a verified default after checking its official model page during implementation.
- Do not set response application-state persistence when not needed (e.g. use no stored conversation/response state); do not upload to OpenAI Files API. This reduces app-created persistence but does not override provider abuse-monitoring or other platform retention.
- Set server-side image size cap much lower than provider maximum, appropriate for chart screenshots (initial cap 10 MiB; product owner may revise after testing). Validate actual image dimensions and restrict to PNG/JPEG. Reject decompression bombs/extreme dimensions before provider call. Strip metadata where feasible without altering chart pixels materially. Never log image bytes, base64, API keys, prompts containing screenshot data, or unredacted provider errors.
- Close/dispose upload streams promptly; avoid creating temp files. If libraries require in-memory image processing, impose dimensions/pixel caps before decode.
- Credentials: evaluate `keyring` for Windows Credential Manager; verify runtime backend is an expected OS-backed Windows store. If that verification fails, do not save through keyring fallback. Environment variable is explicitly user-provided fallback; settings reports only configured/not-configured state and never reveals environment variable value. Provide clear/replace operations for the secure credential.
- The provider can retain data per its currently published API controls; UI disclosure should link to current official OpenAI API data controls page and be reviewed when model/provider configuration changes.

## API interfaces

### Image analysis

- `POST /api/chart-analysis` — multipart upload field `image`, optional accepted metadata only if separately enabled (not v1), and explicit consent indicator such as `consent=true` in the request. Return typed `ChartAnalysisResult` JSON. Reject missing consent, absent image, unsupported type, oversized payload, corrupt image, dimension/pixel-limit breach, missing provider key, and unavailable provider with actionable HTTP errors.
- Request caps: image <= 10 MiB, supported types PNG/JPEG, pixel count/dimensions limit enforced before provider call, one image per analysis. Server ingress must enforce cap before fully buffering when feasible, including chunked requests.
- Avoid persisting image or analysis record. Response is returned directly to the caller; do not write data to DB, access logs, tracing, or backups.
- `GET /api/ai/status` returns only `{provider: "openai", configured: boolean, model: string|null, credential_source: "credential_manager"|"environment"|"none"}`. Never include key, suffix, or secret-derived fingerprint.
- Settings endpoints for credential create/replace/clear and connection test can be scoped separately; no endpoint returns the key. A connection test must make a real provider request or clearly describe that it only checks local configuration; no fake success.

### Provider configuration

- Settings UI provides provider fixed to OpenAI for milestone 1 of this pivot; model selection only from a vetted allowlist or documented configured model ID; no arbitrary API base URL in first hosted implementation.
- Environment key variable name should be documented (for example `OPENAI_API_KEY`) and read only by local backend process.
- Secure UI save sends secret only to same-origin local API over loopback. Backend immediately hands it to Credential Manager and does not keep it in persistent app settings.
- If both secure-store secret and environment variable exist, clearly define precedence (recommended: explicit environment variable override for development, otherwise Credential Manager) and expose source name only. User may choose one path or the other.

## UI requirements

- Chart-analysis workspace is route `/` and primary home. Header title/subtitle communicates “Chart analysis”; primary CTA is **Analyze chart**.
- File chooser, keyboard-operable paste target, drag-drop, image preview, remove/replace, accepted formats and file-size limit shown before submission.
- Clipboard paste must be triggered by a user action and handle browser permission/unsupported clipboard cases with an upload fallback; no clipboard polling.
- Hosted-send disclosure is shown near Analyze and again before first analysis in a session or each time if required by user policy. Explicit checkbox/button state required; no silent submission.
- Loading/progress state blocks duplicate submit; request timeout/cancel where feasible; user may cancel local wait, understanding an already-transmitted provider request may not be recallable.
- Result layout prioritizes decision badge, structured entry/stop/targets, timeframe/symbol certainty, confidence label and caveat, rationale, observations, invalidation, warnings.
- NO_TRADE and unreadable-data states are prominent, not styled as failure to encourage forced signals.
- All signal values are visible as text for screen readers; charts are not analyzed by screen scraping beyond submitted image pixels.
- Journal navigation moves to secondary navigation; existing records and functions remain accessible and intact unless a separate user-approved removal/migration is requested.

## Security, privacy and risk controls

- Never make an unsolicited provider request; explicit analyze confirmation is mandatory.
- Never call OpenAI from browser code, embed keys in the bundle, store keys in localStorage/sessionStorage/IndexedDB, or log secrets.
- Do not claim a screenshot is never retained globally. Say Tradeveo does not save the image; OpenAI may handle/retain API data under its current published terms/settings.
- Never treat visual analysis as ground truth. A screenshot lacks tick data, spread, order book, event calendar, and unseen context. State these limitations in result and product copy.
- A model “confidence” field is subjective text label only, not calibrated probability. Consider omitting it if evaluation reveals misleading behavior; report that as a design follow-up rather than showing false precision.
- No live orders, trade execution, backtest, profit guarantee, or individualized suitability advice.
- Restrict request and response sizes, bound model output tokens, validate schema, sanitize displayed text, and use safe local errors. Do not allow user-controlled system prompts in v1.
- A local app is not automatically secure against malware or another process running as the Windows user. Credential Manager improves at-rest key handling but not same-user malware defense.

## Verification and acceptance criteria

### Functional/browser

1. Fresh user can open chart-first home and paste/upload a PNG/JPEG; preview and remove/replace work by mouse and keyboard.
2. Invalid extension/content mismatch, corrupt image, oversize file, and excessive dimensions are rejected before any provider call.
3. No provider network call occurs before explicit Analyze; cancel/no consent makes no call.
4. With provider mocked, valid request returns a schema-valid structured signal and renders all result sections; NO_TRADE, null/unreadable levels, refusal, malformed response, provider error, timeout, and rate limit have truthful UI states.
5. A test confirms image bytes are not written to disk, database, backup, or browser persistent storage and are absent from logs.
6. Settings state reports configured source but never returns key; replace/clear works; secure-store unavailable fails closed; environment variable fallback works as documented.
7. Existing journal records remain intact and journal route is still reachable secondary; no forced migration or deletion.
8. Mobile/narrow viewport, clipboard fallback, visible focus, labels, keyboard access, and reduced motion are tested.
9. Actual provider UAT is only declared passed after the user has configured an OpenAI key and a real chart screenshot has been analyzed; mocked adapter tests are not called real-model verification.

### Backend/security

- Unit-test strict Pydantic result schema, numeric finite/range validation, ordering constraints, no-trade conditions, data URL MIME matching, and upload caps.
- API tests cover same-origin guard, absent consent, invalid MIME, forged MIME/content mismatch, corrupt input, high pixel count, oversized/chunked request, concurrency/timeout, provider exception redaction, empty/malformed/refusal response, and provider key non-disclosure.
- Provider adapter test verifies image is supplied as in-memory base64 data URL, uses HTTPS default endpoint and explicit model, requests schema-constrained response, does not use Files API, and does not request stored response state.
- Integration can mock provider locally for deterministic test suite. Never use a real key in tests or store screenshots in repository fixtures without explicit approval.
- Validate local app endpoints remain loopback only and review local-browser DNS-rebinding/origin threats; CORS alone is not sufficient.

## Scope and deferred work

- First chart milestone includes chart-first home, upload/paste preview, OpenAI adapter, structured response, key setup, disclosure, and test coverage.
- Claude, Ollama, generic custom endpoints, strategy configuration, optional symbol/timeframe input, image markup/annotation, multi-image/context bundles, chart history, sharing, broker integration, and order placement are deferred pending separately approved design.
- Existing journal remains as an existing, secondary capability; do not delete user data.

## Research references reviewed for design

- OpenAI [Images and vision](https://developers.openai.com/api/docs/guides/images-vision): image URL/base64/file inputs, formats, detail levels, and image constraints.
- OpenAI [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): JSON Schema-constrained response support; verify model/API compatibility at implementation time.
- OpenAI [Models overview](https://developers.openai.com/api/docs/models): choose a currently supported vision model only after checking per-model feature support.
- OpenAI [Your data](https://developers.openai.com/api/docs/guides/your-data): API training defaults, abuse-monitoring logs, response-state retention, and endpoint-specific storage controls. Review current policy before shipping.
- Python [`keyring`](https://pypi.org/project/keyring/) and its [documentation](https://keyring.readthedocs.io/en/latest/): candidate OS credential store; verify selected Windows backend in actual runtime and fail closed when unsafe.
- Microsoft [Handling passwords](https://learn.microsoft.com/en-us/windows/win32/secbp/handling-passwords) and [Credential APIs](https://learn.microsoft.com/en-us/windows/win32/secauthn/credentials-management): OS credential management recommendations and API details.
- FastAPI [CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/) and CERT/CC [DNS rebinding/CORS note](https://www.kb.cert.org/vuls/id/652514): browser-origin and local-service threat considerations.

## Review checklist

- [x] Product priority is corrected to screenshot-driven chart analysis, not journaling.
- [x] User-confirmed primary input, output, provider, timeframe, and chart-structure limitations are explicit.
- [x] User-approved explicit consent, no image persistence by Tradeveo, API-key handling, and environment fallback are specified.
- [x] Result contract distinguishes observations, inferences, no-trade, and uncalibrated confidence.
- [x] OpenAI retention caveat avoids false no-retention promise.
- [x] Existing journal preservation is explicit; no destructive migration is authorized.
- [x] API limits, security checks, error cases, and browser/provider verification criteria are specified.
- [x] Current external API/provider facts are linked for revalidation at implementation time.
