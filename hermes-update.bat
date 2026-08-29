@echo off
:: ============================================================================
::  hermes-update.bat — Safe Hermes update with auto-MoA self-healing
::
::  Usage:
::    hermes-update.bat           Run hermes update, then auto-repair auto-MoA
::    hermes-update.bat --check  Check if auto-MoA is healthy
::    hermes-update.bat --repair Repair auto-MoA without updating Hermes
::
::  Place on PATH (e.g. %LOCALAPPDATA%\hermes\) for `hermes-update` command.
:: ============================================================================
setlocal
set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
set "PATCH=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch"
set "WATCHDOG=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\auto-moa-watchdog.bat"
set "CMD=%~1"
if not defined CMD set "CMD=update"

if /I "%CMD%"=="--check" goto :check
if /I "%CMD%"=="--repair" goto :repair
if /I "%CMD%"=="update" goto :update
echo Unknown command: %CMD%
echo Usage: %~nx0 [--check^|update^|repair]
exit /b 1

:check
if exist "%REPO%\agent\moa_auto_router.py" (
  git -C "%REPO%" apply --reverse --check "%PATCH%" >nul 2>&1
  if not errorlevel 1 (
    echo [auto-moa] HEALTHY
    exit /b 0
  )
)
echo [auto-moa] MISSING or DIVERGED
exit /b 1

:repair
call "%WATCHDOG%"
exit /b %ERRORLEVEL%

:update
echo [auto-moa] running hermes update...
hermes update
set "UPDATE_RC=%ERRORLEVEL%"
echo.
echo [auto-moa] re-applying auto-MoA after update...
call :repair
set "REPAIR_RC=%ERRORLEVEL%"
if %REPAIR_RC% neq 0 (
  echo [auto-moa] WARNING: auto-MoA repair failed. Run: "%WATCHDOG%"
)
exit /b %UPDATE_RC%
