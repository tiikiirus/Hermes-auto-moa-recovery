@echo off
:: run-moa-tests.bat — focused MoA pytest with Windows-safe temp handling.
:: Works around two environment noises:
::   1. stale pytest-of-tiki/pytest-current symlink (may be Admin-owned) that
::      crashes pytest's sessionfinish cleanup with WinError 5;
::   2. leftover basetemp dirs from previous runs.
:: Strategy: never touch the foreign temp root; use a fresh timestamped
:: --basetemp per run and sweep only our own dirs (best-effort).
setlocal EnableExtensions
set "VENV=%LOCALAPPDATA%\hermes\hermes-agent\.venv\Scripts\python.exe"
set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
set "TS=%DATE:~-4%%DATE:~3,2%%DATE:~0,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "TS=%TS: =0%"
set "BASE=%TEMP%\opencode\ptest-%TS%"

if not exist "%VENV%" (
  echo [moa-tests] FATAL: venv python not found: %VENV%
  exit /b 2
)
if not exist "%REPO%" (
  echo [moa-tests] FATAL: repo not found: %REPO%
  exit /b 2
)
mkdir "%BASE%" >nul 2>&1
pushd "%REPO%" || exit /b 2
"%VENV%" -m pytest tests/agent/test_moa_auto_router.py tests/agent/test_moa_auto_runtime.py tests/agent/test_moa_slot_max_tokens.py tests/agent/test_moa_reasoning_effort.py tests/agent/test_moa_context_max_tokens.py tests/hermes_cli/test_moa_config.py tests/hermes_cli/test_moa_cmd_auto.py tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py -p no:cacheprovider --basetemp="%BASE%" --tb=short -q
set "RC=%ERRORLEVEL%"
popd
rmdir /s /q "%BASE%" >nul 2>&1
exit /b %RC%
