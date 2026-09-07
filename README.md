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
/model moa:free_auto_moa
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
| `check-moa-models.py` / `.bat` | Мониторинг живости моделей схемы (free+pay тиры, без API-ключа) + статус гейта `paid_access` + новые free-модели каталога. |
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
| `code_visual_deep`, `logic_visual_deep` | `stepfun/step-3.7-flash:free` | step умрёт → 2 |

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

### Где лежат MoA-трейсы

`moa.save_traces: true` пишет **per-profile**: `%LOCALAPPDATA%\hermes\profiles\<profile>\moa-traces\<session_id>.jsonl`
(каждая строка — полный ход: входы/выходы референсов, вход/выход агрегатора, `routing`).
Глобальный `%LOCALAPPDATA%\hermes\moa-traces\` — legacy, свежих сессий там нет, смотри в профиле.

## Два режима auto-MoA (dual-mode, с 01.09.2026)

| Режим | Пресет | Панель | Агрегаторы |
|---|---|---|---|
| Free (дневной) | `free_auto_moa` | 5 free-пресетов | longcat / laguna-s / step |
| Pay (тяжёлые задачи) | `pay_auto_moa` | 5 pay-пресетов | gpt-5.6-luna (агрегатор всех pay-пресетов) |

Переключение: `/model moa:pay_auto_moa` (или `free_auto_moa`) в Desktop/CLI; глобальный
дефолт — free. В pay-панели платный ТОЛЬКО агрегатор (1 платный вызов за ход, референсы
free), капы и reasoning-распределение те же.

### Дедупликация пресетов (07.09.2026)

12 пресетов вместо 13: legacy-имя `auto_moa` удалено везде (тот же граф, что у
`free_auto_moa`; сессии мигрированы `auto_moa` → `free_auto_moa` с бэкапами
`state.db.preset-dedup-20260907.bak`). Одинаковые слоты не копятся:
`free_auto_moa` алиасит блоки `default`, `pay_auto_moa` — блоки `pay_default`
(YAML anchors — парсер видит те же словари, валидация зелёная). Профили fantrax
досинканы каноническим графом (там не хватало `auto_route`).

⚠️ **Pay-режим требует `paid_access`** (Plus-подписка ИЛИ купленные кредиты). Промо-кредиты
Free-плана платный доступ не открывают; без него pay-пресеты **тихо** работают как free —
CLI не печатает ни ошибки, ни warning (проверено identity-пробой 01.09.2026). Статус гейта
показывает `check-moa-models.bat` (строка `account gate: ... paid_access=...`).

### reasoning_effort: почему разные уровни

- **Advisors — low/medium**: их совет обрезается `reference_max_tokens: 600` — reasoning
  сверх этого бюджета физически не доезжает до агрегатора; wall time хода = самый медленный
  advisor (docs), поэтому max у всех советников = все ждут самого глубокого (было 86s).
- **Агрегатор — high**: пишет финальный ответ и tool-calls. `max` не держим сознательно —
  при деградации качества поднять до `xhigh`/`max` у конкретного пресета.

### Адекватность reasoning сложности хода (с коммита `cda3c3860`)

Роутер раз в ход считает `complexity` (`trivial` ≤8 слов без кода/картинки/аттача;
`complex` — длинный текст / свежий визуал / `@url`-контекст / содержательный код;
иначе `standard`) и масштабирует **только slot-пины, на копиях** (конфиг не мутирует):
`trivial` — советники→low, агрегатор→medium (только понижение); `complex` —
советники +1 ступень (потолок high), агрегатор→xhigh (только повышение);
`standard` — как в конфиге. Незапиненные/отключённые (`none`) слоты не трогаются,
глобальный fallback агрегатора (`#64187`) сохраняется. Сложность пишется в трейс
(`routing.complexity`) — проверять там.

### Подписка Nous Plus ($20/мес) — зачем и когда

Текущий аккаунт — free tier: 50 RPM / 500K TPM, только `:free`-модели; **платные
модели не работают вовсе** («requires available credits», проверено 01.09.2026).
Plus ($20/мес) даёт: $22 кредитов (rollover до $10), 400 RPM / 4M TPM, весь каталог
(300+ моделей) минимум −20% от list-цены, Tool Gateway. Главный практический смысл:
платная модель-агрегатор не исчезает «вместе с free-периодом» — снимается главный
риск схемы. Платный агрегатор с 07.09.2026: `openai/gpt-5.6-luna` ($0.20/$1.20 за 1M,
1.05M ctx) — выбран как компромисс «сильно и недорого»: в разы дешевле
флагманов (Sonnet-5 $1.60/$8.00, glm-5.3 $0.90/$2.82), заметно сильнее
flash-моделей на тяжёлых задачах. Ранее был `z-ai/glm-5.3-flash`
($0.06/$0.20 за 1M, 1.31M ctx, vision) — заменён из-за redo-rate на
сложных задачах. Решение о подписке — за владельцем; без неё схема
полностью рабочая на free-моделях (см. таблицу выше).

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
