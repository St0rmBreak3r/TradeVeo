@echo off
setlocal
cd /d "%~dp0"
if not exist node_modules\vite\bin\vite.js (
  echo Frontend dependencies are missing. Run: npm install
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Python environment is missing. Create it with: python -m venv .venv
  echo Then install with: .venv\Scripts\python -m pip install -e ".[dev]"
  pause
  exit /b 1
)
start "Tradeveo API" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 --reload"
start "Tradeveo UI" cmd /k "cd /d "%~dp0" && npm run dev"
echo Tradeveo is starting. Open http://127.0.0.1:5173 after both windows are ready.
endlocal
