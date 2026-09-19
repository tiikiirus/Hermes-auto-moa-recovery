# Stage B calibration sample

15 too_short + 15 no_quote downgraded lines. For each: keep or lower threshold?
Label: OK-downgrade (real missing evidence) | FP (honest evidence, threshold too strict).

## too_short (has quote, below 12 chars / 2 tokens; hit = short quote verbatim in corpus)
- [20260918_154224_88db5f.jsonl] hit=True quotes=['.cursor/mcp.json', 'atxp-*']
  > - Cursor's `.cursor/mcp.json` exists and contains only `atxp-*` servers; no GitHub MCP configuration is present there.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['c:\\users\\tiki\\appdata\\roaming\\claude\\claude_desktop_config.json']
  > - Claude Desktop config is not at `C:\Users\tiki\AppData\Roaming\Claude\claude_desktop_config.json`.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['ghcr.io/github/github-mcp-server:latest', 'keen_hopper', 'dreamy_snyder']
  > - Two containers use `ghcr.io/github/github-mcp-server:latest`: `keen_hopper` (Exited (0)) and `dreamy_snyder` (Up 5 minutes)
- [20260918_154224_88db5f.jsonl] hit=True quotes=['config.yaml']
  > - `config.yaml` contains extensive MCP server configurations but no explicit GitHub MCP entry in the visible portion
- [20260918_154224_88db5f.jsonl] hit=True quotes=['mcp-stderr.log', 'max-dev-docs', 'mcp.server.fastmcp']
  > - `mcp-stderr.log` shows other MCP errors (`max-dev-docs`: missing `mcp.server.fastmcp` module)
- [20260918_154224_88db5f.jsonl] hit=True quotes=['keen_hopper', 'dreamy_snyder', 'ghcr.io/github/github-mcp-server:latest']
  > - В логах контейнер `keen_hopper` (Exited (0) 11 минут назад) и `dreamy_snyder` (Up 5 минут) используют образ `ghcr.io/github/github-mcp-server:latest`.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['keen_hopper', 'session_id=""', 'dreamy_snyder']
  > - У `keen_hopper` в логах пустой `session_id=""` и мгновенный дисконнект; у `dreamy_snyder` корректные токен-скопы и работающая сессия.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['github_token']
  > - Переменная `GITHUB_TOKEN` не установлена в текущем окружении shell.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['c:\\users\\tiki\\.cursor\\mcp.json']
  > - В конфигурации Cursor (`C:\Users\tiki\.cursor\mcp.json`) нет GitHub MCP, только atxp-серверы.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['config.yaml', 'fantrax', 'github-mcp', 'ghcr.io/github']
  > - В текущем `config.yaml` профиля `fantrax` и в проверенных бэкапах нет секции с `github-mcp` или `ghcr.io/github`.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['fantrax']
  > - В автозагрузке Windows 7 скриптов Hermes Gateway для разных профилей, включая `fantrax`.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['session_id=""', 'disconnected', 'ended']
  > - Логи keen_hopper: `session_id=""` → `disconnected` → `ended` за ~250 мс (15:40:55.638–.640).
- [20260918_154224_88db5f.jsonl] hit=True quotes=['ghcr.io/github/github-mcp-server:latest']
  > - Образ `ghcr.io/github/github-mcp-server:latest` существует локально.
- [20260918_154224_88db5f.jsonl] hit=True quotes=['keen_hopper', 'dreamy_snyder']
  > - Контейнер `keen_hopper` exited(0) в 15:40:55, `dreamy_snyder` Up 5 минут (запущен 15:47:35).
- [20260918_154224_88db5f.jsonl] hit=True quotes=['github_personal_access_token', 'dreamy_snyder']
  > - `GITHUB_PERSONAL_ACCESS_TOKEN` присутствует в env `dreamy_snyder`.

## no_quote (no quoted span at all)
- [20260918_154224_88db5f.jsonl]
  > - Cursor settings.json has only atxp-search, atxp-docs, atxp servers — no github MCP.
- [20260918_154224_88db5f.jsonl]
  > - Claude config not found at default path; Cursor mcp.json not found.
- [20260910_115202_f1c329.jsonl]
  > - Available sort options: по просмотрам (by views), по репостам в каналы (by reposts to channels), по реакциям (by reactions)
- [20260910_115202_f1c329.jsonl]
  > - Constraint: по пересылкам - недоступно в Макс (forwarding sort is not available in Max)
- [20260910_115202_f1c329.jsonl]
  > - Task NEWLOG-704 exists at `C:\qa-helper\knowledge_base\mxstat\tasks\NEWLOG-704\` with files: README.md, checklist_and_cases.md, INDEX.md, BUG-046_ratings_posts_tgstat_title.md.
- [20260910_115202_f1c329.jsonl]
  > - Category links present: blogs, news, economics, business, travels, politics, education, etc.
- [20260910_115202_f1c329.jsonl]
  > - Meta description/og tags are correct, no TGStat/Telegram branding.
- [20260910_115202_f1c329.jsonl]
  > - Category slugs visible in sidebar (blogs, news, economics, etc.); periods visible (pt, py, py2, p7d, pcw, ppw, pcm, ppm).
- [20260910_115202_f1c329.jsonl]
  > - 65 post cards parsed on current page.
- [20260910_115202_f1c329.jsonl]
  > - Количество карточек: views=65, quotes=100, reactions=74; все сортировки убывающие (desc=True), missing метрик=0.
- [20260910_115202_f1c329.jsonl]
  > - На дев-стенде `
- [20260910_115202_f1c329.jsonl]
  > - All periods return 200; empty-state hint text exists for some periods on dev but not observed on prod samples.
- [20260910_115202_f1c329.jsonl]
  > - No pagination links present on prod pages (hard Top-100).
- [20260910_115202_f1c329.jsonl]
  > - Key findings verified on production:
- [20260910_115202_f1c329.jsonl]
  > - Footer contains a «Рейтинг публикаций» link (previous open question).
