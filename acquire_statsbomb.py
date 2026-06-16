"""
acquire_statsbomb.py
---------------------
Pobiera selektywnie foldery events/lineups/matches z repozytorium
StatsBomb open-data i zapisuje je do Unity Catalog Volume.

Odpowiednik acquire_statsbomb.sh, ale bez `hdfs dfs` — Volume jest
zamontowany jak normalny system plików, więc piszemy do niego bezpośrednio.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import requests

TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M")
URL_SB = "https://github.com/statsbomb/open-data/archive/refs/heads/master.zip"
SELECTED_PREFIXES = ("data/events/", "data/lineups/", "data/matches/")


def log_event(log_lines: list[str], src: str, size: int, status: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"{ts} | {src} | {size} bytes | {status} | {msg}")
    print(f"[{status}] {src}: {msg}")


def _flush_log(log_lines: list[str], volume_logs: str) -> None:
    log_dir = Path(volume_logs)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"acq_statsbomb_{TIMESTAMP}.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )


def _validate_path(path: str, label: str) -> None:
    if not path.startswith("/"):
        raise ValueError(
            f"{label}='{path}' nie jest ścieżką absolutną — sprawdź pole Parameters "
            "tego taska (prawdopodobnie literówka albo przypadkowo dopisana flaga, np. '-f')."
        )


def main(volume_dest: str, volume_logs: str) -> None:
    """volume_dest np. /Volumes/workspace/default/pdzd/input
    — utworzy w nim podfoldery events/, lineups/, matches/."""
    _validate_path(volume_dest, "volume_dest")
    _validate_path(volume_logs, "volume_logs")

    log_lines: list[str] = []
    log_event(log_lines, "SYSTEM", 0, "INFO", "Starting selective extraction")

    dest_dir = Path(volume_dest)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        zip_path = tmp / "sb_raw.zip"

        print("Downloading archive...")
        try:
            with requests.get(URL_SB, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
        except Exception as e:  # noqa: BLE001
            log_event(log_lines, "STATSBOMB", 0, "ERROR", f"Download failed: {e}")
            _flush_log(log_lines, volume_logs)
            return

        print("Extraction in progress...")
        extract_dir = tmp / "extracted"
        extract_dir.mkdir()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                members = [
                    m for m in zf.namelist() if any(p in m for p in SELECTED_PREFIXES)
                ]
                zf.extractall(extract_dir, members=members)
        except Exception as e:  # noqa: BLE001
            log_event(log_lines, "STATSBOMB", 0, "ERROR", f"Unzip failed: {e}")
            _flush_log(log_lines, volume_logs)
            return

        # Znajdź folder 'data' wewnątrz wypakowanej struktury (ignorując nesting master-master)
        data_path = next(extract_dir.rglob("data"), None)
        if data_path is None or not data_path.is_dir():
            log_event(
                log_lines, "STATSBOMB", 0, "ERROR", "Could not find 'data' folder in extraction"
            )
            _flush_log(log_lines, volume_logs)
            return

        total_size = sum(f.stat().st_size for f in data_path.rglob("*") if f.is_file())

        print("Kopiowanie danych (events, lineups, matches) do Volume...")
        for folder in ("events", "lineups", "matches"):
            src_folder = data_path / folder
            if src_folder.is_dir():
                shutil.copytree(src_folder, dest_dir / folder, dirs_exist_ok=True)

        log_event(
            log_lines,
            "STATSBOMB",
            total_size,
            "SUCCESS",
            f"Selective folders saved to Volume (run {TIMESTAMP})",
        )

    _flush_log(log_lines, volume_logs)
    print("--- PROCESS FINISHED ---")


if __name__ == "__main__":
    # Ustaw na sztywno ścieżki do Unity Catalog
    DEST =   "/Volumes/workspace/default/pdzd/input"
    LOGS = "/Volumes/workspace/default/pdzd/logs/acquisition"
    
    main(DEST, LOGS)