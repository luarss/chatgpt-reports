# AI Bubble Risk Dashboard

The [AI Bubble Risk Dashboard](https://app.notion.com/p/AI-Bubble-Risk-Dashboard-3d1b7fcffbda81f0a1c2f2a3324912cd)
Notion page, exported to Markdown and published as a Hugo site on GitHub Pages.
The export runs on a schedule (and on demand) via GitHub Actions.

## How it works

```
Notion page ──(scripts/export_notion.py)──▶ content/*.md ──(hugo)──▶ GitHub Pages
                        ▲
             GitHub Actions: daily cron + manual "Run workflow"
```

The source is a single Notion **page** containing four inline databases plus a
methodology child page. The exporter discovers them from the page id and writes:

| Output | Source |
|---|---|
| `content/_index.md` | Dashboard home: latest score, an inline-SVG risk-score trend, recent runs, and the page's Purpose/Workflow/Interpretation prose |
| `content/runs/<date>.md` | One page per row of **AI Bubble — Weekly Runs** |
| `content/indicators/_index.md` | Table from **AI Bubble — Indicators** |
| `content/observations/_index.md` | Table from **AI Bubble — Observations** |
| `content/forecasts/_index.md` | Table from **AI Bubble — Forecasts** |
| `content/methodology.md` | The **Data Model & Methodology** child page |

The workflow commits content changes back to `main`, then Hugo (PaperMod theme)
builds the site and deploys it to GitHub Pages. The trend chart is a plain inline
SVG generated at export time — no JavaScript or external chart library.

## One-time setup

### 1. Notion integration
- <https://www.notion.so/my-integrations> → **New integration** (internal) →
  copy the **Internal Integration Secret** (`NOTION_API_KEY`).
- Open the dashboard page in Notion → **⋯ → Connections → Connect to** your
  integration. This grants access to the page *and* its inline databases.

### 2. Repository secrets
Repo → **Settings → Secrets and variables → Actions**:
- `NOTION_API_KEY` — the integration secret *(required)*
- `NOTION_PAGE_ID` — *(optional)* overrides the dashboard page id baked into
  `scripts/export_notion.py` (`DEFAULT_PAGE_ID`). Set only to point at a
  different page.

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
#   NOTION_PAGE_ID=3d1b7fcffbda81f0a1c2f2a3324912cd   # optional
set -a; source .env; set +a

python scripts/export_notion.py   # writes content/**
hugo server                       # preview at http://localhost:1313
```

## Schedule

Edit the `cron` line in `.github/workflows/export-and-publish.yml`
(default `0 6 * * *` = daily 06:00 UTC). The `workflow_dispatch` manual button
stays regardless.

## Notes
- The exporter wipes and rebuilds `content/runs|indicators|observations|forecasts`
  and the top-level pages each run, so deletions in Notion propagate to the site.
- Databases are matched by title keyword (`weekly run`, `indicator`,
  `observation`, `forecast`), so renaming them in Notion needs a matching tweak
  in `discover()`.
- Table columns per section are defined by `INDICATOR_COLS` / `OBSERVATION_COLS`
  / `FORECAST_COLS` in the script; unknown columns are skipped, so schema changes
  degrade gracefully.
