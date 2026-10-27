# TRYEDVEO

TRYEDVEO is a local-first trading journal and review workspace. Journal records live on this PC; there are no accounts, broker connections, orders, live feeds, cloud sync, or AI providers in the current build.

## Start on Windows

1. Install Python 3.12+ and Node.js 20+.
2. From this folder, create and install the backend environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   ```
3. Install frontend packages once:
   ```powershell
   npm install
   ```
4. Double-click `start.bat` or run it in Explorer/Command Prompt.
5. Wait for the API and Vite windows to become ready, then open <http://127.0.0.1:5173>.

For backend tests: `.venv\Scripts\python -m pytest -q`. For frontend tests/typechecking/build: `npm test`, `npm run typecheck`, `npm run build`.

## Local data and privacy

The default journal database is `%LOCALAPPDATA%\TRYEDVEO\journal.sqlite3` on Windows. The API listens on `127.0.0.1:8010`; the development UI listens on `127.0.0.1:5173`. Do not expose either service to a network. Development API requests are proxied through Vite so browser requests remain same-origin. SQLite stores decimal fields as text to avoid binary floating-point rounding.

Use `TRYEDVEO_UI_ORIGIN` only when intentionally changing the local browser origin. `TRYEDVEO_TIMEZONE` will select the IANA time zone used for calendar grouping when that milestone is implemented.

## Current functionality

- Create, edit, list, filter, and delete individual long/short positions.
- Record open positions without inventing a realized P&L.
- Calculate closed-position gross and net P&L exactly from direction, prices, size, multiplier, fees, or an optional realized-P&L override.
- See an overview of counts, win rate, recent activity, and realized P&L grouped by currency. Different currencies are never combined.
- Keep all trade requests on this PC; no LLM is currently configured or called.

## Planned milestones

1. **Journal core (in progress):** robust SQLite migrations, full dashboard metrics, equity timeline, analytics and calendar filters.
2. **Data portability:** CSV preview/mapping/validation, safe export, atomic import, and validated local backup/restore.
3. **Optional AI analysis:** OpenAI, Anthropic Claude, Ollama, and custom OpenAI-compatible endpoint/model, only after secure Windows Credential Manager storage and explicit outbound-data disclosure are implemented and tested.

No live trading or broker sync is planned for the initial release. AI analysis will be advisory and optional; the journal will remain usable offline.
