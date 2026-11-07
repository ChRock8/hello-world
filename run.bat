@echo off
REM Double-click to start D3 Helper. First run sets everything up.
cd /d "%~dp0"
if not exist .venv (
  echo Setting up for the first time...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python -m d3helper
pause
