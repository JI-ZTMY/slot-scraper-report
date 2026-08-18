"""Scraper for the "summary site" family: MinRepo (min-repo.com), AnaSlo
(ana-slo.com) and SloNavi (slo-navi.com).

This is a fairly direct port of SummaryScrapingManager.kt from the original
Android app (Slot Scraper). It reuses the same JavaScript snippets the
Android WebView used to run, executed here through Playwright instead.

Only MinRepo has been tested against a real store URL so far (2026-08-17).
AnaSlo / SloNavi are implemented from the Kotlin source but not yet verified
end to end -- if you add a store of that type and it fails, tell Claude the
exact error message from the log and we'll fix it together.
"""
from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PWTimeoutError

from models import SlotRow, csv_path, write_rows
import os

SOURCE_MINREPO = "MR"
SOURCE_ANASLO = "AS"
SOURCE_SLONAVI = "SN"


class ScrapeError(Exception):
    pass


class InvalidDifferenceError(ScrapeError):
    """MinRepo hid the diff value (rate-limited / login wall) - stop immediately."""


def log(msg: str) -> None:
    print(f"[summary] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------

def build_date_range(start_days_ago: int, end_days_ago: int) -> List[str]:
    """Returns YYYY/MM/DD strings from (today - start_days_ago) to
    (today - end_days_ago), oldest first. Matches Store.kt's createDateRange."""
    if start_days_ago < end_days_ago or end_days_ago < 0:
        return []
    today = date.today()
    out = []
    for days_ago in range(start_days_ago, end_days_ago - 1, -1):
        d = today - timedelta(days=days_ago)
        out.append(d.strftime("%Y/%m/%d"))
    return out


# ---------------------------------------------------------------------------
# JS snippets (ported near-verbatim from SummaryScrapingManager.kt)
# ---------------------------------------------------------------------------

JS_MINREPO_LIST_PAGE = r"""
() => {
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const tables = Array.from(document.querySelectorAll('#primary .table_wrap table')).filter(candidate => {
     const headers = Array.from(candidate.querySelectorAll('th')).map(cell => clean(cell.textContent));
     return headers.some(value => value === '日付') &&
            headers.some(value => value.includes('総差枚')) &&
            headers.some(value => value.includes('平均G'));
  });
  const articleLinks = tables.flatMap(table =>
    Array.from(table.querySelectorAll('tr'))
      .map(row => row.querySelector('td:first-child a[href]'))
      .filter(Boolean)
  );
  return {
    validTable: tables.length > 0,
    links: articleLinks.map(a => {
      const text = (a.textContent || '').replace(/\s+/g, ' ').trim();
      const match = text.match(/(?:(\d{4})[\/年])?(\d{1,2})[\/月](\d{1,2})(?:日)?/);
      return match ? {
        year: match[1] || '',
        month: String(Number(match[2])),
        day: String(Number(match[3])),
        href: a.href
      } : null;
    }).filter(Boolean),
    next: (() => {
      const a = document.querySelector('#primary a[rel="next"], #primary a.next.page-numbers, #primary .pagination a.next, #primary .nav-links a.next');
      return a ? a.href : '';
    })()
  };
}
"""

JS_HEADINGS = r"""
() => Array.from(document.querySelectorAll('h1,h2,.entry-title'))
  .slice(0, 8).map(x => (x.textContent || '').trim()).join(' | ')
"""

JS_MINREPO_BACKLINKS = r"""
() => {
  const links = [];
  const headerLink = document.querySelector('article > div.hall_header .hall_name a[href]');
  if (headerLink) links.push(headerLink.href);
  const historyLink = Array.from(document.querySelectorAll('.modal_menu a[href]'))
    .find(link => (link.textContent || '').trim() === '過去レポート一覧');
  if (historyLink) links.push(historyLink.href);
  return Array.from(new Set(links));
}
"""

JS_PAGE_IDENTITY = r"""
() => JSON.stringify({
  title: document.title || '',
  canonical: document.querySelector('link[rel="canonical"]')?.href || '',
  ogUrl: document.querySelector('meta[property="og:url"]')?.content || ''
})
"""


def js_wait_state(selector: str) -> str:
    return f"""
() => {{
  if (document.querySelector({selector!r})) return 'ready';
  const text = document.body ? document.body.innerText : '';
  if (document.body && document.body.classList.contains('error404')) return 'missing';
  if (text.includes('お探しのページはありませんでした') || text.includes('アクセスしようとしたページは見つかりませんでした')) return 'missing';
  return 'wait';
}}
"""


def js_extract_rows(selector: str) -> str:
    return f"""
() => {{
  const table = document.querySelector({selector!r});
  if (!table) return [];
  const clean = v => (v || '').replace(/\\s+/g, ' ').trim();
  let headers = Array.from(table.querySelectorAll('thead tr')).map(tr =>
    Array.from(tr.querySelectorAll('th,td')).map(x => clean(x.textContent))
  ).find(x => x.length) || [];
  if (!headers.length) {{
    const headerRow = Array.from(table.querySelectorAll('tr')).find(tr => tr.querySelector('th'));
    if (headerRow) headers = Array.from(headerRow.querySelectorAll('th,td')).map(x => clean(x.textContent));
  }}
  const find = names => headers.findIndex(h => names.some(n => h === n || h.includes(n)));
  const idx = {{
    machine: find(['機種名', '機種']), unit: find(['台番号', '台番']), diff: find(['差枚']),
    games: find(['G数', 'ゲーム']), big: find(['BB', 'BIG']), reg: find(['RB', 'REG'])
  }};
  return Array.from(table.querySelectorAll('tbody tr')).map(tr => {{
    const cells = Array.from(tr.querySelectorAll('td')).map(x => clean(x.textContent));
    const value = i => i >= 0 && i < cells.length ? cells[i] : '';
    return {{machineName: value(idx.machine), unitNumber: value(idx.unit), diffValue: value(idx.diff),
             totalGames: value(idx.games), big: value(idx.big), reg: value(idx.reg)}};
  }}).filter(x => x.machineName && /^\\d+$/.test(x.unitNumber.replace(/[^0-9]/g, '')));
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def numeric_only(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    v = v.replace(",", "")
    v = re.sub(r"[^0-9+\-]", "", v)
    if v in ("", "+", "-"):
        return None
    return v


def parse_minrepo_difference(raw_value: str, unit_number: str) -> Optional[str]:
    value = (raw_value or "").strip()
    if not value:
        return None
    if not re.match(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)$", value):
        raise InvalidDifferenceError(
            f"みんレポの差枚が数値ではありません（台番: {unit_number}、表示値:「{value}」）"
        )
    return value.replace(",", "")


def parse_slot_rows(raw_list: List[dict], date_str: str, strict_minrepo: bool = False) -> List[SlotRow]:
    rows: List[SlotRow] = []
    for obj in raw_list:
        def val(key: str) -> Optional[str]:
            v = (obj.get(key) or "").strip()
            if not v or v.lower() in ("null", "undefined"):
                return None
            return v

        unit_raw = val("unitNumber")
        unit = re.sub(r"[^0-9]", "", unit_raw) if unit_raw else ""
        if not unit:
            continue
        diff_raw = val("diffValue")
        if strict_minrepo:
            diff = parse_minrepo_difference(diff_raw or "", unit)
        else:
            diff = numeric_only(diff_raw)
        rows.append(SlotRow(
            date=date_str,
            machine_name=val("machineName"),
            unit_number=unit,
            diff_value=diff,
            total_games=numeric_only(val("totalGames")),
            big=numeric_only(val("big")),
            reg=numeric_only(val("reg")),
        ))
    return rows


def data_signature(rows: List[SlotRow]) -> str:
    return "\n".join(
        "|".join((r.machine_name or "").strip() for r in [r]) + "|" +
        "|".join([
            (r.unit_number or "").strip(),
            (r.diff_value or "").strip(),
            (r.total_games or "").strip(),
            (r.big or "").strip(),
            (r.reg or "").strip(),
        ])
        for r in rows
    )


def normalize_minrepo_store_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = re.sub(r"/+", "/", parsed.path or "").rstrip("/")
    path = re.sub(r"/page/\d+$", "", path, flags=re.IGNORECASE)
    return host + path.lower()


def urls_match(current: str, expected: str) -> bool:
    c = urllib.parse.urlparse(current)
    e = urllib.parse.urlparse(expected)
    return c.netloc.lower() == e.netloc.lower() and c.path.rstrip("/") == e.path.rstrip("/")


# ---------------------------------------------------------------------------
# Page interaction
# ---------------------------------------------------------------------------

def goto(page: Page, url: str, timeout_ms: int = 30_000, referer: Optional[str] = None) -> None:
    kwargs = {"wait_until": "domcontentloaded", "timeout": timeout_ms}
    if referer:
        kwargs["referer"] = referer
    page.goto(url, **kwargs)
    # A couple of sites in this family show a real page only after a small
    # amount of human-like interaction (scrolling). This is cheap and
    # harmless even where it's not needed.
    try:
        page.mouse.wheel(0, 400)
    except Exception:
        pass


def open_minrepo_article(page: Page, bare_url: str, referer: str) -> None:
    """Visit the bare article URL (no query string) first and let it settle.

    min-repo.com appears to gate the '?kishu=all&sort=num' deep link (the
    per-unit table sorted by unit number) behind whatever session state gets
    established by a normal visit to the article's own page first -- jumping
    straight to the query-string URL from a cold session/referer reliably
    comes back as a literally empty response. Visiting the bare URL first,
    the way a real visitor would (click the article, then click "台番順"
    inside it), avoids that.
    """
    goto(page, bare_url, referer=referer)
    try:
        page.wait_for_function(
            "document.querySelector('#main') && document.querySelector('#main').innerHTML.length > 500",
            timeout=10_000,
        )
    except PWTimeoutError:
        pass


def wait_for_data_table(page: Page, selector: str, timeout_s: float = 45.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = page.evaluate(js_wait_state(selector))
        if state == "ready":
            return
        if state == "missing":
            raise ScrapeError("対象日のデータページが存在しません")
        time.sleep(0.5)
    raise ScrapeError("データテーブルが表示されませんでした")


def selector_for(site: str) -> str:
    if site == SOURCE_MINREPO:
        return "div.table_wrap table"
    if site == SOURCE_SLONAVI:
        return "div.bl_allMachineTable table.bl_table_data"
    return "table#all_data_table"


def verify_target_date(page: Page, site: str, date_str: str, expected_url: str) -> None:
    parts = date_str.split("/")
    if site == SOURCE_MINREPO:
        expected_year = parts[0]
        current_year = str(date.today().year)
        month_day = f"{int(parts[1])}/{int(parts[2])}"
        heading = page.evaluate(JS_HEADINGS)
        if month_day not in heading:
            raise ScrapeError(
                f"表示ページの日付が対象日 {date_str} と一致しません "
                f"(url={page.url} / heading=\"{heading[:200]}\")"
            )
        if expected_year != current_year and expected_year not in heading:
            raise ScrapeError(
                f"表示ページの年が対象日 {date_str} と一致しません "
                f"(url={page.url} / heading=\"{heading[:200]}\")"
            )
    elif site == SOURCE_SLONAVI:
        expected_path = urllib.parse.urlparse(expected_url).path.rstrip("/")
        m = re.match(r"^/data/\d{4}-\d{2}-\d{2}-(\d+)$", expected_path)
        if not m:
            raise ScrapeError("スロナビ対象URLからホールIDを確認できません")
        expected_hall_id = m.group(1)
        import json
        identity = json.loads(page.evaluate(JS_PAGE_IDENTITY))
        title = identity.get("title", "")
        dm = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", title)
        title_date = [int(x) for x in dm.groups()] if dm else None
        expected_parts = [int(p) for p in parts]
        if title_date != expected_parts:
            raise ScrapeError(f"スロナビページ内の日付が対象日 {date_str} と一致しません（title={title}）")
        canonical = urllib.parse.urlparse(identity.get("canonical", ""))
        if canonical.netloc.lower() != "slo-navi.com" or canonical.path.rstrip("/") != f"/hall/{expected_hall_id}":
            raise ScrapeError("スロナビページ内の店舗IDが設定店舗と一致しません")
        if not urls_match(identity.get("ogUrl", ""), expected_url):
            raise ScrapeError("スロナビページ内のog:urlが取得対象URLと一致しません")
    else:
        iso = date_str.replace("/", "-")
        if iso not in urllib.parse.urlparse(expected_url).path:
            raise ScrapeError(f"対象日 {date_str} のURLを確認できません")
    if not urls_match(page.url, expected_url):
        raise ScrapeError(f"現在URLが対象日のURLと一致しません (actual={page.url} / expected={expected_url})")


def verify_minrepo_backlink(page: Page, expected_store_url: str) -> None:
    links = page.evaluate(JS_MINREPO_BACKLINKS)
    if not links:
        raise ScrapeError("記事内の店舗レポート一覧リンクを確認できません")
    expected = normalize_minrepo_store_url(expected_store_url)
    for link in links:
        if normalize_minrepo_store_url(link) != expected:
            raise ScrapeError("記事の店舗レポート一覧URLが店舗設定URLと一致しません")


def resolve_data_url(store: dict, site: str, date_str: str, minrepo_links: Dict[str, str]) -> str:
    iso = date_str.replace("/", "-")
    if site == SOURCE_MINREPO:
        url = minrepo_links.get(date_str)
        if not url:
            raise ScrapeError(f"{date_str} のデータリンクが見つかりません")
        return url
    if site == SOURCE_SLONAVI:
        hall_id = [p for p in urllib.parse.urlparse(store["url"]).path.split("/") if p][-1]
        return f"https://slo-navi.com/data/{iso}-{hall_id}/"
    if site == SOURCE_ANASLO:
        segment = urllib.parse.urlparse(store["url"]).path.rstrip("/").split("/")[-1]
        decoded = urllib.parse.unquote(segment).removesuffix("-データ一覧")
        slug = urllib.parse.quote(decoded).lower()
        return f"https://ana-slo.com/{iso}-{slug}-data/"
    raise ScrapeError("未対応のまとめサイトです")


def collect_minrepo_available_links(page: Page, store_url: str, requested_dates: List[str]) -> Dict[str, str]:
    requested = set(requested_dates)
    current_year = str(date.today().year)
    found: Dict[str, str] = {}
    visited = set()
    page_url = store_url
    page_count = 0

    while page_url and page_count < 100 and len(found) < len(requested):
        normalized = page_url.split("#")[0]
        if normalized in visited:
            break
        visited.add(normalized)
        goto(page, normalized)
        page_count += 1

        result = page.evaluate(JS_MINREPO_LIST_PAGE)
        if not result or not result.get("validTable"):
            raise ScrapeError("店舗の記事一覧表を確認できません")
        for item in result.get("links", []):
            month = item.get("month", "")
            day_ = item.get("day", "")
            year = item.get("year", "")
            href = (item.get("href") or "").split("?")[0]
            article_path = urllib.parse.urlparse(href).path.rstrip("/")
            if not re.match(r"^/\d+$", article_path):
                continue
            candidates = []
            if year:
                candidates.append(f"{year}/{int(month):02d}/{int(day_):02d}")
            else:
                candidates.append(f"{current_year}/{int(month):02d}/{int(day_):02d}")
            for date_str in candidates:
                if date_str in requested and href:
                    found.setdefault(date_str, href)
        page_url = result.get("next") or None

    skipped = len(requested) - len(found)
    if skipped > 0:
        log(f"みんレポ: データリンクが存在しない {skipped} 日分を待機せずスキップします")
    log(f"みんレポ: 店舗ページ{page_count}ページから取得対象 {len(found)} 日分のリンクを確認しました")
    return found


def filter_slonavi_available_dates(page: Page, store: dict, requested_dates: List[str]) -> List[str]:
    goto(page, store["url"])
    hall_id = [p for p in urllib.parse.urlparse(store["url"]).path.split("/") if p][-1]
    if not hall_id:
        raise ScrapeError("ホールIDを取得できません")
    script = f"""
() => Array.from(document.querySelectorAll('a[href]'))
  .map(a => a.href)
  .map(href => href.match(new RegExp('/data/(\\\\d{{4}}-\\\\d{{2}}-\\\\d{{2}})-' + {hall_id!r} + '/?$')))
  .filter(Boolean)
  .map(match => match[1].replace(/-/g, '/'))
  .filter((date, index, all) => all.indexOf(date) === index)
"""
    available = set(page.evaluate(script) or [])
    if not available:
        raise ScrapeError("店舗ページからデータ日付リンクを取得できません")
    dates = [d for d in requested_dates if d in available]
    skipped = len(requested_dates) - len(dates)
    if skipped > 0:
        log(f"スロナビ: データページが存在しない {skipped} 日分を待機せずスキップします")
    return dates


def save_debug_snapshot(page: Page, data_dir: str, store_slug: str, date_digits: str) -> Optional[str]:
    """On repeated failure, save a screenshot + HTML snapshot of whatever
    page Playwright ended up on, so a human (or Claude) can see what went
    wrong without needing to reproduce it interactively."""
    try:
        debug_dir = os.path.join(os.path.dirname(data_dir), "debug", store_slug)
        os.makedirs(debug_dir, exist_ok=True)
        base = os.path.join(debug_dir, date_digits)
        page.screenshot(path=base + ".png", full_page=True)
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(page.content())
        return base + ".png / " + base + ".html"
    except Exception as e:  # pragma: no cover - best effort only
        log(f"デバッグ情報の保存に失敗しました: {e}")
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def scrape_store(page: Page, store: dict, data_dir: str) -> None:
    site = store["source_type"]
    requested_dates = build_date_range(store["start_days_ago"], store["end_days_ago"])
    if not requested_dates:
        raise ScrapeError("取得期間が設定されていません")

    minrepo_links: Dict[str, str] = {}
    if site == SOURCE_SLONAVI:
        dates = filter_slonavi_available_dates(page, store, requested_dates)
    elif site == SOURCE_MINREPO:
        minrepo_links = collect_minrepo_available_links(page, store["url"], requested_dates)
        dates = [d for d in requested_dates if d in minrepo_links]
    else:
        dates = requested_dates

    if not dates:
        raise ScrapeError("取得期間内にデータが存在する日付がありません")

    log(f"{store['name']} まとめサイト取得開始: {len(dates)}日分")
    failed_days = 0
    previous_signature: Optional[str] = None
    max_attempts = 5 if site == SOURCE_MINREPO else 3

    for i, date_str in enumerate(dates):
        date_digits = date_str.replace("/", "")
        out_path = csv_path(data_dir, store["slug"], date_digits)
        if os.path.isfile(out_path):
            log(f"[{i + 1}/{len(dates)}] {date_str} 保存済みのためスキップ")
            continue

        log(f"[{i + 1}/{len(dates)}] {date_str} データページを開いています")
        last_error: Optional[Exception] = None
        rows: Optional[List[SlotRow]] = None
        signature: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            try:
                data_url = resolve_data_url(store, site, date_str, minrepo_links)
                if site == SOURCE_MINREPO:
                    bare_url = data_url
                    open_minrepo_article(page, bare_url, store["url"])
                    data_url = bare_url + "?kishu=all&sort=num"
                    goto(page, data_url, referer=bare_url)
                else:
                    goto(page, data_url, referer=store["url"])
                verify_target_date(page, site, date_str, data_url)
                if site == SOURCE_MINREPO:
                    verify_minrepo_backlink(page, store["url"])
                wait_for_data_table(page, selector_for(site))
                raw_rows = page.evaluate(js_extract_rows(selector_for(site)))
                # de-dup by machine+unit like the Kotlin version does
                seen = set()
                deduped = []
                for r in raw_rows:
                    key = (r.get("machineName", "").strip(), r.get("unitNumber", "").strip())
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(r)
                candidate = parse_slot_rows(deduped, date_str, strict_minrepo=(site == SOURCE_MINREPO))
                if not candidate:
                    raise ScrapeError("データテーブルに有効な行がありません")
                sig = data_signature(candidate)
                if previous_signature is not None and sig == previous_signature:
                    raise ScrapeError("前ページと同じデータです")
                rows, signature = candidate, sig
                break
            except InvalidDifferenceError:
                raise
            except (ScrapeError, PWTimeoutError) as e:
                last_error = e
                if attempt < max_attempts:
                    log(f"{date_str} ページ取得を再試行します（{attempt}/{max_attempts}）: {e}")
                    time.sleep(attempt * 1.0)

        if rows is None:
            log(f"{date_str} 取得失敗: {last_error}")
            debug_path = save_debug_snapshot(page, data_dir, store["slug"], date_digits)
            if debug_path:
                log(f"  -> デバッグ用のスクリーンショット/HTMLを保存しました: {debug_path}")
            failed_days += 1
            continue

        write_rows(out_path, rows)
        previous_signature = signature
        log(f"{date_str} {len(rows)}台のデータを保存しました")

    if failed_days > 0:
        log(f"[警告] {failed_days} 日分の取得に失敗しました")
