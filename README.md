# Research Dashboards

Notion research dashboards exported to Markdown and published as a Hugo site on
GitHub Pages. The export runs on a schedule (and on demand) via GitHub Actions.

Two dashboards are published today, and adding more is a config-only change:

- **[AI Bubble Risk Dashboard](https://app.notion.com/p/AI-Bubble-Risk-Dashboard-3d1b7fcffbda81f0a1c2f2a3324912cd)** — weekly AI-bubble risk score, burst probability and indicator signals.
- **[Fundamental Opportunity Dashboard](https://app.notion.com/p/Fundamental-Opportunity-Dashboard-3d2b7fcffbda8121aceac5cc77256a83)** — weekday 100+ stock fundamental screen: per-ticker snapshots, trade ideas and observations.

## How it works

```
Notion pages ──(scripts/export_notion.py)──▶ content/*.md ──(hugo)──▶ GitHub Pages
                        ▲
             GitHub Actions: daily cron + manual "Run workflow"
```

Each dashboard is a single Notion **page** containing several inline databases
(a runs-style database plus a few table databases) and optional prose. The whole
exporter is driven by the `DASHBOARDS` list at the top of
`scripts/export_notion.py`; each dashboard becomes its own `/<slug>/` section and
the home page is a generic hub linking to them all:

| Output | Source |
|---|---|
| `content/_index.md` | Generic hub: one card per dashboard with its latest reading |
| `content/<slug>/_index.md` | Dashboard home: latest reading, an inline-SVG trend, recent runs, and the page's prose |
| `content/<slug>/runs/<date>.md` | One page per row of the dashboard's runs database |
| `content/<slug>/<section>/_index.md` | A table section (observations, snapshots, trade ideas, forecasts…) |
| `content/<slug>/indicators/_index.md` | Interactive indicator table (AI Bubble only) |
| `content/<slug>/methodology.md` | A methodology child page, if present |
| `data/history/<slug>.json` | Durable run time-series — the trend source of truth |
| `data/indicators.json` | Interactive-indicator data read by the Hugo shortcode |

The workflow commits content changes back to `main`, then Hugo (PaperMod theme)
builds the site and deploys it to GitHub Pages. Trend charts are plain inline
SVGs generated at export time — no JavaScript or external chart library.

## Adding a dashboard

Append an entry to `DASHBOARDS` in `scripts/export_notion.py`:

- `slug`, `title`, `menu_name`, `weight`, `tagline`
- `page_id` (+ optional `page_id_env` for a secret override)
- a `runs` block (which database is the runs series, plus its headline/trend/columns)
- a `sections` list (`kind: "table"` or `kind: "indicators"`, matched by title keyword)
- `methodology_keywords` (empty to skip)

Then add a matching `[[menu.main]]` entry in `hugo.toml`.

## One-time setup

### 1. Notion integration
- <https://www.notion.so/my-integrations> → **New integration** (internal) →
  copy the **Internal Integration Secret** (`NOTION_API_KEY`).
- Open **each** dashboard page in Notion → **⋯ → Connections → Connect to** your
  integration. This grants access to the page *and* its inline databases.

### 2. Repository secrets
Repo → **Settings → Secrets and variables → Actions**:
- `NOTION_API_KEY` — the integration secret *(required)*
- `NOTION_PAGE_ID` — *(optional)* overrides the AI Bubble page id.
- `NOTION_FUNDAMENTAL_PAGE_ID` — *(optional)* overrides the Fundamental page id.

### 3. Enable GitHub Pages
Repo → **Settings → Pages → Source: GitHub Actions**.

### 4. First run
Repo → **Actions → Export Notion & Publish → Run workflow**.
Publishes to `https://luarss.github.io/chatgpt-reports/`.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env is gitignored — put at least NOTION_API_KEY here:
#   NOTION_API_KEY=secret_xxx
#   NOTION_PAGE_ID=3d1b7fcffbda81f0a1c2f2a3324912cd              # optional
#   NOTION_FUNDAMENTAL_PAGE_ID=3d2b7fcffbda8121aceac5cc77256a83  # optional
set -a; source .env; set +a

python scripts/export_notion.py   # writes content/**
hugo server                       # preview at http://localhost:1313
```

## Schedule

Edit the `cron` line in `.github/workflows/export-and-publish.yml`
(default `0 6 * * *` = daily 06:00 UTC). The `workflow_dispatch` manual button
stays regardless.

## Notes
- The exporter wipes and rebuilds each `content/<slug>` section every run, so
  deletions in Notion propagate to the site. `data/history/<slug>.json` is the
  one durable store and is intentionally **not** wiped — it preserves the trend
  even when a run is edited or removed in Notion.
- Databases are matched by title keyword (e.g. `weekly run`, `daily run`,
  `indicator`, `snapshot`, `trade idea`, `observation`, `forecast`), so renaming
  them in Notion needs a matching tweak to the dashboard's config.
- Table columns per section are defined by the `*_COLS` lists in the script;
  unknown columns are skipped, so schema changes degrade gracefully.
