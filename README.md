# Tradeveo

Tradeveo is a local chart desk. Upload a chart screenshot and it returns one entry setup: direction, entry, stop, and targets. The read uses only what is visible on the screenshot.

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

For backend tests: `.venv\Scripts\python -m pytest -q`. For frontend tests, typechecking, and build: `npm test`, `npm run typecheck`, `npm run build`.

## Privacy

The API listens on `127.0.0.1:8010` and the development UI listens on `127.0.0.1:5173`. Do not expose either service to a network. Chart screenshots are sent to the provider you choose and are not saved by Tradeveo. The provider key stays in Windows Credential Manager on this PC.
