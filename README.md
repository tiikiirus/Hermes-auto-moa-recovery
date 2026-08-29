# Hermes `auto_moa` self-healing recovery kit

Локальный архив opt-in доработки Hermes Agent, которая выбирает MoA preset по типу задачи:

- код/репозиторий → `code_logic_deep`;
- логика/архитектура → `logic_deep`;
- изображение + код/UI → `code_visual_deep`;
- изображение + другой анализ → `logic_visual_deep`;
- неоднозначный короткий follow-up может наследовать предыдущую code/logic категорию;
- новая самостоятельная задача классифицируется заново.

**Ключевое свойство:** этот пакет делает `auto_moa` **устойчивым к `hermes update`** (который делает `reset --hard` и затирает локальные коммиты) и **работает на всех профилях**.

## Быстрый старт

### Один раз: установить self-healing

```powershell
# Обычный пользователь (без admin) — без cronjob:
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\install-auto-moa.bat" fantrax

# От администратора — с cronjob (safety net каждые 60 мин):
# (ПКМ → Запуск от имени администратора)
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\install-auto-moa.bat" fantrax
```

### Каждый раз: обновить Hermes без потери auto-MoA

```powershell
# Вместо `hermes update`:
hermes-update

# Или напрямую:
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\hermes-update.bat"
```

### Проверить здоровье

```powershell
hermes-update --check
```

### Починить без обновления Hermes

```powershell
hermes-update --repair
```

## Как это работает

```
hermes update (reset --hard origin/main)
        ↓
auto-MoA исчезает (коммиты затираются)
        ↓
hermes-update.bat автоматически накатывает патч из recovery-проекта
        ↓
auto-MoA восстановлен
```

Патч хранится **вне `.git`** — в recovery-проекте, поэтому не затирается при `reset --hard`.

## Файлы

| Файл | Назначение |
|---|---|
| `auto-moa-current.patch` | Чистый патч против `origin/main` (1011 строк, 9 файлов). Накатывается на свежий `hermes update`. |
| `auto-moa-hook.sh` | post-merge git hook для ручного `git pull` (не срабатывает при `hermes update`, т.к. тот использует `reset --hard`). |
| `auto-moa-watchdog.bat` | Скрипт починки: пере-накатывает патч если `auto_moa_router.py` отсутствует или рассинхрон. |
| `hermes-update.bat` | Обёртка `hermes update` с авто-починкой (`--check`/`--repair`/`update`). |
| `install-auto-moa.bat` | Установщик: патч + hook + watchdog + cronjob. |
| `restore-auto-moa-after-update.bat` | Идемпотентное восстановление (config check, focused tests, UI builds). |
| `auto-moa-router-source-20260820.patch` | Legacy source patch для совместимых старых деревьев. |
| `auto-moa-moa-section.yaml` | Backup шести MoA presets и `auto_route` graph. |
| `SHA256SUMS.txt` | Контроль целостности recovery-артефактов. |
| `USER_GUIDE_RU.txt` | Подробная русская инструкция. |

## Для всех профилей

Пакет работает на всех профилях автоматически:

- `hermes-update.bat` и `auto-moa-watchdog.bat` используют `%LOCALAPPDATA%\hermes\hermes-agent` — не зависят от профиля
- Cronjob (если установлен) работает на уровне системы
- Для установки на другой профиль: `install-auto-moa.bat <profile_name>`

## Cronjob (опционально)

Устанавливается через `install-auto-moa.bat` от администратора:

- Имя задачи: `AutoMoA-Watchdog`
- Интервал: каждые 60 минут
- Действие: запуск `auto-moa-watchdog.bat`
- Safety net: если `hermes-update.bat` не сработал, cronjob починит в течение часа

## Безопасность

- Патч хранится вне `.git` — не затирается при `hermes update`
- `hermes-update.bat` не меняет `config.yaml` — только накатывает патч
- Не используются `git reset --hard`, `git clean`, `git checkout .` или `git apply --reject`
- Перед восстановлением MoA graph сохраняется `config.yaml.before-auto-moa-restore.bak`
- Реальные Nous/model requests скрипт не запускает

## Git-архив

Это локальный Git-репозиторий без remote. Git защищает историю от случайного изменения файлов, но не от поломки диска.

Проверить состояние:

```powershell
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" status
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" log --oneline
```

## После будущей ручной адаптации patch

1. Заменить `auto-moa-current.patch` актуальным проверенным файлом.
2. Пересчитать `SHA256SUMS.txt`.
3. Выполнить focused verification.
4. Зафиксировать новый snapshot отдельным Git commit.

Не объявлять новую версию рабочей только потому, что patch применился: обязательны config check и scoped tests.
