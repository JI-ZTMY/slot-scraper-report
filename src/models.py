"""Shared data structures and CSV helpers for Slot Scraper (PC edition).

CSV format (one file per store per date, header row included):
    date,machine_name,unit_number,diff_value,total_games,big,reg

This intentionally does NOT try to byte-for-byte match the old Android app's
CSV files (those had no header and lived in the phone's private storage).
This is a fresh, self-contained format for the PC version.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, asdict
from typing import Optional, List

CSV_HEADER = ["date", "machine_name", "unit_number", "diff_value", "total_games", "big", "reg"]


@dataclass
class SlotRow:
    date: str  # YYYY/MM/DD
    machine_name: Optional[str]
    unit_number: Optional[str]
    diff_value: Optional[str]
    total_games: Optional[str]
    big: Optional[str]
    reg: Optional[str]


def csv_path(data_dir: str, store_slug: str, date_yyyymmdd: str) -> str:
    store_dir = os.path.join(data_dir, store_slug)
    os.makedirs(store_dir, exist_ok=True)
    return os.path.join(store_dir, f"{date_yyyymmdd}.csv")


def write_rows(path: str, rows: List[SlotRow]) -> None:
    """Overwrites the file with the given rows (a day's data is written once)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def read_rows(path: str) -> List[SlotRow]:
    if not os.path.isfile(path):
        return []
    rows: List[SlotRow] = []
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(SlotRow(**{k: r.get(k) for k in CSV_HEADER}))
    return rows
