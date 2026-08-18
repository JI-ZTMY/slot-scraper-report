"""Generates a single self-contained HTML page (docs/index.html) listing the
raw scraped data, grouped by store and date (newest first).

This is intentionally simple ("raw data list only" — v1 scope). Analysis /
aggregation views (Juggler stats, hollow analysis, etc.) from the original
Android app's CsvCalculationActivity are NOT reproduced here yet.
"""
from __future__ import annotations

import html
import os
from datetime import datetime
from typing import List

from models import read_rows, SlotRow


def _list_dates_desc(store_dir: str) -> List[str]:
    if not os.path.isdir(store_dir):
        return []
    names = [f[:-4] for f in os.listdir(store_dir) if f.endswith(".csv")]
    return sorted(names, reverse=True)


def _rows_table_html(rows: List[SlotRow]) -> str:
    def esc(v) -> str:
        return html.escape(v) if v else ""

    body_rows = []
    for r in rows:
        diff = r.diff_value or ""
        diff_class = ""
        try:
            diff_num = int(diff)
            diff_class = "pos" if diff_num > 0 else ("neg" if diff_num < 0 else "")
        except (TypeError, ValueError):
            pass
        body_rows.append(
            f"<tr><td>{esc(r.machine_name)}</td><td>{esc(r.unit_number)}</td>"
            f"<td class='{diff_class}'>{esc(diff)}</td><td>{esc(r.total_games)}</td>"
            f"<td>{esc(r.big)}</td><td>{esc(r.reg)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>機種名</th><th>台番号</th><th>差枚</th>"
        "<th>G数</th><th>BIG</th><th>REG</th></tr></thead><tbody>"
        + "".join(body_rows) + "</tbody></table>"
    )


def _format_date_label(yyyymmdd: str) -> str:
    try:
        d = datetime.strptime(yyyymmdd, "%Y%m%d")
        return d.strftime("%Y/%m/%d")
    except ValueError:
        return yyyymmdd


def generate(data_dir: str, out_path: str, stores: List[dict], recent_open: int = 3) -> None:
    sections = []
    for store in stores:
        slug = store.get("slug")
        name = html.escape(store.get("name", slug or "unknown"))
        store_dir = os.path.join(data_dir, slug) if slug else None
        dates = _list_dates_desc(store_dir) if store_dir else []

        if not dates:
            sections.append(
                f"<section><h2>{name}</h2><p class='muted'>まだデータがありません。</p></section>"
            )
            continue

        blocks = []
        for i, d in enumerate(dates):
            rows = read_rows(os.path.join(store_dir, f"{d}.csv"))
            open_attr = " open" if i < recent_open else ""
            blocks.append(
                f"<details{open_attr}><summary>{_format_date_label(d)}"
                f"（{len(rows)}台）</summary>{_rows_table_html(rows)}</details>"
            )
        sections.append(f"<section><h2>{name}</h2>{''.join(blocks)}</section>")

    generated_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Slot Scraper レポート</title>
<link rel="icon" href="favicon.png">
<link rel="apple-touch-icon" href="icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Slot Scraper">
<meta name="theme-color" content="#1e1e24">
<style>
  :root {{
    color-scheme: light dark;
    --border: #d9d9df;
    --muted: #767680;
    --pos: #1a7f37;
    --neg: #cf222e;
    --bg-alt: #f6f6f8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Hiragino Sans", "Yu Gothic", sans-serif;
    margin: 0; padding: 16px; max-width: 760px; margin-inline: auto;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.3rem; margin-bottom: 4px; }}
  .updated {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }}
  section {{ margin-bottom: 28px; }}
  h2 {{ font-size: 1.05rem; border-bottom: 2px solid var(--border); padding-bottom: 6px; }}
  details {{ border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }}
  summary {{ padding: 10px 12px; cursor: pointer; font-weight: 600; background: var(--bg-alt); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }}
  th:first-child, td:first-child {{ text-align: left; white-space: normal; }}
  td.pos {{ color: var(--pos); }}
  td.neg {{ color: var(--neg); }}
  .muted {{ color: var(--muted); }}
</style>
</head>
<body>
<h1>Slot Scraper レポート</h1>
<div class="updated">最終更新: {generated_at}</div>
{''.join(sections)}
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
