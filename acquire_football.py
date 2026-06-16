"""
acquire_football.py
---------------------
Pobiera bezpośrednio pliki Excel (.xlsx/.xls) z football-data.co.uk dla
sezonów 1993-2025 i zapisuje je prosto do Unity Catalog Volume.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import requests

TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M")


def log_event(log_lines: list[str], src: str, size: int, status: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"{ts} | {src} | {size} bytes | {status} | {msg}")
    print(f"[{status}] {src}: {msg}")


def _flush_log(log_lines: list[str], volume_logs: str) -> None:
    log_dir = Path(volume_logs)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"acq_football_{TIMESTAMP}.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )


def try_download(url: str, dest_dir: Path, filename: str, log_lines: list[str]) -> bool:
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200 or not resp.content:
            return False
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / filename).write_bytes(resp.content)
        size = len(resp.content)
        print(f"Found {filename} ({size} bytes). Zapisano do Volume.")
        log_event(log_lines, "FOOTBALL_DATA", size, "SUCCESS", f"Saved {filename} to Volume")
        return True
    except Exception as e:  # noqa: BLE001
        log_event(log_lines, "FOOTBALL_DATA", 0, "ERROR", f"Failed to download/save {filename}: {e}")
        return False


def _validate_path(path: str, label: str) -> None:
    if not path.startswith("/"):
        raise ValueError(
            f"{label}='{path}' nie jest ścieżką absolutną — sprawdź pole Parameters "
            "tego taska (prawdopodobnie literówka albo przypadkowo dopisana flaga, np. '-f')."
        )


def main(volume_dest: str, volume_logs: str) -> None:
    """volume_dest np. /Volumes/workspace/default/pdzd/input/odds_excel"""
    _validate_path(volume_dest, "volume_dest")
    _validate_path(volume_logs, "volume_logs")

    log_lines: list[str] = []
    dest_dir = Path(volume_dest)
    log_event(
        log_lines, "SYSTEM", 0, "INFO",
        f"Starting Football-Data 1993-2026 acquisition (run {TIMESTAMP})",
    )

    for year in range(1993, 2026):
        next_year = year + 1
        season_code = f"{year % 100:02d}{next_year % 100:02d}"
        file_base = f"all-euro-data-{year}-{next_year}"

        print("---------------------------------------------------")
        print(f"Processing Season: {year}/{next_year} (Folder: {season_code})")

        url_xlsx = f"https://www.football-data.co.uk/mmz4281/{season_code}/{file_base}.xlsx"
        url_xls = f"https://www.football-data.co.uk/mmz4281/{season_code}/{file_base}.xls"

        if try_download(url_xlsx, dest_dir, f"{file_base}.xlsx", log_lines):
            continue
        if try_download(url_xls, dest_dir, f"{file_base}.xls", log_lines):
            continue

        print("Data not found on server for this season.")
        log_event(
            log_lines, "FOOTBALL_DATA", 0, "SKIP",
            f"No Excel file found for {year}/{next_year} (.xls or .xlsx)",
        )

    log_event(log_lines, "SYSTEM", 0, "INFO", "Football-Data Excel massive acquisition finished")
    _flush_log(log_lines, volume_logs)
    print("--- PROCESS FINISHED ---")


if __name__ == "__main__":
    # Ustaw na sztywno ścieżki do Unity Catalog
    DEST =   "/Volumes/workspace/default/pdzd/input/odds_excel"
    LOGS = "/Volumes/workspace/default/pdzd/logs/acquisition"
    
    main(DEST, LOGS)