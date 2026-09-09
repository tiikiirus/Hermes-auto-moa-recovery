@echo off
:: Auto-MoA Watchdog — re-applies auto-moa patch if missing or diverged.
:: Called by cronjob or manually after hermes update.
setlocal EnableDelayedExpansion
set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
set "PATCH=%USERPROFILE%\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch"
if exist "%~dp0auto-moa-current.patch" set "PATCH=%~dp0auto-moa-current.patch"

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
if not errorlevel 1 (
  git apply --whitespace=nowarn "%PATCH%" >nul 2>&1
  if errorlevel 1 (
    popd
    echo [watchdog] FAILED to apply patch.
    exit /b 1
  )
  goto :verify
)
echo [watchdog] full apply failed; trying per-file salvage...
set "FAIL="
for %%F in (
  agent/moa_loop.py
  agent/moa_trace.py
  agent/turn_request_assembly.py
  hermes_cli/moa_cmd.py
  hermes_cli/moa_config.py
  agent/moa_auto_router.py
  tests/agent/test_moa_auto_router.py
  tests/agent/test_moa_auto_runtime.py
  tests/hermes_cli/test_moa_cmd_auto.py
) do (
  git apply --reverse --check --include="%%F" "%PATCH%" >nul 2>&1
  if not errorlevel 1 (
    echo [watchdog] already applied: %%F
  ) else (
    git apply --whitespace=nowarn --check --include="%%F" "%PATCH%" >nul 2>&1
    if not errorlevel 1 (
      git apply --whitespace=nowarn --include="%%F" "%PATCH%" >nul 2>&1
      if errorlevel 1 (
        echo [watchdog] FAILED: %%F
        set "FAIL=!FAIL! %%F"
      ) else (
        echo [watchdog] applied: %%F
      )
    ) else (
      git apply --3way --include="%%F" "%PATCH%" >nul 2>&1
      if errorlevel 1 (
        echo [watchdog] FAILED: %%F
        set "FAIL=!FAIL! %%F"
      ) else (
        echo [watchdog] applied ^(3-way^): %%F
      )
    )
  )
)
if defined FAIL (
  popd
  echo [watchdog] FAILED to apply files:%FAIL%
  exit /b 1
)
:verify
if not exist "%REPO%\agent\moa_auto_router.py" (
  popd
  echo [watchdog] FAILED: router still missing after apply.
  exit /b 1
)
REM Refresh the post-merge hook snapshot so manual `git pull` repairs with the current patch.
if exist "%REPO%\.git\hooks\auto-moa" copy /y "%PATCH%" "%REPO%\.git\hooks\auto-moa\auto-moa-current.patch" >nul 2>&1
popd
echo [watchdog] auto-MoA repaired successfully.
exit /b 0
