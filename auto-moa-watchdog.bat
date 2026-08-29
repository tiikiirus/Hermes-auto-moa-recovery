@echo off
:: Auto-MoA Watchdog — re-applies auto-moa patch if missing or diverged.
:: Called by cronjob or manually after hermes update.
setlocal
set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
set "PATCH=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch"

if not exist "%PATCH%" (
  echo [watchdog] PATCH NOT FOUND: %PATCH%
  exit /b 1
)

if exist "%REPO%\agent\moa_auto_router.py" (
  git -C "%REPO%" apply --reverse --check "%PATCH%" >nul 2>&1
  if not errorlevel 1 (
    REM Already applied cleanly
    exit /b 0
  )
)

pushd "%REPO%" || exit /b 1
git apply --whitespace=nowarn --check "%PATCH%" >nul 2>&1
if errorlevel 1 (
  echo [watchdog] trying 3-way merge...
  git apply --3way "%PATCH%" >nul 2>&1
  if errorlevel 1 (
    popd
    echo [watchdog] FAILED to apply patch.
    exit /b 1
  )
) else (
  git apply --whitespace=nowarn "%PATCH%" >nul 2>&1
  if errorlevel 1 (
    popd
    echo [watchdog] FAILED to apply patch.
    exit /b 1
  )
)
popd
echo [watchdog] auto-MoA repaired successfully.
exit /b 0
