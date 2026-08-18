"""Entry point: reads config/stores.json, scrapes every configured store,
then regenerates the HTML report in docs/index.html.

Usage (from the project root, with the venv active):
    python src/run_all.py
    python src/run_all.py --headed      # show the browser window (debugging)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))

from scrape_summary import scrape_store as scrape_summary_store, SOURCE_MINREPO, SOURCE_ANASLO, SOURCE_SLONAVI
import report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "stores.json")
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")

SUMMARY_TYPES = {SOURCE_MINREPO, SOURCE_ANASLO, SOURCE_SLONAVI}
NOT_YET_IMPLEMENTED = {"PS", "S7", "SP"}


def load_stores() -> list[dict]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["stores"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    args = parser.parse_args()

    stores = load_stores()
    if not stores:
        print("config/stores.json に店舗が設定されていません。")
        return 1

    had_error = False
    with sync_playwright() as p:
        launch_kwargs = dict(
            headless=not args.headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            # Prefer the user's real, already-installed Chrome over the
            # bundled Chromium build -- some sites specifically fingerprint
            # (and block) the bundled build / automation flags.
            browser = p.chromium.launch(channel="chrome", **launch_kwargs)
            print("[info] using system Google Chrome", flush=True)
        except Exception:
            browser = p.chromium.launch(**launch_kwargs)
            print("[info] Google Chrome not found, using bundled Chromium", flush=True)

        context = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        # Hide the most common automation fingerprint before any page script runs.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        for store in stores:
            source_type = store.get("source_type")
            print(f"\n===== {store.get('name')} ({source_type}) =====", flush=True)
            try:
                if source_type in SUMMARY_TYPES:
                    scrape_summary_store(page, store, DATA_DIR)
                elif source_type in NOT_YET_IMPLEMENTED:
                    print(
                        f"[skip] source_type={source_type} はまだ未実装です "
                        f"(PS/S7店舗の情報がまだ登録されていません)。"
                    )
                else:
                    print(f"[skip] 不明な source_type: {source_type}")
            except Exception:
                had_error = True
                print(f"[error] {store.get('name')} の取得中にエラーが発生しました:")
                traceback.print_exc()

        context.close()
        browser.close()

    print("\n===== レポート生成 =====", flush=True)
    report.generate(DATA_DIR, os.path.join(DOCS_DIR, "index.html"), stores)
    print(f"レポートを書き出しました: {os.path.join(DOCS_DIR, 'index.html')}")

    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
