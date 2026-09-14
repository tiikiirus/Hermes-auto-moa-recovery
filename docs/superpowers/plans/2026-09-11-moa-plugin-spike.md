# Spike: может ли auto-MoA стать плагином вместо 9-файлового патча

**Time-box:** одна разведка без реализации (≈12 tool-calls: чтение `plugins/AGENTS.md`, `plugin_loader.py`, `hermes_cli/plugins.py` (`VALID_HOOKS`, `register_hook`, `register_cli_command`), `hermes_cli/providers.py`, `runtime_provider.py`, `conversation_loop.py`, `chat_completion_helpers.py`, `docs/observability/README.md`, `turn_context.py`, `turn_finalizer.py`, `tools/live_tree_check.py`, `git diff --stat`). Ни одной правки live-кода.

**Вердикт: нет — целиком нельзя, ни сегодня, ни «дописав плагин». Около 3% дельты (21 из 715 строк) хук-абельно сейчас; остальное требует *обобщённого* расширения поверхности плагинов в ядре, и это расширение придётся предлагать апстриму. Скелет при этом полезен уже сейчас: он фиксирует, где именно проходит граница.**

---

## 1. Что именно надо разместить

Патч — это не «слой рядом с Hermes», а **дельта к нативной реализации MoA**. Замер (`git diff --stat` против `9fd44b4df`):

| Файл | Изменение |
|---|---|
| `agent/moa_loop.py` | +431 / −0 |
| `agent/moa_auto_router.py` | +214 (новый файл) |
| `hermes_cli/moa_config.py` | +34 |
| `hermes_cli/moa_cmd.py` | +21 |
| `agent/moa_trace.py` | +21 |
| `agent/turn_request_assembly.py` | +5 |
| 3 файла тестов | +~600 |

Итого 715 вставок / 11 удалений. Из них ~135 строк — скраббер `_scrub_unverified_tool_claims`, ~214 — авто-роутер, ~11 — пункт контракта в `_REFERENCE_SYSTEM_PROMPT`, остальное — проводка, счётчики и нормализация пресетов.

## 2. Что вообще даёт плагинная поверхность

Общее (general) семейство плагинов, `plugins/<name>/` | `~/.hermes/plugins/` | `./.hermes/plugins/` | pip entry points, discovery через `PluginManager` («later-wins»), `register(ctx)`:

- **Хуки.** `VALID_HOOKS` (`hermes_cli/plugins.py:107`) — около 40 имён. Релевантные нам: `pre_tool_call`, `post_tool_call`, `transform_tool_result`, `transform_llm_output`, `pre_llm_call`, `post_llm_call`, `pre_api_request`, `post_api_request`, `api_request_error`, `on_session_start/end`.
- **Middleware.** `ctx.register_middleware(kind, callback)`: «request kinds rewrite the payload, execution kinds wrap the callback».
- **CLI.** `ctx.register_cli_command` — argparse-поддерево вшивается в `hermes` на старте, без правки `main.py` (строки 638, 2656, 3136 в `hermes_cli/main.py` — то есть путь реально рабочий).
- **Секции системного промпта.** `ctx.register_system_prompt_section(id, content, position="after_memory")` — **промпт главного агента**, не советника.
- **Редакция.** `ctx.register_redaction_patterns(patterns)`.
- **Провайдеры.** `plugins/model-providers/<name>/` → `providers.register_provider(ProviderProfile(...))`, лениво, last-writer-wins; `ProviderProfile.create_client()` умеет отдавать кастомный клиент (`agent_runtime_helpers.py:1586`).

Точные семантики трёх «почти подходящих» хуков (`docs/observability/README.md:57-60`):

- `pre_llm_call` — **раз на ход, до начала tool-loop**, «may return a string or `{"context": "..."}` to inject ephemeral context into the current user message» (`agent/turn_context.py:608`).
- `transform_llm_output` — **раз на ход, после tool-loop**, заменяет финальный текст ответа (`agent/turn_finalizer.py:404`).
- `post_api_request` — на API-запрос. Про MoA там есть отдельная оговорка в ядре: «a plugin only sees the aggregator generation; this carries the per-slot advisor spend» (`conversation_loop._moa_reference_metrics_for_hook`).

## 3. Матрица хук-абельности

| Дельта патча | Точка врезки в ядре | Хук-абельно сегодня? | Почему |
|---|---|---|---|
| Скраббер tool-претензий (~135 стр.) | `_scrub_reference_outputs`, вызывается из двух путей guidance | **Нет** | Нет fire-site. Нужны одновременно текст советника, корпус advisory-view и право переписать блок, который получит агрегатор. `transform_llm_output` срабатывает на финальном тексте хода, `pre_llm_call` — до tool-loop и только в user-message |
| Пункт контракта в промпте советника (+11) | `_REFERENCE_SYSTEM_PROMPT`, модульная константа | **Нет** | Промпт советника собирается внутри `moa_loop._run_references_parallel`. `register_system_prompt_section` питает промпт **главного агента** |
| Поля трейса `guidance_output` / `scrub` (+21) | `moa_trace._slot_trace` | **Частично** | Метрики советников уже доезжают до `post_api_request` через `_moa_reference_metrics_for_hook` — это работающий прецедент. Но форма записи трейса плагину не расширяема |
| Авто-роутер (+214) | внутри `MoAChatCompletions.create()` до fan-out | **Нет** | Решение требует raw `moa`-конфига, отпечатка хода и состояния предыдущей категории. Хука там нет; `pre_llm_call` до fan-out не дотягивается |
| Нормализация пресетов (+34) | `moa_config._normalize_preset`, `_FLAT_PRESET_KEYS` | **Нет** | Схема конфига ядра. Неизвестные ключи пресета молча выбрасываются — ровно этот эффект дал находку F1 в аудите пресетов (`max_tokens` был мёртв 72 раза) |
| `turn_request_assembly` (+5) | путь сборки запроса ядра | **Нет** | — |
| CLI-дополнения к `hermes moa` (+21) | `hermes_cli/moa_cmd.py` | **Да** | `ctx.register_cli_command`. Единственный кусок, живущий в плагине без единой правки ядра |

**Итог: 21 из 715 строк, ≈3%.**

## 4. Почему целиком нельзя — корневая причина

MoA в Hermes — **нативный виртуальный провайдер**, а не расширение:

- `hermes_cli/providers.py:30`: `"moa": HermesOverlay(auth_type="virtual", base_url_override="moa://local")` — слаг встроен в реестр провайдеров, а не обнаружен через `plugins/model-providers/`.
- `hermes_cli/runtime_provider.py:757`: `if requested_provider == "moa": return _runtime("moa", "chat_completions", "moa://local", "moa-virtual-provider", …)`.
- Ядро знает про MoA явными ветками: `chat_completion_helpers.should_use_direct_api_call` (`… or getattr(agent, "provider", None) == "moa"` — MoA намеренно оставлен на interrupt-worker), `conversation_loop._moa_client_consumes_prepared_request` (опознаёт фасад по наличию `prepare()`), `conversation_loop._moa_reference_metrics_for_hook`.
- Нативная обвязка вокруг: подкоманда `hermes moa`, `normalize_moa_config`, запись `"moa"` в `models_catalog_static`, потоки `model_switch` / `inventory` / `doctor` / `models_validate`.

Патч **модифицирует** эту реализацию. Плагин по политике (`plugins/AGENTS.md`, «Plugins never touch core») не может ни заменить её, ни врезаться внутрь. И там же прямо описан единственный разрешённый путь: «If it needs a capability the framework lacks, widen the **generic** plugin surface (new hook, new ctx method) and have the plugin use it — never hardcode plugin-specific logic into core».

Отдельная оговорка той же политики: «A hook with no concrete consumer is speculative infrastructure and is rejected». То есть расширение надо предлагать апстриму **вместе с плагином-потребителем** — что и делает этот спайк.

## 5. Отвергнутый путь: MoA как model-provider плагин

Технически возможно: `plugins/model-providers/<name>/` + `register_provider(ProviderProfile(...))` + `create_client()` может вернуть кастомный клиент. То есть плагин мог бы зарегистрировать **второй** виртуальный провайдер (`automoa`) со своим фасадом. Отвергнуто по трём причинам:

1. **Это дубликат, а не слой.** Нативный `provider: moa` никуда не исчезнет, а все существующие конфиги (`model.provider: moa`, пресеты) указывают именно на него. Два источника истины.
2. **Он не наследует специальные ветки ядра.** `should_use_direct_api_call` ключуется на `provider == "moa"`; `_moa_client_consumes_prepared_request` — на наличии `prepare()`; `_moa_reference_metrics_for_hook` читает `client.last_reference_metrics`. Плагинный провайдер молча получит другой путь отмены/воркера и потеряет per-advisor метрики, если их не переписать.
3. **Появляется новый публичный слаг** во всех продуктахых поверхностях (inventory, model switch, doctor, validate) и вечное сопровождение против быстро меняющегося ядра — ровно та причина, по которой политика запрещает «absorbed plugins».

## 6. Что нужно расширить — W1/W2/W3

Все три — **обобщённые**, без `moa` в имени. Прецедент, что это работает: per-advisor метрики в `post_api_request` уже встроены обобщённым хаком (`_moa_reference_metrics_for_hook`), а не отдельным `moa_*`-хуком.

- **W1 — per-generation LLM hook с ролевой разметкой.** Хук, срабатывающий на **каждую** генерацию, включая под-генерации внутри составного/виртуального провайдера. Payload: `role` (`"acting" | "reference" | …`), `label`, `text`, `parent_request_id` и — главное — **сообщения, реально отправленные в этом запросе**. Именно последнего поля не хватает скрабберу (корпус), и именно поэтому сегодня «плагин видит только генерацию агрегатора». С W1 скраббер и весь детектор «контракт-как-схема» становятся чистым кодом плагина без единого упоминания MoA в ядре.
- **W2 — трансформация внедряемого контекст-блока.** Аналог `transform_tool_result` для блока контекста, который составной провайдер прикрепляет к запросу: возврат строки-замены. Тогда пункт протокола, баннеры неподтверждённых цитат и предупреждение в заголовке guidance — всё на стороне плагина. Сегодня `pre_llm_call` умеет только дописывать в user-message и только до tool-loop.
- **W3 — «выбор варианта до fan-out».** Точка, где можно подменить профиль/пресет составного вызова, имея на входе конфиг и отпечаток хода. Без неё авто-роутер остаётся в патче — это наименее переносимая часть (214 строк).

**Что остаётся патчем в любом случае:** `_normalize_preset` / `_FLAT_PRESET_KEYS` (схема конфига) и интеграция дополнений в существующую подкоманду `hermes moa`. Полный уход от патча недостижим без изменения продуктового контракта конфигов.

## 7. Скелет спайка

Лежит в `spike/moa-plugin/` этого репозитория: `plugin.yaml`, `__init__.py`, `README.md`.

Что в нём:
- честный `register(ctx)`: валидные хуки (`post_llm_call`, `pre_llm_call`) + CLI-подкоманда, которая **работает сегодня** (единственные 3%);
- проба `_required_surface_missing(payload)` — на каждом вызове проверяет, пришло ли в payload `role` и `advisory_context`; при отсутствии пишет **один** warning «spike blocked: W1 not landed» и не пытается скраббить. Это делает границу видимой в логах, вместо тихой видимости работы;
- функции стадий объявлены, но не реализованы — их место занимает `NotImplementedError` с ссылкой на W1/W2.

**Куда скелет НЕЛЬЗЯ класть:** в live-дерево. `tools/live_tree_check.py` держит allowlist ровно из 9 файлов патча, а **любой** другой файл (включая untracked) считает NOISE и выходит с кодом 1 (`noise = [(s, p) for s, p in status_lines(repo) if p not in ALLOWLIST]`; untracked не удаляется, но «kept (manual review needed)»). Положенный в `hermes-agent/plugins/hermes-automoa/` скелет сломает гейт `CLEAN` и — что хуже — начнёт протекать в следующие экспорты патча. Установка при реальном внедрении — это `~/.hermes/plugins/hermes-automoa/` (документированный каталог пользовательских плагинов), вне патча по построению.

## 8. Решение спайка

1. **Не переводить auto-MoA на плагины сейчас.** Живой код остаётся 9-файловым патчем; регресс-набор и ритуал экспорта не меняются.
2. **Не реализовывать `automoa`-провайдер** (п. 5) — цена выше выгоды.
3. **Оформить W1/W2 как апстрим-предложение** с этим плагином в роли конкретного потребителя (требование политики: хук без потребителя отклоняется). W2 — самый дешёвый и общий из трёх: он же обслуживает будущую проверку «цитата — реальная подстрока» из `2026-09-11-moa-provenance-schema.md`.
4. **Условие остановки (stop condition):** если апстрим отклоняет W1/W2 как необобщаемые — фиксируем 9-файловый патч как долгосрочную архитектуру, а не как временную, и переносим усилия в регресс-набор и `SHA256SUMS`-ритуал.
