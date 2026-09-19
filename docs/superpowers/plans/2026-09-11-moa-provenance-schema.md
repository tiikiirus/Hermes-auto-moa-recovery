# MoA Provenance Contract as Checkable Schema

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal.** Заменить «гонку вооружений» вокруг форм tool-вывода механической проверкой уже подписанного агентом контракта: буллет из секции `VERIFIED` обязан содержать цитату, которая является **реальной подстрокой транскрипта**, который советник получил. Не прошедшие проверку буллеты не удаляются, а **перемаркировываются** в `INFERRED`. Детектор форм (`_TOOL_CLAIM_RES`) остаётся, но перестаёт быть единственной линией защиты.

**Статус.** Дизайн (фаза 5 из плана правок). Не начато; зависит от фаз 2–4 — они уже выкачены (`9426b02`, `0873c63`).

---

## 1. Почему blacklist не может закрыть вопрос

Сегодня антифабрикация — это набор регулярок (`agent/moa_loop.py`, `_TOOL_CLAIM_RES`, ~строка 834):

```python
re.compile(r"^\s*\[called tool:"),
re.compile(r"^\s*\[tool result"),
re.compile(r"^\s*containerTag\s*[:=]\s*\S+\s*$"),
re.compile(r"^\s*\"\s*exit_code\s*\"\s*:"),
re.compile(r"^\s*\{\s*\"exit_code\""),
```

Плюс `_CLAIM_PREFIX_RE` (~849), который снимает `- ` / `VERIFIED:` / `INFERRED:` перед судом, и `_scrub_unverified_tool_claims` (~853), который режет «голое» совпадение и оборачивает процитированное.

Разбор `tools/probes/review_scrub_probes.py` (14 форм) показывает границу метода — вот формы, которые **не** ловятся ни одним из пяти выражений:

| Форма в пробе | Что это |
|---|---|
| `stdout: bash: command not found` | голая метка канала |
| `stderr: permission denied` | голая метка канала |
| `exit_code: 0` | незакавыченный ключ |
| `HTTP/1.1 404 Not Found` | строка статуса HTTP |
| `Status: 200 OK` | статус-строка |
| `PID 12345 — процесс жив` | идентификатор процесса |

Каждая новая форма — новая регулярка, а множество форм **открыто**: оно растёт вместе с изобретательностью модели. Прошлый замер это подтверждает эмпирически: в трейсе `20260909_212807_4478b2.jsonl` 282 tool-подобных строки, из них часть — именно непокрытые формы.

При этом тот же агент уже **подписал** другой контракт (`_REFERENCE_SYSTEM_PROMPT`, ~262):

> `VERIFIED:` only claims directly supported by a quote from the conversation above (**quote the supporting words**).
> `INFERRED:` hypotheses, guesses, and recommendations — mark every uncertain claim with `[uncertain]`.

Это и есть закрытый предикат. «Цитата обязана быть подстрокой материала, который советник видел» — **механически проверяемо** и не расширяется вместе с фантазией модели. Сегодня никто не читает `VERIFIED`/`INFERRED` семантически: `_CLAIM_PREFIX_RE` их только срезает.

**Смена вопроса:**

| | Blacklist (сегодня) | Schema (предлагается) |
|---|---|---|
| Вопрос | «похоже ли это на tool-результат?» | «несёт ли утверждение собственное доказательство?» |
| Поверхность | открытая (список форм) | закрытая (есть цитата / нет цитаты) |
| Действие | удалить / обернуть | перемаркировать `VERIFIED → INFERRED` |
| Доказательство | ручная ревизия форм | подстрока + детерминированный счётчик |

---

## 2. Архитектура

Новый этап — **Stage B** в том же конвейере подготовки текста, где уже живёт Stage A.

```
_reference_messages(messages)            # advisory view: транскрипт, который видел советник
        │
        ├─ corpus_text  ─────────────────────────────┐
        │                                            │
advisor output ──► Stage A: _scrub_unverified_tool_claims(text, corpus)
                     режет голые tool-формы,           │
                     оборачивает процитированные       │
                        │                              │
                        └──► Stage B: _check_verified_quotes(text, corpus)   ◄── НОВОЕ
                               VERIFIED-буллет без реальной цитаты
                               → [UNVERIFIED-CLAIM, ...] + метка, текст СОХРАНЯЕТСЯ
                                        │
                                        ▼
                        _guidance_inputs → _build_guidance → агрегатор
                                        │
                                        ▼
                        _RefAccounting(scrub_removed/marked, verified_checked/downgraded)
                                        │
                                        ▼
                        moa_trace._slot_trace → "scrub": {removed, marked, checked, downgraded}
```

Порядок важен: Stage A → Stage B. Stage A удаляет активно вводящие в заблуждение блоки; Stage B перемаркировывает недоказанные утверждения. Stage B никогда не удаляет — иначе мы теряем полезный совет, который просто не смог сослаться.

### 2.1 Корпус: что считается «транскриптом»

**Решение: корпус — это advisory view, то есть ровно тот текст, который был отправлен советнику** — `_reference_messages(messages)` после `_truncate_tool_result` и после редактирования приватности. Это то, что уже использует Stage A (`_scrub_reference_outputs`, ~1006: `context_text = "\n".join(flatten_message_text(...))` по `ref_messages`).

Обоснование:

1. **Семантика утверждения.** `VERIFIED` говорит «я нашёл это в материале, который мне дали». Значит материал — это вход советника, а не то, что гипотетически существует в системе.
2. **Приватность.** Корпус после редактирования (`privacy_filter: full` → `_redact_reference_outputs`) не содержит секретов, вычищенных из промпта. Проверка сырого транскрипта позволила бы «верифицировать» цитату, которую советнику не показывали.
3. **Совместимость.** Тот же корпус, что у Stage A ⇒ один аргумент, одна нормализация на ход, никаких рассинхронов между двумя стадиями.

**Отвергнутая альтернатива.** Полный необрезанный транскрипт агрегатора. Он «честнее» по фактам, но проверяет не тот предикат: советник физически не видел вырезанную середину tool-результата (`_truncate_tool_result` ~687: head+tail по `_REFERENCE_TOOL_RESULT_BUDGET = 4000`, маркер `[... N chars omitted ...]`), поэтому совпадение там — случайность, а не доказательство. Цена выбора — пункт FP2 в политике ниже.

### 2.2 Предикат: нормализация и извлечение цитат

Две чистые функции, без I/O, без модульных глобалов (урок `_QUOTED_CACHE` из фазы 3).

**Нормализация `_normalize_for_match(text) -> str`** — одинаковая для корпуса и для цитаты:

- `unicodedata.normalize("NFKC", text)`;
- фолдинг парных типографских кавычек и апострофов `“ ” ‘ ’ « » „ ‟` → `"`, `'`;
- `\r\n` / `\r` → `\n`, затем схлопывание **любых** пробельных последовательностей в один пробел;
- `casefold()`.

Гомоглифы кириллица/латиница (`а`/`a`, `о`/`o`) **не** сворачиваются: это создало бы ложные совпадения. Такие цитаты просто не подтверждаются — см. FP9.

**Извлечение `_extract_quotes(line) -> list[str]`** — кандидаты-цитаты внутри одной строки:

- парные `"…"`, `'…'`, `` `…` ``, типографские варианты (уже сведены нормализацией);
- содержимое fenced/индент-блока, открытого на этой строке;
- экранирование `\"` внутри цитаты разэкранируется;
- **несбалансированный** маркер ⇒ цитатой не считается (`unbalanced` в телеметрию).

**Порог значимости:** цитата принимается к проверке только если после нормализации `len >= _MIN_QUOTE_CHARS` (12) **и** в ней `>= 2` токена. Это главный регулятор, и он сознательно смещён в сторону **false positive по строгости**: короткое совпадение («the file», «4 байта») статистически ничего не доказывает, а пропуск длинной честной цитаты — цена, которую мы решили платить (FP5).

### 2.3 Разбор структуры

`_check_verified_quotes(text, context_text) -> tuple[str, int, int]` возвращает `(relabeled_text, downgraded, verified_bullets_checked)`.

1. Режем текст на строки, отслеживаем **текущую секцию**: строка, чей нормализованный вид начинается с `verified:` → секция `VERIFIED`; начинается с `inferred:` → секция `INFERRED`; пустая строка секцию не меняет; иначе строка принадлежит текущей секции. Если заголовков нет вообще — детектор молчит (`(text, 0, 0)`): контракт не был соблюдён структурно, но перемаркировывать нечего.
2. Только для строки в секции `VERIFIED` (включая `- ` / `* ` буллеты — снимаются `_CLAIM_PREFIX_RE`):
   - собрать цитаты `_extract_quotes`;
   - если хотя бы одна цитата нормализована и является **подстрокой** нормализованного корпуса → `checked += 1`, строка не меняется;
   - иначе → `downgraded += 1`.
3. Баннер выдаётся **на прогон** последовательных неподтверждённых `VERIFIED`-строк (`[UNVERIFIED-CLAIM, no verbatim quote from the transcript — treated as inference]`), а не на строку. Прогонная группировка уже отработана в Stage A (~939) ровно по той же причине: построчные маркеры раздувают промпт агрегатора и протекают в следующий advisory view, где советники начинают их имитировать.
4. Строка `INFERRED` не трогается никогда: гипотезы там и должны быть.

**Границы возможного (важно не переобещать):**

- Это **provenance, а не entailment**. Детектор не проверяет, что цитата *подтверждает* утверждение: можно процитировать реальную строку и сделать из неё неверный вывод. Проверка опоры — отдельная задача (NLI / требование ключевых существительных), в v1 вне объёма.
- Советник, который свалит всё в `INFERRED`, пройдёт проверку. Это недо-утверждение, а не фабрикация; агрегатор видит `INFERRED` и не принимает это за факт.
- Детектор не заменяет Stage A: голый tool-блок опасен и без метки `VERIFIED`.

---

## 3. Политика ложных срабатываний

Три инварианта, действующих для **всех** случаев ниже:

- **P1 — Никогда не удалять.** Неподтверждённая цитата — это отсутствие доказательства, а не вводящее в заблуждение свидетельство. Удаление остаётся работой Stage A. Stage B только перемаркировывает.
- **P2 — Fail-open.** Любое исключение внутри Stage B возвращает исходный текст, `(text, -1, -1)`-подобный «не работал» сигнал (конкретно: `None`-семантика счётчиков, см. §5), и `logger.warning`. Умирающий детектор не должен ни ломать ход, ни молча терять совет. Это та же дисциплина, что `except`-ветка `_scrub_reference_outputs` (~1044).
- **P3 — Детерминизм.** Никаких вероятностных порогов, никакого fuzzy-матчинга, никаких модульных глобалов. Exact substring после нормализации — **единственный** путь к подтверждению. Если после реплея (§6) строгость окажется невыносимой, нечёткое сопоставление добавляется отдельной фазой с собственным порогом и отдельным счётчиком, никогда не как v1.

| ID | Источник ложного срабатывания | Пример | Что было бы, если не обработать | Политика v1 | Телеметрия |
|---|---|---|---|---|---|
| **FP1** | **Пересказ.** Самая частая форма: советник перефразирует запрос пользователя своими словами. | `VERIFIED: пользователь просит починить парсер` (в транскрипте — `исправь, пожалуйста, парсер`) | Удаление → потеря верного наблюдения; молчание → фабрикация проходит как факт | Перемаркировать в `[UNVERIFIED-CLAIM, no verbatim quote — treated as inference]`, текст сохранить целиком | `downgraded`, причина `no_quote` |
| **FP2** | **Шов усечения.** Цитата пересекает вырезанную середину tool-превью (`[... N chars omitted ...]`, бюджет 4000). | Цитата из середины длинного `read_file` | Тот же шов режет честную цитату, что и пропускает случайное совпадение | Принять цитату, целиком лежащую в head **или** tail (индексы частей известны после нормализации по маркеру). Цитату, **пересекающую** шов, пометить отдельной меткой `[UNVERIFIED-CLAIM, quote crosses a truncation boundary]` | `downgraded`, причина `truncation_seam` |
| **FP3** | **Редактирование приватности.** В `privacy_filter: full` плейсхолдеры вырезают фрагменты до отправки советнику. | Цитата содержит плейсхолдер | Проверка сырого транскрипта подтверждала бы цитату текста, которого советник не видел | Корпус — уже отредактированный advisory view. Плейсхолдер в цитате совпадает с корпусом → проходит; секрет до редактирования — не может | нет (по построению) |
| **FP4** | **Вариации маркеров цитирования:** вложенность, `\"`, бэктики, `«»`, тройные кавычки, несбалансированная пара. | `VERIFIED: "он сказал \"готово\""` | Лишние даунгрейды честных цитат | Парные маркеры нормализуются и разэкранируются; fenced/индент-блок — тоже цитата; **несбалансированный** маркер цитатой не считается | `unbalanced` |
| **FP5** | **Слишком короткая цитата / стоп-слова.** | `VERIFIED: "файл"` | Совпадение почти всегда, доказательство ≈ 0 | Порог: `>= 12` нормализованных символов **и** `>= 2` токена, иначе даунгрейд | `downgraded`, причина `too_short` |
| **FP6** | **Цитата каркаса:** guidance-заголовок, баннеры `[UNVERIFIED-CLAIM]`, `_ADVISORY_INSTRUCTION`. | `VERIFIED: "[Mixture of Agents reference context]"` | Модель «доказывает» реальность, цитируя инструкцию | Корпус по построению — `_reference_messages`, где нет ни guidance, ни баннеров. Закрепляется тестом-инвариантом | нет (по построению) |
| **FP7** | **Цитата реальна, но не подтверждает вывод** (пробел entailment). | Верная строка про порт 8000 + неверный вывод про причину падения | Оверклейм, если считать детектор гарантией истинности | **Вне объёма v1**, задокументировано. Компенсация: заголовок guidance уже говорит агрегатору проверять инструментами (строка ~1583) | нет |
| **FP8** | **Повторы.** Лог-эхо-советник повторяет идентичную строку сотни раз. | 300 раз один и тот же `[tool result]` | O(n·m) подстроковые сканы, помноженные на fan-out | Мемоизация в **локальном** dict на вызов (контекст у каждого советника свой и параллельный fan-out ⇒ модульный кэш был бы и неверен, и потоконебезопасен) | нет |
| **FP9** | **Unicode/гомоглифы/NBSP/CRLF.** | `о` кириллическая вместо `o`, неразрывный пробел в цитате | Ложные подтверждения при агрессивном фолдинге, ложные даунгрейды при отсутствии нормализации | NFKC + фолдинг кавычек + схлопывание пробелов + casefold. **Гомоглифы не сворачиваются** — даунгрейд вместо подгонки | `no_quote` + образец в офлайн-ревизию (§6) |
| **FP10** | **Другой язык.** Транскрипт рус+англ; цитата — перевод. | `VERIFIED: "the user asks to fix the parser"` при русском исходнике | Массовые даунгрейды | Оставить даунгрейд: контракт требует «quote the supporting words» — пересказ переводом цитатой не является. Если доля велика, правкой **промпта**, а не детектора | `downgraded`, причина `no_quote` |

**Правило о порогах.** Если реплей (§6) покажет долю даунгрейдов `> ~50%` от всех `VERIFIED`-буллетов — это сигнал, что неверен **корпус или контракт**, а не модели. Тогда правка идёт в `_build_guidance`/`_REFERENCE_SYSTEM_PROMPT` или в бюджет усечения, а не в ослабление предиката.

**Стоимость ложных срабатываний ограничена по построению.** Худший исход Stage B — лишний баннер перед верным советом; совет не теряется, агрегатор видит его как гипотезу. Именно поэтому P1 запрещает удаление: при удалении асимметрия была бы обратной (одно ложное срабатывание = потеря полезного совета).

---

## 4. Tech Stack

Python 3.11 (venv `hermes-agent`), pytest, PowerShell 5.1, `git apply`. Тесты — через `run-moa-tests.bat` (live + recovery) или тот же venv-pytest с `--basetemp` под `Temp\opencode` и `-p no:cacheprovider`.

## 5. File Structure

Modify (9 файлов патча — список не меняется, новых файлов в live-дереве нет):

- `agent/moa_loop.py` — `_normalize_for_match`, `_extract_quotes`, `_check_verified_quotes`, Stage B в `_scrub_reference_outputs`, поля `_RefAccounting`.
- `agent/moa_trace.py` — `scrub` получает `checked` / `downgraded`.
- `tests/agent/test_moa_auto_runtime.py` — тесты Tasks 1–3.

Modify (recovery-репозиторий):

- `tools/probes/moa_provenance_replay.py` — **новый** read-only реплей-аудитор (Task 4).
- `auto-moa-current.patch`, `SHA256SUMS.txt`, `.gitattributes` (по конвенции реестра).

**Интерфейсы:**

- `_normalize_for_match(text: str) -> str`
- `_extract_quotes(line: str) -> list[str]`
- `_check_verified_quotes(text: str, context_text: str) -> tuple[str, int, int]` → `(relabeled_text, downgraded, checked)`
- `_REFERENCE_TOOL_RESULT_BUDGET` — не меняется в этой фазе (но FP2 даёт телеметрию для решения о нём).

**Конвенция счётчиков (существующая, не ломать).** `_RefAccounting.scrub_removed/scrub_marked` = `None` означает «советник не тронут скраббером» (by design; подтверждено свежим трейсом `20260911_011217_069587.jsonl`: `guidance_output == output`, `scrub: {removed: None, marked: None}`). Новые поля следуют тому же: `None` = стадия не запускалась/советник чист, `int` = стадия работала. **Известный дефект, который эта фаза обязана закрыть:** сегодня `None` смешивает «не запускалась» и «запускалась, ничего не нашла» — для Stage B это делает долю даунгрейдов неизмеримой. Решение: Stage B всегда пишет `verified_checked` (в т.ч. `0`), а `verified_downgraded` — `0` при отсутствии находок. Миграция трейса согласуется тестом.

---

## 6. Tasks

### Task 1: Нормализация и извлечение цитат (чистые функции)

**Files:** Modify `agent/moa_loop.py` (рядом с `_CLAIM_PREFIX_RE`); Test `tests/agent/test_moa_auto_runtime.py`.

- [ ] **Step 1: Падающие тесты**

```python
def test_normalize_for_match_folds_quotes_whitespace_and_case():
    from agent.moa_loop import _normalize_for_match

    assert _normalize_for_match('«Он \u00a0Сказал»\r\n\t"Готово"') == '"он сказал" "готово"'


def test_extract_quotes_reads_paired_markers_and_unescapes():
    from agent.moa_loop import _extract_quotes

    line = 'VERIFIED: он сказал \\"exit_code: 0\\" — вот цитата'
    assert any("exit_code: 0" in q for q in _extract_quotes(line))


def test_extract_quotes_ignores_unbalanced_marker():
    from agent.moa_loop import _extract_quotes

    assert _extract_quotes('VERIFIED: "цитата без закрывающей кавычки') == []
```

- [ ] **Step 2: Убедиться, что падают** — `...\.venv\Scripts\python.exe -m pytest tests/agent/test_moa_auto_runtime.py -p no:cacheprovider --basetemp="C:\Users\tiki\AppData\Local\Temp\opencode\ptest-prov1" -q -k "normalize_for_match or extract_quotes"` → `ImportError`.

- [ ] **Step 3: Реализовать** `_normalize_for_match` и `_extract_quotes` по §2.2 с `_MIN_QUOTE_CHARS = 12`, `_MIN_QUOTE_TOKENS = 2`; регулярки — модульным кортежем.

- [ ] **Step 4: Зелёные.** Тот же прогон → 3 passed.

- [ ] **Step 5: Полный гейт.** `run-moa-tests.bat` → exit 0.

### Task 2: Детектор `_check_verified_quotes`

**Files:** Modify `agent/moa_loop.py` (после `_scrub_unverified_tool_claims`); Test `tests/agent/test_moa_auto_runtime.py`.

- [ ] **Step 1: Падающие тесты** (это и есть регрессионный набор на ложные срабатывания из §3)

```python
_CTX = 'пользователь: исправь парсер\n[tool result: {"output": "ok"}]\nассистент: готово'


def test_verified_bullet_with_real_quote_is_untouched():
    from agent.moa_loop import _check_verified_quotes

    text = 'VERIFIED: в транскрипте есть "исправь парсер".\nINFERRED: вероятно, дело в кавычках [uncertain].'
    assert _check_verified_quotes(text, _CTX) == (text, 0, 1)


def test_verified_paraphrase_is_downgraded_but_kept():
    from agent.moa_loop import _check_verified_quotes

    text = "VERIFIED: пользователь просит починить парсер."
    out, downgraded, checked = _check_verified_quotes(text, _CTX)
    assert (downgraded, checked) == (1, 0)
    assert "починить парсер" in out  # P1: текст сохранён
    assert "[UNVERIFIED-CLAIM" in out


def test_verified_quote_from_own_words_is_downgraded():
    """Цитата реальна, но её нет в транскрипте — только в самом ответе советника."""
    from agent.moa_loop import _check_verified_quotes

    text = 'VERIFIED: "кэш агрегатора был холодным".'
    out, downgraded, _ = _check_verified_quotes(text, _CTX)
    assert downgraded == 1 and "кэш агрегатора" in out


def test_inferred_section_is_never_touched():
    from agent.moa_loop import _check_verified_quotes

    text = "INFERRED: без цитаты, так и должно быть [uncertain]."
    assert _check_verified_quotes(text, _CTX) == (text, 0, 0)


def test_no_headings_means_no_opinion():
    from agent.moa_loop import _check_verified_quotes

    text = "Просто совет без секций."
    assert _check_verified_quotes(text, _CTX) == (text, 0, 0)


def test_truncation_seam_quote_is_labeled_distinctly():
    from agent.moa_loop import _check_verified_quotes

    ctx = "начало\n[... 900 chars omitted ...]\nконец"
    seam = 'VERIFIED: "начало [... 900 chars omitted ...] конец"'
    out, downgraded, _ = _check_verified_quotes(seam, ctx)
    assert downgraded == 1 and "truncation boundary" in out


def test_fail_open_on_non_string():
    from agent.moa_loop import _check_verified_quotes

    assert _check_verified_quotes(None, _CTX) == (None, 0, 0)
```

- [ ] **Step 2: Убедиться, что падают** → `ImportError`.

- [ ] **Step 3: Реализовать** `_check_verified_quotes` по §2.3, с локальной мемоизацией (FP8) и без модульных глобалов.

- [ ] **Step 4: Зелёные** — `-k "verified or inferred_section or truncation_seam"`.

- [ ] **Step 5: Полный гейт** — `run-moa-tests.bat`.

### Task 3: Stage B в конвейере + счётчики в трейсе

**Files:** Modify `agent/moa_loop.py` (`_scrub_reference_outputs` ~1006, `_RefAccounting` ~231), `agent/moa_trace.py` (~67); Test `tests/agent/test_moa_auto_runtime.py`.

- [ ] **Step 1: Падающие тесты** — Stage A then B на одном корпусе; `verified_downgraded` доезжает до `acct` и до персистентного трейса.

```python
def test_scrub_reference_outputs_runs_quote_check_after_tool_claim_scrub():
    ...
    assert acct.verified_checked == 1 and acct.verified_downgraded == 1


def test_trace_slot_records_verified_quote_counts():
    ...
    assert rec["scrub"]["checked"] == 1 and rec["scrub"]["downgraded"] == 1
```

- [ ] **Step 2: Падают** → `AttributeError`.

- [ ] **Step 3: Реализовать.** В `_scrub_reference_outputs`, внутри той же `try`: Stage A → Stage B → агрегированные счётчики в `logger.warning` (с разбивкой по советникам, как сейчас) → `replace(acct, ...)`. В `_RefAccounting` добавить `verified_checked: int | None = None`, `verified_downgraded: int | None = None`. В `_slot_trace` — `"checked": getattr(acct, "verified_checked", None)`, `"downgraded": getattr(acct, "verified_downgraded", None)`.

- [ ] **Step 4: Зелёные.** В том числе существующий `test_loop_persists_trace_with_guidance_output_and_scrub_counts` (не сломать форму `scrub`).

- [ ] **Step 5: Полный гейт** — `run-moa-tests.bat` (69 live + 7 recovery, ожидание — все зелёные).

### Task 4: Реплей-аудит ДО включения (гейт решения)

**Files:** New `tools/probes/moa_provenance_replay.py` (read-only).

- [ ] **Step 1:** Пройти по всем `*/moa-traces/*.jsonl` всех профилей, прогнать `_check_verified_quotes` на сохранённых `references[].output` против их же advisory-контекста (для пост-патчевых трейсов — `guidance_output`, для старых — `output`).
- [ ] **Step 2:** Отчёт: `verified_bullets`, `downgraded`, доля; гистограмма причин (`no_quote` / `too_short` / `truncation_seam` / `unbalanced`); **дамп каждой даунгрейднутой строки** для глазной ревизии.
- [ ] **Step 3: Гейт.** Идём дальше только если: (а) даунгрейдов без ложных срабатываний при ручной ревизии выборки (минимум 20 строк), (б) доля `> 50%` не наблюдается, (в) доля `truncation_seam` не доминирует. Иначе — правка корпуса/промпта/бюджета, а не детектора (§3, «Правило о порогах»).
- [ ] **Step 4:** Записать итог реплея в этот документ (раздел «Результат реплея») и в реестр SHA.

### Task 5: Реэкспорт патча, верификация, коммит

**Files:** `auto-moa-current.patch`, `SHA256SUMS.txt`, `.gitattributes`.

- [ ] **Step 1:** Реэкспорт диффа база→рабочее дерево по тем же 9 путям (base `9fd44b4dfc44138b9e5d5689acb56c438364ff7b`); `grep -c "^diff --git"` → `9`.
- [ ] **Step 2:** `git apply --reverse --check` (reverse OK) + `git worktree add --detach` на базовом коммите, `apply --check`, прогон MoA-тестов внутри worktree (доказывает самодостаточность патча), затем `git worktree remove --force` + `prune`.
- [ ] **Step 3:** Обновить `SHA256SUMS.txt` (включая новую пробу) → `ALL FRESH`; `python tools/moa_sync.py --check` → `PASS`.
- [ ] **Step 4:** `hermes-update.bat --check` → `HEALTHY` без предупреждений. Коммит в recovery-репозитории. Live-дерево остаётся рабочим незакоммиченным состоянием (оно и есть источник патча).
- [ ] **Step 5:** Перезапустить гейтвей/бэкенды, снять свежий трейс, подтвердить поля `checked`/`downgraded` сканером `tools/probes/moa_trace_toolclaim_scan.py`.

---

## Global Constraints

- PowerShell 5.1: без `&&`/`||` (использовать `;`), `-LiteralPath` для путей.
- НИКОГДА не выполнять `git reset --hard`, `git clean`, `git checkout .` в live-дереве (`C:\Users\tiki\AppData\Local\hermes\hermes-agent`); никогда `git apply --reject`.
- Патч покрывает РОВНО 9 путей: `agent/moa_loop.py`, `agent/moa_trace.py`, `agent/turn_request_assembly.py`, `hermes_cli/moa_cmd.py`, `hermes_cli/moa_config.py`, `agent/moa_auto_router.py`, `tests/agent/test_moa_auto_router.py`, `tests/agent/test_moa_auto_runtime.py`, `tests/hermes_cli/test_moa_cmd_auto.py`.
- Не трогать `peel_reference_guidance` / `peel`-формы, `state.db`, `C:/Fantrax`.
- `max_tokens` в пресетах — мёртвый ключ (фаза аудита); не возвращать.
- Скраббер и детектор — чистые функции: без I/O, без модульных глобалов, счётчики только через `_RefAccounting`.

---

## Результат реплея

_(прогон 2026-09-19, `tools/probes/moa_provenance_replay.py`, 252 трейса всех
профилей; фаза НЕ доказана — гейт <50% не пройден, Stage B не приземлять)_

| Прогон | verified | checked | downgraded | rate | no_quote | too_short | seam |
|---|---|---|---|---|---|---|---|
| baseline (без структурного скипа) | 770 | 297 | 473 | 61.4% | 226 | 247 | 0 |
| + пропуск фенсов/таблиц | 713 | 292 | 421 | 59.0% | 195 | 226 | 0 |

Структурный скип исключил 1240 строк (` ``` `, `},`, `| comp-001 | ...`),
которые детектор судил как утверждения. Глазная выборка после фикса —
настоящие фактические буллеты (пути, статусы контейнеров), а не код.

Что мешает гейту: `too_short` (226/421) — буллеты с короткими бэктик-ссылками
(`.cursor/mcp.json` — 1 токен) при пороге 12 символов + 2 токена, и `no_quote`
(195/421) — пересказ без цитаты. Оба упираются в политику, а не в детектор:
порог — сознательный FP5-сдвиг в строгость; пересказ — by-design даунгрейд
(FP1, текст сохраняется). `truncation_seam = 0` — бюджет усечения не при чём.

Решение по «Правилу о порогах»: детектор больше не трогать. Дальше — либо
калибровка порога на hand-labeled выборке (≥20 строк, Task 4 Step 3), либо
правка контракта/корпуса. Плюс ограничение тени: корпус здесь — прокси
(aggregator input_messages + ref inputs), а не настоящий advisory view, так
что часть `no_quote` может быть артефактом прокси, а не моделей.
