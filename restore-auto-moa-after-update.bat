@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "REPO=%LOCALAPPDATA%\hermes\hermes-agent"
set "RECOVERY_DIR=%~dp0"
set "PATCH=%RECOVERY_DIR%auto-moa-router-source-20260820.patch"
set "MOA_BACKUP=%RECOVERY_DIR%auto-moa-moa-section.yaml"
if defined AUTO_MOA_REPO set "REPO=%AUTO_MOA_REPO%"
if defined AUTO_MOA_PATCH set "PATCH=%AUTO_MOA_PATCH%"
if defined AUTO_MOA_CONFIG_BACKUP set "MOA_BACKUP=%AUTO_MOA_CONFIG_BACKUP%"

set "PROFILE=aiqa"
set "QUICK=0"
if not "%~1"=="" set "PROFILE=%~1"
if /I "%~1"=="--quick" (
  set "PROFILE=aiqa"
  set "QUICK=1"
)
if /I "%~2"=="--quick" set "QUICK=1"
if defined AUTO_MOA_QUICK set "QUICK=1"
set "PUSHED=0"

echo [auto_moa] repo: %REPO%
echo [auto_moa] profile: %PROFILE%

where git >nul 2>&1 || goto :missing_git
where hermes >nul 2>&1 || goto :missing_hermes
if not exist "%PATCH%" goto :missing_patch
if not exist "%MOA_BACKUP%" goto :missing_backup

pushd "%REPO%" || goto :pushd_failed
set "PUSHED=1"
git rev-parse --is-inside-work-tree >nul 2>&1 || goto :not_repo

if exist "agent\moa_auto_router.py" (
  echo [auto_moa] already restored; skipping patch.
  goto :patch_verified
)

git apply --reverse --check "%PATCH%" >nul 2>&1
if not errorlevel 1 (
  echo [auto_moa] source patch is already applied.
  goto :patch_verified
)

git apply --check "%PATCH%" >nul 2>&1
if not errorlevel 1 (
  echo [auto_moa] applying source patch...
  git apply --whitespace=nowarn "%PATCH%" || goto :apply_failed
  goto :patch_verified
)

git apply --3way --check "%PATCH%" >nul 2>&1
if not errorlevel 1 (
  echo [auto_moa] applying source patch with 3-way merge...
  git apply --3way "%PATCH%" || goto :apply_failed
  goto :patch_verified
)

echo [auto_moa] ERROR: patch is incompatible with the updated source tree.
echo [auto_moa] No files were changed by this script.
echo [auto_moa] Resolve manually using: %PATCH%
goto :conflict

:patch_verified
git apply --reverse --check "%PATCH%" >nul 2>&1 || goto :reverse_check_failed
git diff --check || goto :diff_failed

if defined AUTO_MOA_SKIP_PROFILE goto :profile_verified
set "CONFIG_PATH="
if defined AUTO_MOA_CONFIG_PATH set "CONFIG_PATH=%AUTO_MOA_CONFIG_PATH%"
if not defined CONFIG_PATH for /f "usebackq delims=" %%I in (`hermes -p "%PROFILE%" config path 2^>nul`) do if not defined CONFIG_PATH set "CONFIG_PATH=%%I"
if not defined CONFIG_PATH goto :profile_path_failed
if not exist "!CONFIG_PATH!" goto :profile_config_missing

set "PYTHON=%REPO%\venv\Scripts\python.exe"
if not exist "!PYTHON!" set "PYTHON=python"

"!PYTHON!" -c "import sys,yaml; from pathlib import Path; d=yaml.safe_load(Path(sys.argv[1]).read_text(encoding='utf-8')) or {}; r=((d.get('moa') or {}).get('presets') or {}).get('auto_moa') or {}; r=r.get('auto_route') or {}; q={'code':'code_logic_deep','logic':'logic_deep','code_visual':'code_visual_deep','logic_visual':'logic_visual_deep','fallback':'default'}; raise SystemExit(0 if all(r.get(k)==v for k,v in q.items()) else 1)" "!CONFIG_PATH!"
if errorlevel 1 (
  echo [auto_moa] restoring MoA graph in profile %PROFILE%...
  copy /y "!CONFIG_PATH!" "!CONFIG_PATH!.before-auto-moa-restore.bak" >nul || goto :config_backup_failed
  "!PYTHON!" -c "import sys,yaml; from pathlib import Path; p=Path(sys.argv[1]); b=Path(sys.argv[2]); d=yaml.safe_load(p.read_text(encoding='utf-8')) or {}; s=yaml.safe_load(b.read_text(encoding='utf-8')) or {}; d['moa']=s['moa']; p.write_text(yaml.safe_dump(d,sort_keys=False,allow_unicode=True),encoding='utf-8')" "!CONFIG_PATH!" "%MOA_BACKUP%" || goto :config_restore_failed
) else (
  echo [auto_moa] profile graph is already present.
)

if defined AUTO_MOA_SKIP_HERMES_CONFIG goto :profile_verified
set "CONFIG_CHECK_FILE=%TEMP%\auto-moa-config-check-%RANDOM%.txt"
hermes -p "%PROFILE%" config check >"!CONFIG_CHECK_FILE!" 2>&1
if errorlevel 1 (
  type "!CONFIG_CHECK_FILE!"
  goto :config_check_failed
)
del /q "!CONFIG_CHECK_FILE!" >nul 2>&1
set "MOA_LIST_FILE=%TEMP%\auto-moa-list-%RANDOM%.txt"
hermes -p "%PROFILE%" moa list >"!MOA_LIST_FILE!" || goto :moa_list_failed
findstr /i /c:"auto_moa" "!MOA_LIST_FILE!" >nul || goto :auto_moa_missing
del /q "!MOA_LIST_FILE!" >nul 2>&1

:profile_verified
if "%QUICK%"=="1" goto :success

set "PYTHON=%REPO%\venv\Scripts\python.exe"
if not exist "!PYTHON!" set "PYTHON=python"
echo [auto_moa] running focused Python tests...
"!PYTHON!" -m pytest tests/agent/test_moa_auto_router.py tests/agent/test_moa_auto_runtime.py tests/hermes_cli/test_moa_config.py tests/hermes_cli/test_moa_cmd_auto.py tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py tests/tui_gateway/test_moa_reference_emit.py tests/cli/test_moa_command.py -q || goto :python_tests_failed

where npm >nul 2>&1 || goto :missing_npm
echo [auto_moa] rebuilding and testing Ink TUI...
call npm run build:ink --workspace ui-tui || goto :tui_build_ink_failed
call npm run build --workspace ui-tui || goto :tui_build_failed
call npm run test --workspace ui-tui -- src/__tests__/createGatewayEventHandler.test.ts || goto :tui_tests_failed
call npm run typecheck --workspace ui-tui || goto :tui_typecheck_failed

echo [auto_moa] building and testing Desktop MoA UI...
call npm run build --workspace apps/desktop || goto :desktop_build_failed
call npm run test:ui --workspace apps/desktop -- src/app/session/hooks/use-message-stream/moa-progress-event.test.tsx || goto :desktop_tests_failed

:success
echo.
echo [auto_moa] SUCCESS.
echo [auto_moa] Restart Hermes Desktop/backend to load restored source.
if "%PUSHED%"=="1" popd
exit /b 0

:missing_git
echo [auto_moa] ERROR: git is not on PATH.
goto :fail
:missing_hermes
echo [auto_moa] ERROR: hermes is not on PATH.
goto :fail
:missing_patch
echo [auto_moa] ERROR: patch not found: %PATCH%
goto :fail
:missing_backup
echo [auto_moa] ERROR: MoA config backup not found: %MOA_BACKUP%
goto :fail
:pushd_failed
echo [auto_moa] ERROR: cannot enter repo.
goto :fail
:not_repo
echo [auto_moa] ERROR: path is not a Git worktree.
goto :fail
:apply_failed
echo [auto_moa] ERROR: patch application failed.
goto :fail
:conflict
if "%PUSHED%"=="1" popd
exit /b 2
:reverse_check_failed
echo [auto_moa] ERROR: reverse patch verification failed.
goto :fail
:diff_failed
echo [auto_moa] ERROR: git diff --check failed.
goto :fail
:profile_path_failed
echo [auto_moa] ERROR: cannot resolve config path for profile %PROFILE%.
goto :fail
:profile_config_missing
echo [auto_moa] ERROR: profile config not found: !CONFIG_PATH!
goto :fail
:config_backup_failed
echo [auto_moa] ERROR: cannot back up profile config.
goto :fail
:config_restore_failed
echo [auto_moa] ERROR: cannot restore MoA graph.
goto :fail
:config_check_failed
echo [auto_moa] ERROR: hermes config check failed.
goto :fail
:moa_list_failed
echo [auto_moa] ERROR: hermes moa list failed.
goto :fail
:auto_moa_missing
echo [auto_moa] ERROR: auto_moa is absent after config restore.
goto :fail
:python_tests_failed
echo [auto_moa] ERROR: focused Python tests failed.
goto :fail
:missing_npm
echo [auto_moa] ERROR: npm is not on PATH.
goto :fail
:tui_build_ink_failed
echo [auto_moa] ERROR: Ink dependency build failed.
goto :fail
:tui_build_failed
echo [auto_moa] ERROR: Ink TUI build failed.
goto :fail
:tui_tests_failed
echo [auto_moa] ERROR: Ink TUI tests failed.
goto :fail
:tui_typecheck_failed
echo [auto_moa] ERROR: Ink TUI typecheck failed.
goto :fail
:desktop_build_failed
echo [auto_moa] ERROR: Desktop build failed.
goto :fail
:desktop_tests_failed
echo [auto_moa] ERROR: Desktop MoA tests failed.
goto :fail

:fail
if defined CONFIG_CHECK_FILE del /q "!CONFIG_CHECK_FILE!" >nul 2>&1
if defined MOA_LIST_FILE del /q "!MOA_LIST_FILE!" >nul 2>&1
if "%PUSHED%"=="1" popd
exit /b 1
