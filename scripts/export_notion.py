#!/usr/bin/env python3
"""Export the 'AI Bubble Risk Dashboard' Notion page into a Hugo site.

The source is a single Notion *page* whose body contains four inline databases
(Weekly Runs, Indicators, Observations, Forecasts) plus a 'Data Model &
Methodology' child page. This script discovers those from the page id and emits:

  content/_index.md          dashboard: latest score, trend SVG, recent runs
  content/runs/<date>.md      one page per weekly run
  content/indicators/_index.md    table of indicators
  content/observations/_index.md  table of observations
  content/forecasts/_index.md     table of forecasts
  content/methodology.md          rendered from the child page

Environment:
  NOTION_API_KEY   Notion internal-integration secret (required)
  NOTION_PAGE_ID   Dashboard page id (optional; defaults to the known page)
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from notion_client import Client

DEFAULT_PAGE_ID = "3d1b7fcffbda81f0a1c2f2a3324912cd"
CONTENT_DIR = Path("content")

# Column order for each table section; missing columns are silently skipped.
INDICATOR_COLS = ["Indicator", "Code", "Category", "Weight", "Unit", "Active",
                  "Bubble Direction", "Description"]
OBSERVATION_COLS = ["Observation Date", "Indicator Code", "Entity", "Period",
                    "Value", "Value Text", "Unit", "Signal", "QoQ Change",
                    "YoY Change", "Source", "Source Type", "Confidence",
                    "Retrieved Date", "Notes"]
FORECAST_COLS = ["Forecast", "Category", "Prediction", "Probability",
                 "Forecast Date", "Resolution Date", "Resolution Criteria",
                 "Outcome", "Resolved Date", "Brier Score", "Evidence URL"]


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
        text = str(v)
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


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover(client: Client, page_id: str) -> dict:
    """Map the dashboard page's child databases (by title keyword) and child page."""
    databases: dict[str, str] = {}
    methodology_id = None
    intro_blocks_id = page_id
    cursor = None
    while True:
        resp = client.blocks.children.list(block_id=page_id, start_cursor=cursor)
        for b in resp["results"]:
            if b["type"] == "child_database":
                title = b["child_database"].get("title", "")
                key = title.lower()
                if "weekly run" in key:
                    databases["runs"] = b["id"]
                elif "indicator" in key:
                    databases["indicators"] = b["id"]
                elif "observation" in key:
                    databases["observations"] = b["id"]
                elif "forecast" in key:
                    databases["forecasts"] = b["id"]
            elif b["type"] == "child_page":
                title = b["child_page"].get("title", "")
                if "methodology" in title.lower() or "data model" in title.lower():
                    methodology_id = b["id"]
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return {"databases": databases, "methodology_id": methodology_id, "page_id": intro_blocks_id}


# --------------------------------------------------------------------------- #
# Rendering
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


def sparkline_svg(series: list[tuple[str, float]]) -> str:
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
        f'aria-label="Risk score trend" '
        f'style="max-width:100%;height:auto;font-family:system-ui,sans-serif">'
        f'<text x="{pad}" y="20" fill="currentColor" font-size="13" '
        f'font-weight="600">Risk Score trend</text>'
        f'<text x="{pad}" y="{py(vmax):.1f}" fill="currentColor" font-size="11" '
        f'opacity="0.6" dx="-4" text-anchor="end">{vmax:g}</text>'
        f'<text x="{pad}" y="{py(vmin):.1f}" fill="currentColor" font-size="11" '
        f'opacity="0.6" dx="-4" text-anchor="end">{vmin:g}</text>'
        f'{line}{dots}</svg>'
    )


def export_runs(client: Client, db_id: str, out_dir: Path) -> tuple[list[dict], list[tuple[str, float]]]:
    rows = query_all(client, db_id)
    rows.sort(key=lambda r: prop_value(r["properties"], "Run Date") or "", reverse=True)
    section = out_dir / "runs"
    section.mkdir(parents=True, exist_ok=True)
    (section / "_index.md").write_text(
        front_matter({"title": "Weekly Runs"}) + "\nWeekly Bubble Risk scores and probabilities.\n",
        encoding="utf-8",
    )
    for r in rows:
        p = r["properties"]
        run_date = prop_value(p, "Run Date")
        title = prop_value(p, "Run") or run_date or "run"
        slug = slugify(str(run_date or title))
        fm = front_matter({
            "title": f"Weekly Run — {run_date}" if run_date else str(title),
            "date": run_date,
            "riskScore": prop_value(p, "Risk Score"),
            "riskLevel": prop_value(p, "Risk Level"),
            "burstProbability": prop_value(p, "Burst Probability"),
            "direction": prop_value(p, "Direction"),
        })
        metrics = [
            ("Risk Score", prop_value(p, "Risk Score")),
            ("Prior Risk Score", prop_value(p, "Prior Risk Score")),
            ("Score Change", prop_value(p, "Score Change")),
            ("Risk Level", prop_value(p, "Risk Level")),
            ("Direction", prop_value(p, "Direction")),
            ("Burst Probability", prop_value(p, "Burst Probability")),
            ("Adoption Collapse Probability", prop_value(p, "Adoption Collapse Probability")),
            ("Method Version", prop_value(p, "Method Version")),
        ]
        body = ["| Metric | Value |", "| --- | --- |"]
        for label, val in metrics:
            if val is not None and val != "":
                body.append(f"| {label} | {val} |")
        thesis = prop_value(p, "Thesis")
        key_changes = prop_value(p, "Key Changes")
        report_url = prop_value(p, "Report URL")
        if thesis:
            body.append(f"\n### Thesis\n\n{thesis}\n")
        if key_changes:
            body.append(f"\n### Key Changes\n\n{key_changes}\n")
        if report_url:
            body.append(f"\n[Full report]({report_url})\n")
        page_body = blocks_to_md(client, r["id"])
        if page_body.strip():
            body.append("\n" + page_body)
        (section / f"{slug}.md").write_text(fm + "\n" + "\n".join(body) + "\n", encoding="utf-8")

    # Ascending series for the trend chart.
    series: list[tuple[str, float]] = []
    for r in reversed(rows):
        d = prop_value(r["properties"], "Run Date")
        v = prop_value(r["properties"], "Risk Score")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            series.append((str(d or ""), float(v)))
    return rows, series


def export_table_section(client: Client, db_id: str, out_dir: Path, slug: str,
                         title: str, columns: list[str], sort_key: str | None,
                         intro: str = "") -> None:
    rows = query_all(client, db_id)
    if sort_key:
        rows.sort(key=lambda r: prop_value(r["properties"], sort_key) or "", reverse=True)
    section = out_dir / slug
    section.mkdir(parents=True, exist_ok=True)
    body = front_matter({"title": title})
    if intro:
        body += f"\n{intro}\n"
    body += "\n" + render_table(rows, columns)
    (section / "_index.md").write_text(body, encoding="utf-8")


def export_methodology(client: Client, page_id: str, out_dir: Path) -> None:
    body = blocks_to_md(client, page_id)
    (out_dir / "methodology.md").write_text(
        front_matter({"title": "Data Model & Methodology"}) + "\n" + body + "\n",
        encoding="utf-8",
    )


def export_dashboard(client: Client, page_id: str, out_dir: Path,
                     runs: list[dict], series: list[tuple[str, float]]) -> None:
    intro = blocks_to_md(client, page_id)  # Purpose / Workflow / Interpretation prose
    parts = [front_matter({"title": "AI Bubble Risk Dashboard"}), ""]

    if runs:
        p = runs[0]["properties"]
        latest_date = prop_value(p, "Run Date")
        score = prop_value(p, "Risk Score")
        parts.append(f"## Latest reading — {latest_date}\n")
        headline = [
            ("Risk Score", prop_value(p, "Risk Score")),
            ("Risk Level", prop_value(p, "Risk Level")),
            ("Direction", prop_value(p, "Direction")),
            ("Burst Probability (18–24mo)", prop_value(p, "Burst Probability")),
            ("Adoption Collapse Probability", prop_value(p, "Adoption Collapse Probability")),
        ]
        parts.append("| Metric | Value |\n| --- | --- |")
        for label, val in headline:
            if val is not None and val != "":
                parts.append(f"| {label} | {val} |")
        parts.append("")
        _ = score

    if series:
        parts.append(sparkline_svg(series) + "\n")

    if runs:
        parts.append("## Recent runs\n")
        cols = ["Run Date", "Risk Score", "Score Change", "Burst Probability",
                "Risk Level", "Direction"]
        parts.append(render_table(runs[:10], cols))

    if intro.strip():
        parts.append("## About this dashboard\n")
        parts.append(intro)

    (out_dir / "_index.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
def main() -> int:
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        print("ERROR: set NOTION_API_KEY.", file=sys.stderr)
        return 1
    page_id = os.environ.get("NOTION_PAGE_ID", DEFAULT_PAGE_ID)
    client = Client(auth=token)

    info = discover(client, page_id)
    dbs = info["databases"]
    print(f"Discovered databases: {list(dbs.keys())}")

    # Rebuild content from scratch so deletions in Notion propagate.
    for sub in ("runs", "indicators", "observations", "forecasts"):
        shutil.rmtree(CONTENT_DIR / sub, ignore_errors=True)
    for f in ("_index.md", "methodology.md"):
        (CONTENT_DIR / f).unlink(missing_ok=True)
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    runs, series = ([], [])
    if "runs" in dbs:
        runs, series = export_runs(client, dbs["runs"], CONTENT_DIR)
        print(f"  runs: {len(runs)} rows")
    if "indicators" in dbs:
        export_table_section(client, dbs["indicators"], CONTENT_DIR, "indicators",
                             "Indicators", INDICATOR_COLS, sort_key="Category",
                             intro="Indicator families and weights driving the Bubble Risk Score.")
        print("  indicators: exported")
    if "observations" in dbs:
        export_table_section(client, dbs["observations"], CONTENT_DIR, "observations",
                             "Observations", OBSERVATION_COLS, sort_key="Observation Date",
                             intro="Immutable dated observations with provenance and confidence.")
        print("  observations: exported")
    if "forecasts" in dbs:
        export_table_section(client, dbs["forecasts"], CONTENT_DIR, "forecasts",
                             "Forecasts", FORECAST_COLS, sort_key="Forecast Date",
                             intro="Explicit forecasts tracked for later Brier-score calibration.")
        print("  forecasts: exported")
    if info["methodology_id"]:
        export_methodology(client, info["methodology_id"], CONTENT_DIR)
        print("  methodology: exported")

    export_dashboard(client, page_id, CONTENT_DIR, runs, series)
    print("  dashboard (_index.md): exported")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
