# Hermes `auto_moa` recovery kit

Локальный архив полезной opt-in доработки Hermes Agent, которая выбирает MoA preset по типу задачи:

- код/репозиторий → `code_logic_deep`;
- логика/архитектура → `logic_deep`;
- изображение + код/UI → `code_visual_deep`;
- изображение + другой анализ → `logic_visual_deep`;
- неоднозначный короткий follow-up может наследовать предыдущую code/logic категорию;
- новая самостоятельная задача классифицируется заново.

## Snapshot

- Дата: `2026-08-29`
- Базовый Hermes commit: `ac8990b47edca65a9e2ba087bedcb0137e95621f`
- Репозиторий `hermes-agent` обновлён; legacy patch часто оказывается несовместимым.
- Скрипт восстановления теперь идемпотентен: при уже восстановленном коде повторно patch не применяется.
- Реальные Nous/model requests скрипт не запускает.

## Файлы

| Файл | Назначение |
|---|---|
| `restore-auto-moa-after-update.bat` | Идемпотентное восстановление: пропускает patch, если `agent/moa_auto_router.py` уже есть; иначе применяет patch; затем config check, focused tests и UI builds |
| `auto-moa-router-source-20260820.patch` | Legacy source patch для совместимых старых деревьев |
| `auto-moa-moa-section.yaml` | Backup шести MoA presets и `auto_route` graph |
| `SHA256SUMS.txt` | Контроль целостности recovery-артефактов |
| `USER_GUIDE_RU.txt` | Подробная русская инструкция, копия файла с рабочего стола |

BAT переносим: он ищет patch и YAML **рядом с собой** через `%~dp0`.

## Рекомендуемый запуск после обновления Hermes

1. Полностью закрыть Hermes Desktop.
2. Открыть PowerShell.
3. Для профиля `default` выполнить:

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\restore-auto-moa-after-update.bat" default
```

Для профиля `aiqa`:

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\restore-auto-moa-after-update.bat" aiqa
```

4. Дождаться `[auto_moa] SUCCESS.` или безопасного сообщения `already restored; skipping patch.`
5. Перезапустить Desktop/backend и выбрать **Mixture of Agents → `auto_moa`**.

### Быстрый режим

Проверяет/восстанавливает source и config, но пропускает tests/builds:

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\restore-auto-moa-after-update.bat" default --quick
```

После крупного update рекомендуется полный запуск без `--quick`.

## Безопасность

- Если `agent/moa_auto_router.py` уже присутствует в целевом репозитории, батник завершается как `already restored` и не трогает рабочие файлы.
- При несовместимом update скрипт завершается с `patch is incompatible` и не применяет patch частично.
- Не используются `git reset --hard`, `git clean`, `git checkout .` или `git apply --reject`.
- Перед восстановлением MoA graph сохраняется `config.yaml.before-auto-moa-restore.bak`.
- При установке в другой профиль его секция `moa` может быть заменена сохранённой секцией из `aiqa`; предыдущий config сначала резервируется.

## Git-архив

Это локальный Git-репозиторий без remote. Git защищает историю от случайного изменения файлов, но не от поломки диска.

Проверить состояние:

```powershell
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" status
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" log --oneline
```

Рядом создаётся `C:\Users\tiki\Documents\Hermes-auto-moa-recovery.bundle` — однофайловая копия Git-истории.

## После будущей ручной адаптации patch

1. Заменить patch/BAT/YAML актуальными проверенными файлами.
2. Пересчитать `SHA256SUMS.txt`.
3. Выполнить focused verification.
4. Зафиксировать новый snapshot отдельным Git commit.
5. Пересоздать `.bundle`.

Не объявлять новую версию рабочей только потому, что patch применился: обязательны config check и scoped tests.
