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
set "SYNC=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\tools\moa_sync.py"
if not exist "%SYNC%" goto :check_failed
where python >nul 2>&1 || goto :check_failed
python "%SYNC%" --check >nul 2>&1
if errorlevel 1 goto :check_failed
if exist "%REPO%\agent\moa_auto_router.py" goto :check_router_ok
echo [auto-moa] HEALTHY-NATIVE (Hermes ^>= 0.21.1 native MoA presets; custom auto-router not ported yet - category routing off)
exit /b 0

:check_router_ok
echo [auto-moa] HEALTHY (custom auto-router active)
exit /b 0

:check_failed
echo [auto-moa] CONFIG DRIFTED or sync tool missing
exit /b 1

:repair
call "%WATCHDOG%"
set "REPAIR_RC=%ERRORLEVEL%"
if not "%REPAIR_RC%"=="0" exit /b %REPAIR_RC%
set "SYNC=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\tools\moa_sync.py"
if not exist "%SYNC%" (
  echo [auto-moa] ERROR: sync tool not found: %SYNC%
  exit /b 1
)
where python >nul 2>&1 || exit /b 1
python "%SYNC%" --sync
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
