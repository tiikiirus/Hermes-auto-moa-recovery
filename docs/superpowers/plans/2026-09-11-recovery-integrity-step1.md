# recovery_integrity — Step 1: the read-only verifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Один модуль `tools/recovery_integrity.py`, который отвечает на вопрос «наши байты — те ли, что мы запечатали?»: проверяет печати, чистоту live-дерева вне patch scope и применимость патча. Шаг 1 поставляет **только чтение**: модуль, его CLI и тесты на настоящих temp-репозиториях. Он **не подключён ни к чему** — не меняет `hermes-update.bat`, не удаляет `tools/live_tree_check.py`, не включает блокировку. Это и есть смысл порядка посадки: первый шаг физически не может повлиять на путь обновления.

**Architecture:** Новый модуль в recovery-репозитории, поэтому **десятый путь патча не появляется** — это и делает шаг дешёвым. Печати (`SHA256SUMS.txt`) остаются человекочитаемыми данными; модуль владеет **правилами** над ними. Git доступен через узкий шов `git(*args, cwd=...)`: юнит-тесты быстрые, а всё, что зависит от семантики самого git (нормализация eol, `check-attr`, reverse-apply), проверяется на настоящих репозиториях в temp. Печать шага 2 (`reseal()`) и экспорт патча в этот шаг не входят.

**Tech Stack:** Python 3.11 (venv `hermes-agent`), pytest, git, PowerShell 5.1 (только для запуска гейтов).

## Global Constraints

- PowerShell 5.1: без `&&`/`||` (использовать `;`), `-LiteralPath` для путей.
- НИКОГДА не выполнять `git reset --hard`, `git clean`, `git checkout .` в live-дереве (`C:\Users\tiki\AppData\Local\hermes\hermes-agent`); никогда `git apply --reject`.
- Шаг 1 **не трогает**: `hermes-update.bat`, `tools/live_tree_check.py`, `run-moa-tests.bat`, любой файл live-дерева, любой `config.yaml` профиля. Любая правка этих файлов — это шаг 2, не этот план.
- `verify()` — **чистая функция чтения**: ни одного `write`, `os.replace`, `shutil.copy`, ни одного `git apply` без `--check`. Инвариант закрепляется тестом (Task 4).
- Тесты — `tools/tests/`, запуск через `run-moa-tests.bat` (он уже подхватывает `%RECOVERY%\tools\tests`) или тем же venv-pytest с `--basetemp` под `Temp\opencode` и `-p no:cacheprovider`.
- Любой новый артефакт из sealed set (а `tools/`, `tools/tests/` — внутри него) требует строки в `SHA256SUMS.txt` **и** объявления в `.gitattributes`; после правок — проверка `ALL FRESH`.
- **Реестр — CRLF-файл, и это ломает наивный оракул.** `SHA256SUMS.txt` объявлен `-text` в `.gitattributes`, значит git его **не** нормализует: байты в репозитории — CRLF (измерено: 20 строк CRLF, 0 одиночных LF, 0 одиночных CR). Следствие: `sha256sum -c SHA256SUMS.txt` из Git Bash/MSYS **не может** служить проверкой реестра — он приклеивает `\r` к имени файла и печатает `FAILED open or read` на все 20 строк при полностью свежем реестре (воспроизведено на этом дереве). Читать реестр только с универсальными переводами строк; инвариант закрепляется тестом в Task 3.
- Recovery-репозиторий коммитится; live-дерево по дизайну остаётся незакоммиченным.
- **Известный красный базлайн.** Первый честный прогон `verify()` на текущем дереве покажет `patch_drift`: выгруженный `auto-moa-current.patch` перестал reverse-apply'иться (в `tests/agent/test_moa_auto_runtime.py` дописаны тесты после последнего экспорта). Task 0 закрывает это до включения чего-либо; без него приёмочный прогон на реальном репозитории невозможен.

---

## File Structure

Add:
- `tools/recovery_integrity.py` — модуль + CLI (шов `git`, `paths()`, чтение печатей, `verify()`, рендер отчёта).
- `tools/tests/test_recovery_integrity.py` — фикстуры (temp git-репозиторий + temp recovery-репозиторий) и весь набор тестов.

Modify:
- `SHA256SUMS.txt` — строка для нового модуля и нового теста (+ патча, если выполняется Task 0).
- `.gitattributes` — объявление `text eol=lf` для тех же файлов.
- `auto-moa-current.patch` — только в Task 0 (переэкспорт).

Не создаётся: `conftest.py` — по конвенции соседа (`test_moa_sync_splice.py`) фикстуры живут в самом тестовом модуле. Не создаётся никакого второго модуля: `hermes_fleet` (разрешение корней и профилей) — отдельная возможность, здесь нужен минимальный локальный `repo_root()` / `live_tree()`, и это отмечено в Interfaces.

**Interfaces:**

- `git(*args: str, cwd: Path) -> GitResult` где `GitResult(rc: int, stdout: str, stderr: str)` — единственный шов к git.
- `repo_root() -> Path`, `live_tree() -> Path` — минимальное разрешение, перекрываемое аргументами.
- `paths() -> tuple[str, ...]` — девять путей patch scope, объявленные здесь один раз.
- `sealed(repo: Path) -> list[Seal]` где `Seal(path: str, digest: str)` — разбор `SHA256SUMS.txt` (данные, не вывод генератора).
- `fresh_bytes(path: Path, repo: Path) -> bytes` — байты, которые произведёт свежий checkout (правило печати).
- `verify(repo: Path, live: Path) -> Report` — главный вход; `Report(findings: tuple[Finding, ...])` с `blocked: bool` и `exit_code() -> int`.
- `Finding(flavour: str, severity: str, path: str | None, detail: str)` — `flavour ∈ {missing_seal, stale_seal, checkout_unstable, live_tree_noise, patch_drift}`.
- CLI: `python tools/recovery_integrity.py [--repo P] [--live P] [--json]`; коды возврата `0` нет блокирующих находок, `1` есть, `2` сам верификатор не смог отработать.

---

### Task 0: Вернуть патч в пригодное состояние (предусловие)

**Files:** Modify `auto-moa-current.patch`, `SHA256SUMS.txt`.

- [ ] **Step 1: Экспортировать патч из live-дерева ровно по девяти путям**

```bash
C:/Users/tiki/AppData/Local/hermes/hermes-agent/.venv/Scripts/python.exe -c "import subprocess; paths=['agent/moa_loop.py','agent/moa_trace.py','agent/turn_request_assembly.py','hermes_cli/moa_cmd.py','hermes_cli/moa_config.py','agent/moa_auto_router.py','tests/agent/test_moa_auto_router.py','tests/agent/test_moa_auto_runtime.py','tests/hermes_cli/test_moa_cmd_auto.py']; r=subprocess.run(['git','diff','--']+paths, capture_output=True, cwd=r'C:\Users\tiki\AppData\Local\hermes\hermes-agent'); open(r'C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch','wb').write(r.stdout); print('bytes:', len(r.stdout), 'files:', r.stdout.count(b'diff --git'))"
```

- [ ] **Step 2: Проверить оба направления**

```bash
cd "C:/Users/tiki/AppData/Local/hermes/hermes-agent" && git apply --reverse --check "C:/Users/tiki/Documents/Hermes-auto-moa-recovery/auto-moa-current.patch"; echo "reverse=$?"
```

Ожидание: `reverse=0`. Плюс `git worktree add --detach <temp>` на upstream HEAD, `git apply --check` в worktree, прогон MoA-тестов внутри worktree, затем `git worktree remove --force` + `git worktree prune` — **и обе команды довести до конца**: прерванный `remove` оставляет каталог наполовину удалённым и регистрацию в `.git/worktrees`, после чего `git worktree list` продолжает показывать мёртвое дерево (наблюдалось: `hermes-e2e`, `hermes-patch-test`).

- [ ] **Step 3: Освежить печать патча и проверить реестр**

Пересчитать строку `*auto-moa-current.patch` в `SHA256SUMS.txt`; полная проверка файла должна дать `ALL FRESH` — **CRLF-совместимым читателем, не `sha256sum -c`** (см. Global Constraints):

```bash
python - <<'PY'
import hashlib
from pathlib import Path
ok = bad = miss = 0
for line in Path("SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    digest, _, name = line.partition(" ")
    name = name.lstrip("*").strip()
    if not Path(name).exists():
        print("MISSING ", name); miss += 1; continue
    if hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest:
        ok += 1
    else:
        print("MISMATCH", name); bad += 1
print(f"ALL FRESH: {ok} ok, {bad} mismatched, {miss} missing")
PY
```

Ожидание: `ALL FRESH: 20 ok, 0 mismatched, 0 missing`. Дополнительно убедиться, что правка строки не разъехалась по eol: в `SHA256SUMS.txt` должно остаться `CRLF=20, bare_LF=0`.

- [ ] **Step 4: Гейт**

`./hermes-update.bat --check` → `HEALTHY` **без** строки `WARNING: source drift` (проверено: `[auto-moa] HEALTHY (custom auto-router active)`, exit 0). Форма `cmd /c …` из Git Bash на этом хосте зависает (наблюдалось дважды: таймаут 300 с, причём прерванный `cmd` оставляет полуудалённый worktree в `%TEMP%`); в PowerShell `cmd /c` эквивалентен. Если предупреждение осталось — Task 0 не закрыт, дальше идти нельзя.

---

### Task 1: Шов `git`, форма отчёта и temp-фикстура

**Files:** Add `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

**Interfaces:** Produces `git()`, `GitResult`, `Finding`, `Report`, `verify()` (пока возвращает пустой отчёт).

- [ ] **Step 1: Написать падающие тесты**

```python
"""Read-only verifier for seals, live-tree noise and patch applicability.

Run:  <hermes venv>/python.exe -m pytest tools/tests -q
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import recovery_integrity as ri  # noqa: E402


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_live(tmp_path: pathlib.Path, autocrlf: str = "true") -> pathlib.Path:
    """Настоящий git-репозиторий с одним коммитом.

    core.autocrlf задаётся ЯВНО: тест, зависящий от машинной глобальной настройки,
    зелёный локально и красный в CI — худший вид теста.
    """
    live = tmp_path / "live"
    live.mkdir()
    _git(live, "init", "-q")
    _git(live, "config", "user.email", "fixture@example.invalid")
    _git(live, "config", "user.name", "fixture")
    _git(live, "config", "core.autocrlf", autocrlf)
    (live / "agent").mkdir()
    (live / "agent" / "moa_loop.py").write_text("patch target\n", encoding="utf-8", newline="")
    _git(live, "add", "-A")
    _git(live, "commit", "-qm", "baseline")
    return live


def make_recovery(tmp_path: pathlib.Path) -> pathlib.Path:
    """Миниатюрный recovery-репозиторий: печати + правила .gitattributes."""
    repo = tmp_path / "recovery"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "sealed_tool.py").write_text("print('hi')\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/sealed_tool.py")  # тестовый помощник: пишет строку печати
    return repo


def test_clean_fixture_reports_no_drift(tmp_path):
    report = ri.verify(repo=make_recovery(tmp_path), live=make_live(tmp_path))
    assert report.findings == ()
    assert report.exit_code() == 0


def test_verify_writes_nothing(tmp_path):
    """Инвариант шага 1: верификатор не мутирует ни один файл."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    ri.verify(repo=repo, live=live)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after
```

- [ ] **Step 2: Убедиться, что падают**

Run: `"C:/Users/tiki/AppData/Local/hermes/hermes-agent/.venv/Scripts/python.exe" -m pytest tools/tests/test_recovery_integrity.py -p no:cacheprovider --basetemp="C:/Users/tiki/AppData/Local/Temp/opencode/ptest-ri1" -q`
Ожидание: `ModuleNotFoundError: No module named 'recovery_integrity'`.

- [ ] **Step 3: Реализовать модуль, шов и отчёт**

```python
@dataclass(frozen=True)
class GitResult:
    rc: int
    stdout: str = ""
    stderr: str = ""


def git(*args: str, cwd: pathlib.Path | None = None) -> GitResult:
    """Единственный шов к git; никогда не бросает — rc говорит сам за себя."""
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return GitResult(rc=127, stderr=str(exc))
    return GitResult(proc.returncode, proc.stdout, proc.stderr)
```

`Finding`/`Report` — frozen dataclasses; `Report.blocked = any(f.severity == "block" for f in findings)`;
`exit_code()` → `1` если `blocked` иначе `0`. `verify()` пока возвращает `Report(())`; тестовый помощник `seal(repo, rel)` пишет/обновляет строку печати (только для тестов, не публичный интерфейс шага 1).

- [ ] **Step 4: Зелёные.** Тот же прогон → `2 passed`.

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0 (7 существующих тестов + новые).

---

### Task 2: `paths()` и временный мост к `live_tree_check`

**Files:** Modify `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

**Interfaces:** Produces `paths()` — девять путей; потребляется Task 4 и Task 5.

- [ ] **Step 1: Написать падающий тест**

```python
def test_scope_matches_live_tree_check_allowlist():
    """ВРЕМЕННЫЙ мост: пока live_tree_check жив, две копии scope не имеют права разойтись.

    Удаляется вместе с tools/live_tree_check.py в шаге 2.
    """
    source = (TOOLS_DIR / "live_tree_check.py").read_text(encoding="utf-8")
    assert set(ri.paths()) == ri._allowlist_from_source(source)
    assert len(ri.paths()) == 9
```

- [ ] **Step 2: Падает** (`AttributeError: paths`) → тот же прогон с `-k scope_matches`.

- [ ] **Step 3: Реализовать**

`paths()` возвращает кортеж из девяти путей в порядке патча; `_allowlist_from_source(text)` вытаскивает литералы из блока `ALLOWLIST = {...}` в исходнике `live_tree_check.py` (AST или регулярка по строкам с кавычками внутри блока — реализовать через `ast.parse` и обход `Assign`).

- [ ] **Step 4: Зелёные.**

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0.

---

### Task 3: Проверки печатей

**Files:** Modify `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

**Interfaces:** Consumes `sealed()`, `fresh_bytes()`. Produces находки `missing_seal`, `stale_seal`, `checkout_unstable` (все `block`).

**Правило (три проверки на каждую печать):**

1. файла нет → `missing_seal`, block;
2. `sha256(fresh_bytes(path))` ≠ дайджест из реестра → `stale_seal`, block;
3. `fresh_bytes(path)` ≠ байты на диске → `checkout_unstable`, block. Смысл: печать достоверна, только если объявленный режим git **не переписывает** эти байты при checkout. Это тот самый hazard, который уже случался: новый инструмент с LF на диске и без объявления в `.gitattributes` при `core.autocrlf=true` выезжает в клоне как CRLF, и печать расходится — локально этого не видно.

- [ ] **Step 1: Падающие тесты**

```python
def test_stale_seal_blocks(tmp_path):
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").write_text("print('changed')\n", encoding="utf-8", newline="")
    report = ri.verify(repo=repo, live=live)
    assert [f.flavour for f in report.findings] == ["stale_seal"]
    assert report.blocked and report.exit_code() == 1


def test_missing_sealed_file_blocks(tmp_path):
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").unlink()
    assert [f.flavour for f in ri.verify(repo=repo, live=live).findings] == ["missing_seal"]


def test_ledger_with_crlf_lines_reads_cleanly(tmp_path):
    """Реестр в репозитории — CRLF (`-text`), поэтому разбор обязан быть
    CRLF-совместимым. Наивный `split("\\n")` оставит `\\r` в имени файла и
    превратит каждую печать в ложный `missing_seal` — ровно то, что делает
    `sha256sum -c` из Git Bash на этом дереве."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    ledger = repo / "SHA256SUMS.txt"
    ledger.write_bytes(ledger.read_bytes().replace(b"\n", b"\r\n"))
    assert ri.verify(repo=repo, live=live).findings == ()


def test_undeclared_lf_file_is_checkout_unstable(tmp_path):
    """Точный hazard из фазы 0: LF на диске, объявления нет, autocrlf=true."""
    repo = make_recovery(tmp_path)
    target = repo / "tools" / "pending.py"
    target.write_text("x = 1\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("", encoding="utf-8", newline="")
    ri.seal(repo, "tools/pending.py")
    findings = ri.verify(repo=repo, live=make_live(tmp_path)).findings
    assert [f.flavour for f in findings] == ["checkout_unstable"]


def test_declared_lf_file_is_stable(tmp_path):
    """Негативный контроль: правило не должно блокировать правильно объявленный файл."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    assert ri.verify(repo=repo, live=live).findings == ()


def test_seal_unit_is_what_a_clone_produces(tmp_path):
    """Модель `fresh_bytes` сверяется с настоящим git, а не с её же логикой."""
    live = make_live(tmp_path)
    (live / "agent" / "tool.py").write_text("y = 2\n", encoding="utf-8", newline="")  # LF, не объявлен
    _git(live, "add", "-A"); _git(live, "commit", "-qm", "add tool")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(live), str(clone))
    assert (clone / "agent" / "tool.py").read_bytes() != (live / "agent" / "tool.py").read_bytes()
    assert ri.fresh_bytes(live / "agent" / "tool.py", live) == (clone / "agent" / "tool.py").read_bytes()
```

Тест `test_seal_unit_is_what_a_clone_produces` — это и есть причина, по которой выбран настоящий temp-репозиторий, а не фейковый git: он проверяет модель против поведения git.

- [ ] **Step 2: Падают** → `-k "seal or checkout_unstable"`.

- [ ] **Step 3: Реализовать `sealed()`, `fresh_bytes()`, три проверки**

`fresh_bytes(path, repo)`: прочитать байты; спросить `git("check-attr", "text", "eol", "--", rel, cwd=repo)`; если `text` ∈ {`set`, `auto`} или `eol == lf` → `raw.replace(b"\r\n", b"\n")`, иначе `raw`. Если `check-attr` недоступен (rc ≠ 0) — вернуть `raw` и добавить `warn`-находку `flavour="git_unavailable"`.

`sealed(repo)`: читать `SHA256SUMS.txt` **с универсальными переводами строк** (`read_text(encoding="utf-8").splitlines()`), формат строки — `<hex> *<path>`, и `\r` не должен оставаться в `path`; иначе все печати становятся ложными `missing_seal` (тест `test_ledger_with_crlf_lines_reads_cleanly`).

- [ ] **Step 4: Зелёные.**

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0.

---

### Task 4: Чистота live-дерева (портирование `live_tree_check`)

**Files:** Modify `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

**Interfaces:** Consumes `paths()`. Produces находку `live_tree_noise` (block) с полем `detail`, различающим tracked (позже откатываемо) и untracked (никогда не удаляется автоматически).

- [ ] **Step 1: Падающие тесты**

```python
def test_tracked_noise_outside_scope_blocks(tmp_path):
    live = make_live(tmp_path)
    (live / "hermes_cli").mkdir()
    (live / "hermes_cli" / "other.py").write_text("dirty\n", encoding="utf-8", newline="")
    findings = ri.verify(repo=make_recovery(tmp_path), live=live).findings
    assert [f.flavour for f in findings] == ["live_tree_noise"]
    assert "tracked" in findings[0].detail


def test_dirty_file_inside_scope_is_not_noise(tmp_path):
    live = make_live(tmp_path)
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live).findings == ()


def test_untracked_noise_is_reported_and_kept(tmp_path):
    live = make_live(tmp_path)
    stray = live / "scratch.txt"
    stray.write_text("junk\n", encoding="utf-8", newline="")
    report = ri.verify(repo=make_recovery(tmp_path), live=live)
    assert [f.flavour for f in report.findings] == ["live_tree_noise"]
    assert "untracked" in report.findings[0].detail
    assert stray.exists()  # verify() не удаляет и не откатывает
```

- [ ] **Step 2: Падают.**

- [ ] **Step 3: Реализовать** — портировать `status_lines()` и разделение tracked/untracked из `tools/live_tree_check.py`, но **без** `--fix`: шаг 1 только сообщает. Шум внутри `paths()` шумом не считается.

- [ ] **Step 4: Зелёные.**

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0.

---

### Task 5: Применимость патча

**Files:** Modify `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

**Interfaces:** Consumes `paths()`, `git()`. Produces находку `patch_drift` (block) или отсутствие находки.

- [ ] **Step 1: Падающие тесты**

```python
def _patch_for(live: pathlib.Path) -> pathlib.Path:
    """Патч, который применяется к baseline и перестаёт reverse-apply'иться после правки."""
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    diff = _git(live, "diff", "--", "agent/moa_loop.py").stdout
    (live / "agent" / "moa_loop.py").write_text("baseline\n", encoding="utf-8", newline="")
    out = live.parent / "auto-moa-current.patch"
    out.write_text(diff, encoding="utf-8", newline="")
    return out


def test_patch_applies_cleanly_when_intact(tmp_path):
    live = make_live(tmp_path)
    patch = _patch_for(live)
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch).findings == ()


def test_patch_drift_blocks(tmp_path):
    live = make_live(tmp_path)
    patch = _patch_for(live)
    report = ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch)  # рабочее дерево = baseline
    assert [f.flavour for f in report.findings] == ["patch_drift"]
    assert report.blocked
```

- [ ] **Step 2: Падают** (`TypeError: verify() got an unexpected keyword argument 'patch'`).

- [ ] **Step 3: Реализовать** — `verify(..., patch: Path | None = None)`; при `patch is None` берётся `repo / "auto-moa-current.patch"`. Проверка: `git("apply", "--reverse", "--check", str(patch), cwd=live)`; `rc != 0` → `patch_drift`. Только `--check`: ни один шаг не применяет патч.

- [ ] **Step 4: Зелёные.**

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0.

---

### Task 6: CLI и отчёт

**Files:** Modify `tools/recovery_integrity.py`, `tools/tests/test_recovery_integrity.py`.

- [ ] **Step 1: Падающий тест**

```python
def test_cli_json_and_exit_codes(tmp_path):
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    ok = subprocess.run([sys.executable, str(TOOLS_DIR / "recovery_integrity.py"),
                         "--repo", str(repo), "--live", str(live), "--json"],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(ok.stdout)["findings"] == []

    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    bad = subprocess.run([sys.executable, str(TOOLS_DIR / "recovery_integrity.py"),
                          "--repo", str(repo), "--live", str(live)], capture_output=True, text=True)
    assert bad.returncode == 1 and "stale_seal" in bad.stdout


def test_cli_missing_repo_exits_2(tmp_path):
    proc = subprocess.run([sys.executable, str(TOOLS_DIR / "recovery_integrity.py"),
                           "--repo", str(tmp_path / "nope"), "--live", str(tmp_path / "nope2")],
                          capture_output=True, text=True)
    assert proc.returncode == 2
```

- [ ] **Step 2: Падают.**

- [ ] **Step 3: Реализовать `main(argv)`** — argparse с `--repo`, `--live`, `--json`; человекочитаемый рендер группирует находки по flavour с severity-префиксом; `--json` печатает `{"findings": [{flavour, severity, path, detail}], "blocked": bool}`; исключение в самом верификаторе → `2` и сообщение в stderr. `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` — как во всех инструментах репозитория (cp1251-консоль).

- [ ] **Step 4: Зелёные.**

- [ ] **Step 5: Полный гейт.** `cmd /c run-moa-tests.bat` → exit 0.

---

### Task 7: Само-запечатывание, приёмочный прогон, коммит

**Files:** Modify `SHA256SUMS.txt`, `.gitattributes`.

- [ ] **Step 1: Приёмочный прогон на реальном состоянии**

```bash
"C:/Users/tiki/AppData/Local/hermes/hermes-agent/.venv/Scripts/python.exe" tools/recovery_integrity.py
```

Ожидание: `0`, пустой отчёт. Если репорт что-то находит — это не «гейт мешает», это либо Task 0, либо новая находка; разбирать, а не ослаблять.

- [ ] **Step 2: Запечатать новый модуль и его тест вручную**

Добавить две строки в `SHA256SUMS.txt` (sha256 обоих файлов) **и** два объявления `text eol=lf` в `.gitattributes`. Пара «файл в реестре + файл в `.gitattributes`» должна быть согласована — именно это проверяет Task 3. Полный прогон проверки реестра → `ALL FRESH`.

- [ ] **Step 3: Финальные гейты**

`cmd /c run-moa-tests.bat` → exit 0; `python tools/moa_sync.py --check` → `PASS`; `cmd /c hermes-update.bat --check` → `HEALTHY` без WARNING; `git status --short` → ровно ожидаемые файлы.

- [ ] **Step 4: Коммит**

```bash
git add tools/recovery_integrity.py tools/tests/test_recovery_integrity.py SHA256SUMS.txt .gitattributes auto-moa-current.patch
git commit -m "feat(tools): read-only recovery verifier (seals, live-tree scope, patch applicability)"
```

---

## Что этот шаг намеренно НЕ делает

- Не подключает верификатор к `hermes-update.bat` и не включает блокировку — это шаг 2, вместе с удалением `tools/live_tree_check.py` и переносом её `--fix` в repair-адаптер.
- Не реализует `reseal()` и `export_patch()`: шаг 1 запечатывает себя **вручную** (Task 7 Step 2), и это честная демонстрация того самого двухсписочного ручного труда, который шаг 2 автоматизирует.
- Не отвечает на вопрос о config drift: это вопрос `moa_sync --check`, и он остаётся там (см. `CONTEXT.md`, «Two different questions»).
- Не решает задачу `hermes_fleet` (разрешение корней и профилей): `repo_root()` и `live_tree()` здесь минимальны, перекрываемы аргументами и подлежат выпуску в отдельный модуль, когда за них возьмутся.
