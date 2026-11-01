@echo off
chcp 65001 >nul
set PYTHONDONTWRITEBYTECODE=1
set LANGSMITH_TRACING=false
set LANGCHAIN_TRACING_V2=false
if defined CAUSALOPS_PYTHON (
  "%CAUSALOPS_PYTHON%" "%~dp0scripts\start_workflow.py" %*
) else if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\start_workflow.py" %*
) else (
  python "%~dp0scripts\start_workflow.py" %*
)
if errorlevel 1 (
  echo Choose the installed Python 3.11 environment with CAUSALOPS_PYTHON. See docs/current/INSTALLATION.md.
  pause
)
