#!/usr/bin/env python3
"""Export one or more Notion dashboard pages into a Hugo site.

Each *dashboard* is a single Notion page whose body contains several inline
databases (a runs-style database plus a few table databases) and optional prose.
The exporter is driven by the DASHBOARDS config below: adding a new dashboard is
a matter of adding one entry — no new code paths.

Site layout (one section per dashboard, plus a generic hub home page):

  content/_index.md                generic hub: one card per dashboard
  content/<slug>/_index.md         dashboard home: latest reading, trend, runs
  content/<slug>/runs/<date>.md    one page per run
  content/<slug>/<section>/_index.md   table sections (observations, snapshots…)
  content/<slug>/indicators/_index.md  interactive indicator table (if any)
  content/<slug>/methodology.md    rendered from a methodology child page (if any)
  data/indicators.json             interactive-indicator source (Hugo shortcode)
  data/history/<slug>.json         durable run time-series (trend source of truth)

Environment:
  NOTION_API_KEY   Notion internal-integration secret (required)
  NOTION_PAGE_ID / NOTION_FUNDAMENTAL_PAGE_ID  optional per-dashboard page-id
                   overrides (see each dashboard's "page_id_env").
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from notion_client import Client

CONTENT_DIR = Path("content")
DATA_DIR = Path("data")

# --------------------------------------------------------------------------- #
# Column order for each table section; missing columns are silently skipped.
# --------------------------------------------------------------------------- #
OBSERVATION_COLS = ["Observation Date", "Indicator Code", "Entity", "Period",
                    "Value", "Value Text", "Unit", "Signal", "QoQ Change",
                    "YoY Change", "Source", "Source Type", "Confidence",
                    "Retrieved Date", "Notes"]
FORECAST_COLS = ["Forecast", "Category", "Prediction", "Probability",
                 "Forecast Date", "Resolution Date", "Resolution Criteria",
                 "Outcome", "Resolved Date", "Brier Score", "Evidence URL"]

SNAPSHOT_COLS = ["Rank", "Ticker", "Company", "Sector", "Score", "Bias",
                 "Confidence", "Actionable", "Catalyst", "Key Risk",
                 "Revenue Signal", "Margin Signal", "FCF Signal",
                 "Balance Sheet Signal", "Valuation Context", "Run Date",
                 "Source URL"]
TRADE_IDEA_COLS = ["Rank", "Ticker", "Idea", "Stance", "Score", "Confidence",
                   "Time Horizon", "Thesis", "Catalyst", "Entry Context",
                   "Valuation", "Invalidation", "Downside Risks", "Run Date",
                   "Source URL"]
FUND_OBSERVATION_COLS = ["Observed Date", "Ticker", "Metric", "Value", "Period",
                         "YoY QoQ", "Signal", "Category", "Confidence",
                         "Source Type", "Source URL", "Notes"]

# --------------------------------------------------------------------------- #
# Dashboard configuration
# --------------------------------------------------------------------------- #
# Each dashboard maps its inline databases by a title keyword to a role:
#   runs        -> per-row pages + dashboard headline/trend (exactly one)
#   indicators  -> interactive shortcode table
#   table       -> a plain Markdown table section
# `methodology_keywords` matches a child page rendered as its own page.
DASHBOARDS = [
    {
        "slug": "ai-bubble",
        "title": "AI Bubble Risk Dashboard",
        "menu_name": "AI Bubble",
        "weight": 10,
        "page_id": "3d1b7fcffbda81f0a1c2f2a3324912cd",
        "page_id_env": "NOTION_PAGE_ID",
        "tagline": "Weekly AI-bubble risk scoring: an evidence-based score, "
                   "burst probability and indicator signals.",
        "runs": {
            "keyword": "weekly run",
            "section_title": "Weekly Runs",
            "section_intro": "Weekly Bubble Risk scores and probabilities.",
            "detail_title_prefix": "Weekly Run",
            "title_field": "Run",
            "date_field": "Run Date",
            "trend_field": "Risk Score",
            "trend_label": "Risk Score trend",
            "trend_legacy_key": "riskScore",
            "front_matter": [
                ("riskScore", "Risk Score"), ("riskLevel", "Risk Level"),
                ("burstProbability", "Burst Probability"), ("direction", "Direction"),
            ],
            "headline": [
                ("Risk Score", "Risk Score"), ("Risk Level", "Risk Level"),
                ("Direction", "Direction"),
                ("Burst Probability (18–24mo)", "Burst Probability"),
                ("Adoption Collapse Probability", "Adoption Collapse Probability"),
            ],
            "recent_cols": ["Run Date", "Risk Score", "Score Change",
                            "Burst Probability", "Risk Level", "Direction"],
            "detail_metrics": [
                ("Risk Score", "Risk Score"), ("Prior Risk Score", "Prior Risk Score"),
                ("Score Change", "Score Change"), ("Risk Level", "Risk Level"),
                ("Direction", "Direction"), ("Burst Probability", "Burst Probability"),
                ("Adoption Collapse Probability", "Adoption Collapse Probability"),
                ("Method Version", "Method Version"),
            ],
            "detail_prose": [("Thesis", "Thesis"), ("Key Changes", "Key Changes")],
            "report_url_field": "Report URL",
        },
        "sections": [
            {"kind": "indicators", "keyword": "indicator", "slug": "indicators"},
            {"kind": "table", "slug": "observations", "keyword": "observation",
             "title": "Observations", "columns": OBSERVATION_COLS,
             "sort": "Observation Date",
             "intro": "Immutable dated observations with provenance and confidence."},
            {"kind": "table", "slug": "forecasts", "keyword": "forecast",
             "title": "Forecasts", "columns": FORECAST_COLS,
             "sort": "Forecast Date",
             "intro": "Explicit forecasts tracked for later Brier-score calibration."},
        ],
        "methodology_keywords": ["methodology", "data model"],
    },
    {
        "slug": "fundamental",
        "title": "Fundamental Opportunity Dashboard",
        "menu_name": "Fundamental Screen",
        "weight": 20,
        "page_id": "3d2b7fcffbda8121aceac5cc77256a83",
        "page_id_env": "NOTION_FUNDAMENTAL_PAGE_ID",
        "tagline": "Weekday 100+ stock fundamental screen: per-ticker snapshots, "
                   "trade ideas and dated observations.",
        "runs": {
            "keyword": "daily run",
            "section_title": "Daily Runs",
            "section_intro": "Daily fundamental screen runs with market context.",
            "detail_title_prefix": "Daily Run",
            "title_field": "Run",
            "date_field": "Run Date",
            "trend_field": "Top Score",
            "trend_label": "Top Score trend",
            "trend_legacy_key": None,
            "front_matter": [
                ("topTicker", "Top Ticker"), ("topScore", "Top Score"),
                ("actionableLongs", "Actionable Longs"),
                ("actionableShorts", "Actionable Shorts"),
            ],
            "headline": [
                ("Top Ticker", "Top Ticker"), ("Top Score", "Top Score"),
                ("Actionable Longs", "Actionable Longs"),
                ("Actionable Shorts", "Actionable Shorts"),
                ("Universe Size", "Universe Size"),
            ],
            "recent_cols": ["Run Date", "Top Ticker", "Top Score",
                            "Actionable Longs", "Actionable Shorts", "Universe Size"],
            "detail_metrics": [
                ("Top Ticker", "Top Ticker"), ("Top Score", "Top Score"),
                ("Actionable Longs", "Actionable Longs"),
                ("Actionable Shorts", "Actionable Shorts"),
                ("Universe Size", "Universe Size"),
                ("Method Version", "Method Version"),
            ],
            "detail_prose": [("Market Context", "Market Context")],
            "report_url_field": "Report URL",
        },
        "sections": [
            {"kind": "table", "slug": "snapshots", "keyword": "snapshot",
             "title": "Stock Snapshots", "columns": SNAPSHOT_COLS, "sort": "Score",
             "intro": "Per-ticker fundamental snapshots from the latest screen."},
            {"kind": "table", "slug": "trade-ideas", "keyword": "trade idea",
             "title": "Trade Ideas", "columns": TRADE_IDEA_COLS, "sort": "Score",
             "intro": "Actionable long/short ideas with thesis, catalyst and risks."},
            {"kind": "table", "slug": "observations", "keyword": "observation",
             "title": "Observations", "columns": FUND_OBSERVATION_COLS,
             "sort": "Observed Date",
             "intro": "Immutable dated observations with provenance and confidence."},
        ],
        "methodology_keywords": [],
    },
]


# --------------------------------------------------------------------------- #
# Notion value helpers
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-") or "untitled"


def rich_text_to_md(rich: list) -> str:
    out = []
    for span in rich:
        content = span.get("plain_text", "")
        if not content:
            continue
        ann = span.get("annotations", {})
        if ann.get("code"):
            content = f"`{content}`"
        else:
            if ann.get("bold"):
                content = f"**{content}**"
            if ann.get("italic"):
                content = f"*{content}*"
            if ann.get("strikethrough"):
                content = f"~~{content}~~"
        if span.get("href"):
            content = f"[{content}]({span['href']})"
        out.append(content)
    return "".join(out)


def extract_property(prop: dict):
    """Return a Python-native value for a Notion property."""
    ptype = prop["type"]
    val = prop.get(ptype)
    if ptype in ("title", "rich_text"):
        return "".join(s.get("plain_text", "") for s in (val or []))
    if ptype in ("select", "status"):
        return val.get("name") if val else None
    if ptype == "multi_select":
        return [o["name"] for o in (val or [])]
    if ptype == "date":
        return val.get("start") if val else None
    if ptype in ("checkbox", "number", "url", "created_time", "last_edited_time"):
        return val
    if ptype == "people":
        return [p.get("name", "") for p in (val or [])]
    return None


def prop_value(props: dict, name: str):
    return extract_property(props[name]) if name in props else None


def yaml_escape(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt_date(value) -> str:
    """Prettify an ISO date/datetime for display: drop seconds and timezone."""
    text = str(value or "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", text)
    if not m:
        return text
    return f"{m.group(1)} {m.group(2)}".strip() if m.group(2) else m.group(1)


def cell(props: dict, name: str) -> str:
    """Format a property as a Markdown table cell (pipes/newlines escaped)."""
    v = prop_value(props, name)
    if v is None:
        text = ""
    elif isinstance(v, bool):
        text = "✓" if v else ""
    elif isinstance(v, list):
        text = ", ".join(str(x) for x in v)
    elif isinstance(v, float):
        text = f"{v:g}"
    else:
        text = fmt_date(v) if isinstance(v, str) else str(v)
    return text.replace("|", "\\|").replace("\n", "<br>")


def blocks_to_md(client: Client, block_id: str, depth: int = 0) -> str:
    lines: list[str] = []
    indent = "  " * depth
    cursor = None
    numbered = 0
    while True:
        resp = client.blocks.children.list(block_id=block_id, start_cursor=cursor)
        for block in resp["results"]:
            btype = block["type"]
            data = block.get(btype, {})
            text = rich_text_to_md(data.get("rich_text", [])) if "rich_text" in data else ""
            if btype != "numbered_list_item":
                numbered = 0

            if btype == "paragraph":
                lines.append(f"{indent}{text}\n" if text else "")
            elif btype == "heading_1":
                lines.append(f"{indent}## {text}\n")   # demote H1 to keep page title unique
            elif btype == "heading_2":
                lines.append(f"{indent}### {text}\n")
            elif btype == "heading_3":
                lines.append(f"{indent}#### {text}\n")
            elif btype == "bulleted_list_item":
                lines.append(f"{indent}- {text}")
            elif btype == "numbered_list_item":
                numbered += 1
                lines.append(f"{indent}{numbered}. {text}")
            elif btype == "to_do":
                lines.append(f"{indent}- [{'x' if data.get('checked') else ' '}] {text}")
            elif btype == "quote":
                lines.append(f"{indent}> {text}\n")
            elif btype == "callout":
                emoji = (data.get("icon") or {}).get("emoji", "")
                lines.append(f"{indent}> {emoji} {text}\n")
            elif btype == "code":
                lines.append(f"{indent}```{data.get('language', '')}\n{text}\n{indent}```\n")
            elif btype == "divider":
                lines.append(f"{indent}---\n")
            elif btype == "image":
                src = data.get("external", {}).get("url") or data.get("file", {}).get("url", "")
                lines.append(f"{indent}![{rich_text_to_md(data.get('caption', []))}]({src})\n")
            elif btype == "bookmark":
                url = data.get("url", "")
                lines.append(f"{indent}[{url}]({url})\n")
            elif btype in ("child_database", "child_page"):
                pass  # handled separately at the top level
            elif text:
                lines.append(f"{indent}{text}\n")

            if block.get("has_children") and btype not in ("code", "child_database", "child_page"):
                child = blocks_to_md(client, block["id"], depth + 1)
                if child:
                    lines.append(child)
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return "\n".join(lines)


def query_all(client: Client, database_id: str) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    while True:
        resp = client.databases.query(database_id=database_id, start_cursor=cursor)
        rows.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return rows


def sort_rows(rows: list[dict], key: str, reverse: bool = True) -> None:
    """Sort rows by a property in place, tolerating rows where it is missing/None.

    The (present, value) tuple keeps None values grouped together so a numeric
    column with blanks never compares None against a number.
    """
    def sk(r):
        v = prop_value(r["properties"], key)
        return (v is not None, v if v is not None else "")
    rows.sort(key=sk, reverse=reverse)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover(client: Client, cfg: dict) -> dict:
    """Map a dashboard page's child databases and methodology child page by keyword."""
    runs_id = None
    sections: dict[str, str] = {}          # section slug -> database id
    methodology_id = None
    keywords = [(s["keyword"], s["slug"]) for s in cfg["sections"]]

    cursor = None
    while True:
        resp = client.blocks.children.list(block_id=cfg["page_id"], start_cursor=cursor)
        for b in resp["results"]:
            if b["type"] == "child_database":
                title = b["child_database"].get("title", "").lower()
                if cfg["runs"]["keyword"] in title:
                    runs_id = b["id"]
                    continue
                for keyword, slug in keywords:
                    if keyword in title:
                        sections[slug] = b["id"]
                        break
            elif b["type"] == "child_page":
                title = b["child_page"].get("title", "").lower()
                if any(k in title for k in cfg["methodology_keywords"]):
                    methodology_id = b["id"]
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return {"runs_id": runs_id, "sections": sections, "methodology_id": methodology_id}


# --------------------------------------------------------------------------- #
# Rendering primitives
# --------------------------------------------------------------------------- #
def front_matter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None or v == "":
            continue
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(f"  - {yaml_escape(x)}" for x in v)
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {yaml_escape(v)}")
    lines.append("---\n")
    return "\n".join(lines)


def render_table(rows: list[dict], columns: list[str]) -> str:
    """Render rows as a Markdown table, keeping only columns present in the schema."""
    if not rows:
        return "_No entries yet._\n"
    present = [c for c in columns if any(c in r["properties"] for r in rows)]
    if not present:
        present = list(rows[0]["properties"].keys())
    header = "| " + " | ".join(present) + " |"
    sep = "| " + " | ".join("---" for _ in present) + " |"
    body = []
    for r in rows:
        body.append("| " + " | ".join(cell(r["properties"], c) for c in present) + " |")
    return "\n".join([header, sep, *body]) + "\n"


def sparkline_svg(series: list[tuple[str, float]], label: str) -> str:
    """Inline SVG line chart of (label, value) points. No external deps."""
    pts_data = [(lbl, v) for lbl, v in series if v is not None]
    if not pts_data:
        return ""
    values = [v for _, v in pts_data]
    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1.0
    w, h, pad = 680, 200, 36
    n = len(pts_data)

    def px(i: int) -> float:
        return pad + (i * (w - 2 * pad) / max(n - 1, 1))

    def py(v: float) -> float:
        return h - pad - ((v - vmin) / span) * (h - 2 * pad)

    poly = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, (_, v) in enumerate(pts_data))
    dots = "".join(
        f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3.5" fill="#e5484d"/>'
        f'<title>{lbl}: {v:g}</title>'
        for i, (lbl, v) in enumerate(pts_data)
    )
    line = (f'<polyline fill="none" stroke="#e5484d" stroke-width="2.5" '
            f'points="{poly}"/>' if n > 1 else "")
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{label}" '
        f'style="max-width:100%;height:auto;font-family:system-ui,sans-serif">'
        f'<text x="{pad}" y="20" fill="currentColor" font-size="13" '
        f'font-weight="600">{label}</text>'
        f'<text x="{pad}" y="{py(vmax):.1f}" fill="currentColor" font-size="11" '
        f'opacity="0.6" dx="-4" text-anchor="end">{vmax:g}</text>'
        f'<text x="{pad}" y="{py(vmin):.1f}" fill="currentColor" font-size="11" '
        f'opacity="0.6" dx="-4" text-anchor="end">{vmin:g}</text>'
        f'{line}{dots}</svg>'
    )


def run_slug(run_date, used: set) -> str:
    """Stable, de-duplicated slug from a run's date (handles intra-day timestamps)."""
    raw = str(run_date or "run")
    if "T" in raw:
        day, rest = raw.split("T", 1)
        base = f"{day}-{rest[:5].replace(':', '')}"   # e.g. 2026-09-05-1322
    else:
        base = raw
    slug = slugify(base)
    candidate, i = slug, 2
    while candidate in used:
        candidate = f"{slug}-{i}"
        i += 1
    used.add(candidate)
    return candidate


# --------------------------------------------------------------------------- #
# Runs (per-row pages + durable history)
# --------------------------------------------------------------------------- #
def export_runs(client: Client, db_id: str, section_dir: Path, cfg: dict) -> list[dict]:
    rc = cfg["runs"]
    rows = query_all(client, db_id)
    sort_rows(rows, rc["date_field"])
    runs_dir = section_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "_index.md").write_text(
        front_matter({"title": rc["section_title"]}) + f"\n{rc['section_intro']}\n",
        encoding="utf-8",
    )

    used: set = set()
    for r in rows:
        p = r["properties"]
        run_date = prop_value(p, rc["date_field"])
        title = prop_value(p, rc["title_field"]) or run_date or "run"
        slug = run_slug(run_date, used)
        fm_fields = {"title": f"{rc['detail_title_prefix']} — {title}", "date": run_date}
        for key, field in rc["front_matter"]:
            fm_fields[key] = prop_value(p, field)
        fm = front_matter(fm_fields)

        body = ["| Metric | Value |", "| --- | --- |"]
        for label, field in rc["detail_metrics"]:
            val = prop_value(p, field)
            if val is not None and val != "":
                body.append(f"| {label} | {val} |")
        for label, field in rc["detail_prose"]:
            val = prop_value(p, field)
            if val:
                body.append(f"\n### {label}\n\n{val}\n")
        report_url = prop_value(p, rc["report_url_field"])
        if report_url:
            body.append(f"\n[Full report]({report_url})\n")
        page_body = blocks_to_md(client, r["id"])
        if page_body.strip():
            body.append("\n" + page_body)
        (runs_dir / f"{slug}.md").write_text(fm + "\n" + "\n".join(body) + "\n", encoding="utf-8")

    return rows


def run_record(props: dict, rc: dict) -> dict:
    """Durable, JSON-friendly record of one run: its date and trend value."""
    return {
        "date": prop_value(props, rc["date_field"]),
        "metric": rc["trend_field"],
        "value": prop_value(props, rc["trend_field"]),
    }


def history_path(slug: str) -> Path:
    return DATA_DIR / "history" / f"{slug}.json"


def update_history(runs: list[dict], cfg: dict) -> list[dict]:
    """Merge current runs into data/history/<slug>.json and return it, date-ascending.

    This file is the durable source of truth for the trend: Notion supplies the
    values, but rows are keyed by date and upserted here — a run edited or deleted
    in Notion updates or leaves its entry, it never erases past history. It is
    intentionally NOT wiped by the content rebuild in main().
    """
    rc = cfg["runs"]
    path = history_path(cfg["slug"])
    legacy = rc.get("trend_legacy_key")
    history: dict[str, dict] = {}
    if path.exists():
        try:
            for rec in json.loads(path.read_text(encoding="utf-8")):
                # Normalise older records that stored the trend under a camelCase key.
                if "value" not in rec and legacy and legacy in rec:
                    rec["value"] = rec[legacy]
                if rec.get("date"):
                    history[rec["date"]] = rec
        except (json.JSONDecodeError, OSError):
            history = {}

    for r in runs:
        rec = run_record(r["properties"], rc)
        date = rec.get("date")
        if not date:
            continue
        # Keep prior values for any field Notion now leaves blank, so a durable
        # record is never clobbered by a transient empty reading.
        merged = {**history.get(date, {}), **{k: v for k, v in rec.items() if v is not None}}
        merged["date"] = date
        history[date] = merged

    ordered = [history[d] for d in sorted(history)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")
    return ordered


def history_series(history: list[dict]) -> list[tuple[str, float]]:
    """Ascending (date, value) points for the trend chart."""
    series: list[tuple[str, float]] = []
    for rec in history:
        v = rec.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            label = str(rec.get("date") or "")
            series.append((label[:16], float(v)))   # trim long ISO timestamps
    return series


# --------------------------------------------------------------------------- #
# Table sections
# --------------------------------------------------------------------------- #
def export_table_section(client: Client, db_id: str, section_dir: Path,
                         section: dict) -> None:
    rows = query_all(client, db_id)
    if section.get("sort"):
        sort_rows(rows, section["sort"])
    out = section_dir / section["slug"]
    out.mkdir(parents=True, exist_ok=True)
    body = front_matter({"title": section["title"]})
    if section.get("intro"):
        body += f"\n{section['intro']}\n"
    body += "\n" + render_table(rows, section["columns"])
    (out / "_index.md").write_text(body, encoding="utf-8")


def export_indicators(client: Client, db_id: str, section_dir: Path) -> None:
    """Emit indicators as data/indicators.json + a page using the {{< indicators >}}
    shortcode, which renders an interactive, color-coded, sortable/filterable table."""
    rows = query_all(client, db_id)
    items = []
    for r in rows:
        p = r["properties"]
        items.append({
            "name": prop_value(p, "Indicator") or "",
            "code": prop_value(p, "Code") or "",
            "category": prop_value(p, "Category") or "Uncategorized",
            "weight": prop_value(p, "Weight") or 0,
            "unit": prop_value(p, "Unit") or "",
            "active": bool(prop_value(p, "Active")),
            "direction": prop_value(p, "Bubble Direction") or "",
            "description": prop_value(p, "Description") or "",
        })
    # Default order: highest-weight (most influential) first.
    items.sort(key=lambda x: (-(x["weight"] or 0), x["category"]))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "indicators.json").write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    out = section_dir / "indicators"
    out.mkdir(parents=True, exist_ok=True)
    body = (
        front_matter({"title": "Indicators"})
        + "\nIndicator families and weights driving the Bubble Risk Score. "
        + "Click a column header to sort; use the controls to filter.\n\n"
        + "{{< indicators >}}\n"
    )
    (out / "_index.md").write_text(body, encoding="utf-8")


def export_methodology(client: Client, page_id: str, section_dir: Path) -> None:
    body = blocks_to_md(client, page_id)
    (section_dir / "methodology.md").write_text(
        front_matter({"title": "Data Model & Methodology"}) + "\n" + body + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Dashboard home + hub
# --------------------------------------------------------------------------- #
def section_nav(cfg: dict, exported: dict) -> str:
    """A one-line link bar to a dashboard's sub-sections (relative to /<slug>/)."""
    links = ["[← All dashboards](../)"]
    if exported.get("runs"):
        links.append(f"[{cfg['runs']['section_title']}](runs/)")
    for section in cfg["sections"]:
        if section["slug"] in exported.get("sections", set()):
            title = "Indicators" if section["kind"] == "indicators" else section["title"]
            links.append(f"[{title}]({section['slug']}/)")
    if exported.get("methodology"):
        links.append("[Methodology](methodology/)")
    return " · ".join(links) + "\n"


def latest_summary(runs: list[dict], cfg: dict) -> dict | None:
    """A compact latest-reading summary for the hub card."""
    if not runs:
        return None
    p = runs[0]["properties"]
    rc = cfg["runs"]
    date = prop_value(p, rc["date_field"])
    parts = []
    for label, field in rc["headline"][:3]:
        val = prop_value(p, field)
        if val is not None and val != "":
            parts.append(f"{label} {val}")
    return {"date": fmt_date(date), "line": " · ".join(parts)}


def export_dashboard_home(client: Client, cfg: dict, section_dir: Path,
                          runs: list[dict], series: list[tuple[str, float]],
                          exported: dict) -> None:
    rc = cfg["runs"]
    intro = blocks_to_md(client, cfg["page_id"])   # dashboard prose
    parts = [front_matter({"title": cfg["title"]}), "", section_nav(cfg, exported), ""]

    if runs:
        p = runs[0]["properties"]
        latest_date = fmt_date(prop_value(p, rc["date_field"]))
        parts.append(f"## Latest reading — {latest_date}\n")
        parts.append("| Metric | Value |\n| --- | --- |")
        for label, field in rc["headline"]:
            val = prop_value(p, field)
            if val is not None and val != "":
                parts.append(f"| {label} | {val} |")
        parts.append("")

    # A trend needs at least two points; one run renders as an empty box.
    if len(series) >= 2:
        parts.append(sparkline_svg(series, rc["trend_label"]) + "\n")

    if runs:
        parts.append(f"## Recent {rc['section_title'].lower()}\n")
        parts.append(render_table(runs[:10], rc["recent_cols"]))

    if intro.strip():
        parts.append("## About this dashboard\n")
        parts.append(intro)

    (section_dir / "_index.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


def export_dashboard(client: Client, cfg: dict) -> dict:
    """Export one dashboard; return a summary card for the hub."""
    page_id = os.environ.get(cfg["page_id_env"]) or cfg["page_id"]
    cfg = {**cfg, "page_id": page_id}
    info = discover(client, cfg)

    section_dir = CONTENT_DIR / cfg["slug"]
    shutil.rmtree(section_dir, ignore_errors=True)
    section_dir.mkdir(parents=True, exist_ok=True)

    exported: dict = {"sections": set()}
    runs, series = [], []
    if info["runs_id"]:
        runs = export_runs(client, info["runs_id"], section_dir, cfg)
        history = update_history(runs, cfg)
        series = history_series(history)
        exported["runs"] = True
        print(f"  [{cfg['slug']}] runs: {len(runs)} rows; history: {len(history)} entries")

    for section in cfg["sections"]:
        db_id = info["sections"].get(section["slug"])
        if not db_id:
            continue
        if section["kind"] == "indicators":
            export_indicators(client, db_id, section_dir)
        else:
            export_table_section(client, db_id, section_dir, section)
        exported["sections"].add(section["slug"])
        print(f"  [{cfg['slug']}] {section['slug']}: exported")

    if info["methodology_id"]:
        export_methodology(client, info["methodology_id"], section_dir)
        exported["methodology"] = True
        print(f"  [{cfg['slug']}] methodology: exported")

    export_dashboard_home(client, cfg, section_dir, runs, series, exported)
    print(f"  [{cfg['slug']}] home (_index.md): exported")

    return {
        "slug": cfg["slug"],
        "title": cfg["title"],
        "tagline": cfg["tagline"],
        "latest": latest_summary(runs, cfg),
    }


def export_hub(summaries: list[dict]) -> None:
    """Write the generic hub home page: one card per dashboard."""
    parts = [
        front_matter({"title": "Research Dashboards"}),
        "",
        "Structured research workspaces exported from Notion and published here. "
        "Pick a dashboard to explore its latest reading, history and detail tables.\n",
        "## Dashboards\n",
    ]
    for s in summaries:
        parts.append(f"### [{s['title']}]({s['slug']}/)\n")
        parts.append(f"{s['tagline']}\n")
        if s.get("latest"):
            line = s["latest"]["line"]
            date = s["latest"]["date"]
            if line:
                parts.append(f"**Latest — {date}:** {line}\n")
        parts.append("")
    (CONTENT_DIR / "_index.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
def main() -> int:
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        print("ERROR: set NOTION_API_KEY.", file=sys.stderr)
        return 1
    client = Client(auth=token)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove legacy single-dashboard output so it doesn't linger as orphan pages.
    for legacy in ("runs", "indicators", "observations", "forecasts"):
        shutil.rmtree(CONTENT_DIR / legacy, ignore_errors=True)
    (CONTENT_DIR / "methodology.md").unlink(missing_ok=True)

    summaries = []
    for cfg in DASHBOARDS:
        print(f"Exporting dashboard: {cfg['slug']}")
        summaries.append(export_dashboard(client, cfg))

    export_hub(summaries)
    print("  hub (_index.md): exported")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
