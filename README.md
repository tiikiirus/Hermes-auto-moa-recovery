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

### Выбор пресета

```powershell
/model moa:auto_moa
```

### Что делает auto-MoA

| Запрос | Куда маршрутизируется |
|---|---|
| «напиши функцию», «рефакторинг» | `code_logic_deep` |
| «объясни», «почему», «сравни» | `logic_deep` |
| «покажи график», «нарисуй» | `code_visual_deep` |
| «проанализируй скриншот» | `logic_visual_deep` |
| Непонятно / follow-up | `default` |

### При проблемах

1. `hermes-update --check` — покажет, сломано или нет
2. `hermes-update --repair` — починит
3. Если не помогло — запусти `install-auto-moa.bat` заново

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
| `auto-moa-current.patch` | Чистый патч против `origin/main` hermes-agent (накатывается на свежий `hermes update`; синхронизирован с hermes-agent `89d076a`). |
| `auto-moa-hook.sh` | post-merge git hook для ручного `git pull` (не срабатывает при `hermes update`, т.к. тот использует `reset --hard`). |
| `auto-moa-watchdog.bat` | Скрипт починки: пере-накатывает патч если `auto_moa_router.py` отсутствует или рассинхрон. |
| `hermes-update.bat` | Обёртка `hermes update` с авто-починкой (`--check`/`--repair`/`update`). |
| `install-auto-moa.bat` | Установщик: патч + hook + watchdog + cronjob. |
| `restore-auto-moa-after-update.bat` | Идемпотентное восстановление (config check, focused tests, UI builds). |
| `auto-moa-router-source-20260820.patch` | Legacy source patch для совместимых старых деревьев. |
| `auto-moa-moa-section.yaml` | Backup шести MoA presets и `auto_route` graph. |
| `check-moa-models.py` / `.bat` | Мониторинг живости `:free`-моделей схемы (без API-ключа) + список новых free-моделей в каталоге. |
| `rotate-moa-model.py` / `.bat` | Ротация выпавшей модели во всех конфигах: `rotate-moa-model.bat <dead> <replacement>`. |
| `SHA256SUMS.txt` | Контроль целостности recovery-артефактов. |
| `USER_GUIDE_RU.txt` | Подробная русская инструкция. |

## Схема MoA и ротация моделей (актуально с 01.09.2026)

Free-модели Nous — ротация промо, не контракт: `tencent/hy3:free` умер 01.09.2026
(«HTTP 404: This model's free period has ended»). Агрегатор MoA-пресета — единая
точка отказа (fallback на него не распространяется), поэтому агрегаторы распределены так:

| Пресет | Агрегатор | Падение модели → сломано пресетов |
|---|---|---|
| `default`, `logic_deep` | `meituan/longcat-2.0:free` | longcat умрёт → 2 |
| `code_logic_deep` | `poolside/laguna-s-2.1:free` | laguna-s умрёт → 1 |
| `code_visual_deep`, `logic_visual_deep`, `auto_moa` | `stepfun/step-3.7-flash:free` | step умрёт → 2 |

Референсы деградируют мягко (turn не роняется): laguna-xs, solar-pro4, ling-3.0-flash-fin.

### Мониторинг и ротация

```powershell
# Проверить живость всех моделей схемы (ключ не нужен; вручную или по расписанию):
check-moa-models.bat            # задачa AutoMoA-ModelCheck, ежедневно 09:00
# Ротация выпавшей модели во всех 4 конфигах + recovery yaml:
rotate-moa-model.bat tencent/hy3:free meituan/longcat-2.0:free
# После ротации:
hermes config check
hermes -z "ping" --provider moa -m <preset> --cli   # прогнать затронутые пресеты
```

Монитор различает без ключа: `404 free period` → модель снята с бесплатных (ROTATE),
`404 not found` → модели нет в каталоге (REMOVED), `401/429` → модель жива.
Лог: `%LOCALAPPDATA%\hermes\logs\model-monitor.log`. Каталог free-моделей:
`https://portal.nousresearch.com/models` и `GET https://inference-api.nousresearch.com/v1/models`.

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

Git-репозиторий с remote (`origin`); история дублируется в `Hermes-auto-moa-recovery.bundle`. Git защищает историю от случайного изменения файлов, но не от поломки диска.

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
