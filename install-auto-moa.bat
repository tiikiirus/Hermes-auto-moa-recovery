@echo off
:: ============================================================================
::  Auto-MoA Self-Healing Installer
::  Makes auto-MoA survive `hermes update` and work across all profiles.
::
::  Usage: install-auto-moa.bat [profile=fantrax]
::
::  What it does:
::    1. Applies auto-moa-current.patch to hermes-agent (if not already applied)
::    2. Installs git post-merge hook (for manual git pull)
::    3. Verifies auto-moa-watchdog.bat repair script
::    4. Creates hermes-update.bat wrapper (safe update)
::    5. Installs cronjob watchdog (safety net, requires Admin)
::    6. Syncs the canonical MoA graph into all profiles (best-effort)
::
::  After install:
::    hermes-update         -> safe update with auto-repair
::    hermes-update --check -> check auto-MoA health
::    hermes-update --repair-> repair auto-MoA without updating
:: ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=fantrax"
set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
if exist "%~dp0auto-moa-current.patch" (
  set "RECOVERY=%~dp0"
  set "RECOVERY=!RECOVERY:~0,-1!"
) else (
  set "RECOVERY=%USERPROFILE%\Documents\Hermes-auto-moa-recovery"
)
set "PATCH=%RECOVERY%\auto-moa-current.patch"
set "HOOK_SRC=%RECOVERY%\auto-moa-hook.sh"
set "WATCHDOG=%RECOVERY%\auto-moa-watchdog.bat"
set "HERMES_UPDATE=%LOCALAPPDATA%\hermes\bin\hermes-update.bat"

echo ===========================================================================
echo  Auto-MoA Self-Healing Installer
echo  Profile: %PROFILE%
echo  Repo:    %REPO%
echo ============================================================================

:: --- Pre-flight checks ------------------------------------------------------
where git >nul 2>&1 || ( echo [FATAL] git not on PATH. & exit /b 1 )
if not exist "%REPO%" ( echo [FATAL] repo not found: %REPO% & exit /b 1 )
if not exist "%PATCH%" ( echo [FATAL] patch not found: %PATCH% & exit /b 1 )
where python >nul 2>&1 || echo [WARN] python not on PATH: --check/--repair/profile-sync will fail until installed.
python -c "import yaml" >nul 2>&1 || echo [WARN] PyYAML missing: tools/moa_sync.py needs it.
where hermes >nul 2>&1 || echo [WARN] hermes CLI not on PATH: config verification will be skipped.

:: --- Step 1: Apply patch if needed ------------------------------------------
pushd "%REPO%" || exit /b 1
git rev-parse --is-inside-work-tree >nul 2>&1 || ( popd & echo [FATAL] not a git worktree & exit /b 1 )

set "PATCH_NEEDED=1"
if exist "agent\moa_auto_router.py" (
  git apply --reverse --check "%PATCH%" >nul 2>&1
  if not errorlevel 1 ( set "PATCH_NEEDED=0" )
)

if "%PATCH_NEEDED%"=="1" (
  echo [1/6] Applying auto-MoA patch...
  git apply --whitespace=nowarn --check "%PATCH%" >nul 2>&1
  if errorlevel 1 (
    echo [WARN] clean apply failed; trying per-file salvage...
    set "SALVAGE_FAIL="
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
      if errorlevel 1 (
        git apply --whitespace=nowarn --check --include="%%F" "%PATCH%" >nul 2>&1
        if errorlevel 1 (
          git apply --3way --include="%%F" "%PATCH%" >nul 2>&1
          if errorlevel 1 (
            echo [WARN] FAILED: %%F
            set "SALVAGE_FAIL=!SALVAGE_FAIL! %%F"
          )
        ) else (
          git apply --whitespace=nowarn --include="%%F" "%PATCH%" >nul 2>&1
          if errorlevel 1 (
            echo [WARN] FAILED: %%F
            set "SALVAGE_FAIL=!SALVAGE_FAIL! %%F"
          )
        )
      )
    )
    if defined SALVAGE_FAIL ( popd & echo [FATAL] apply failed for:%SALVAGE_FAIL% & exit /b 1 )
  ) else (
    git apply --whitespace=nowarn "%PATCH%" || ( popd & echo [FATAL] apply failed & exit /b 1 )
  )
  echo [1/6] Patch applied.
) else (
  echo [1/6] Patch already applied; skip.
)
popd

:: --- Step 2: Install git hook (best-effort) --------------------------------
echo [2/6] Installing git post-merge hook...
if exist "%REPO%\.git\hooks" (
  if not exist "%REPO%\.git\hooks\auto-moa" mkdir "%REPO%\.git\hooks\auto-moa"
  copy /y "%PATCH%" "%REPO%\.git\hooks\auto-moa\auto-moa-current.patch" >nul 2>&1
  copy /y "%HOOK_SRC%" "%REPO%\.git\hooks\post-merge" >nul 2>&1
  echo [2/6] Hook installed.
) else (
  echo [2/6] SKIP: .git\hooks not found.
)

:: --- Step 3: Verify watchdog exists ----------------------------------------
echo [3/6] Verifying watchdog script...
if not exist "%WATCHDOG%" (
  echo [FATAL] watchdog not found: %WATCHDOG%
  exit /b 1
)
echo [3/6] Watchdog ready.

:: --- Step 4: Create hermes-update.bat wrapper -------------------------------
echo [4/6] Creating hermes-update.bat wrapper...
copy /y "%RECOVERY%\hermes-update.bat" "%HERMES_UPDATE%" >nul 2>&1
if errorlevel 1 (
  echo [4/6] WARN: could not copy to %HERMES_UPDATE%
  echo        Use %RECOVERY%\hermes-update.bat directly.
) else (
  echo [4/6] Wrapper installed: %HERMES_UPDATE%
)

:: --- Step 5: Install cronjob (safety net) -----------------------------------
echo [5/6] Checking for cronjob installer...
where schtasks >nul 2>&1
if errorlevel 1 goto :skip_cron

schtasks /create /tn "AutoMoA-Watchdog" /tr "%WATCHDOG%" /sc minute /mo 60 /f /rl LIMITED >nul 2>&1
if errorlevel 1 (
  echo [5/6] WARN: schtasks failed (need Admin). Cronjob not installed.
  echo        Re-run as Administrator for cronjob safety net.
) else (
  echo [5/6] Cronjob installed: runs watchdog every 60 min.
)
goto :profile_sync

:skip_cron
echo [5/6] SKIP: schtasks not available.

:profile_sync
echo [6/6] Syncing MoA graphs into profiles...
set "SYNC_PY=%RECOVERY%\tools\moa_sync.py"
if not exist "%SYNC_PY%" (
  echo [6/6] WARN: sync tool not found: %SYNC_PY%
  goto :summary
)
where python >nul 2>&1 || (
  echo [6/6] WARN: python not on PATH, skipping profile sync. Run: hermes-update --repair
  goto :summary
)
python "%SYNC_PY%" --sync >nul 2>&1
if errorlevel 1 (
  echo [6/6] WARN: profile sync reported drift. Run: hermes-update --repair
) else (
  echo [6/6] Profiles synced.
)
goto :summary

:summary
echo.
echo ===========================================================================
echo  INSTALL COMPLETE
echo ===========================================================================
echo.
echo  Safe update:    "%HERMES_UPDATE%"
echo  Manual repair:  "%WATCHDOG%"
echo  Check health:   "%HERMES_UPDATE%" --check
echo.
echo  Cronjob (if installed) auto-repairs every 60 minutes.
echo.
exit /b 0
