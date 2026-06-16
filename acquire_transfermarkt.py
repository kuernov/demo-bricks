"""
acquire_transfermarkt.py
-------------------------
Pobiera kompletny dataset Kaggle 'davidcariboo/player-scores' i kopiuje go
do Unity Catalog Volume.

Wymaga zmiennych środowiskowych KAGGLE_USERNAME i KAGGLE_KEY ustawionych
PRZED wywołaniem main() — najlepiej przez Databricks Secrets, nie wpisanych
na twardo w kodzie / repo. Wymaga też `%pip install kaggle` w notatniku.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M")
DATASET = "davidcariboo/player-scores"


def log_event(log_lines: list[str], src: str, size: int, status: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"{ts} | {src} | {size} bytes | {status} | {msg}")
    print(f"[{status}] {src}: {msg}")


def _flush_log(log_lines: list[str], volume_logs: str) -> None:
    log_dir = Path(volume_logs)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"acq_transfermarkt_{TIMESTAMP}.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )


def _get_kaggle_credentials() -> tuple[str, str]:
    """Najpierw zmienne środowiskowe (gdyby ktoś wolał je ustawić ręcznie),
    a w razie ich braku — Databricks Secrets przez databricks-sdk. SDK
    autoryzuje się sam w oparciu o kontekst uruchomienia (notebook, Python
    script task — wszędzie tak samo), więc nie potrzeba `dbutils`."""
    if "KAGGLE_USERNAME" in os.environ and "KAGGLE_KEY" in os.environ:
        return os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"]

    import base64

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    username = base64.b64decode(
        w.secrets.get_secret(scope="pdzd", key="kaggle_username").value
    ).decode("utf-8")
    key = base64.b64decode(
        w.secrets.get_secret(scope="pdzd", key="kaggle_key").value
    ).decode("utf-8")
    return username, key


def main(volume_dest: str, volume_logs: str) -> None:
    """volume_dest np. /Volumes/workspace/default/pdzd/input/transfermarkt_raw
    — tu wylądują wszystkie pliki z bundla (players.csv, player_valuations.csv, ...)."""
    log_lines: list[str] = []
    log_event(log_lines, "SYSTEM", 0, "INFO", "Starting Transfermarkt acquisition process")

    try:
        username, key = _get_kaggle_credentials()
        os.environ["KAGGLE_USERNAME"] = username
        os.environ["KAGGLE_KEY"] = key
    except Exception as e:  # noqa: BLE001
        log_event(
            log_lines,
            "TRANSFERMARKT",
            0,
            "ERROR",
            f"Brak danych logowania Kaggle (env vars i Databricks Secrets 'pdzd'): {e}",
        )
        _flush_log(log_lines, volume_logs)
        sys.exit(-1)

    from kaggle.api.kaggle_api_extended import KaggleApi  # import po ustawieniu env vars

    dest_dir = Path(volume_dest)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        print(f"Downloading full dataset from Kaggle: {DATASET} ...")
        try:
            api = KaggleApi()
            api.authenticate()
            api.dataset_download_files(DATASET, path=str(tmp), force=True, unzip=True)
        except Exception as e:  # noqa: BLE001
            log_event(
                log_lines, "TRANSFERMARKT", 0, "ERROR", f"Failed to download dataset from Kaggle: {e}"
            )
            _flush_log(log_lines, volume_logs)
            return

        files = [p for p in tmp.rglob("*") if p.is_file()]
        if not files:
            log_event(
                log_lines, "TRANSFERMARKT", 0, "ERROR",
                f"Dataset downloaded but no files were found in {tmp}",
            )
        else:
            for local_file in files:
                rel_path = local_file.relative_to(tmp)
                target = dest_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_file, target)
                size = local_file.stat().st_size
                log_event(
                    log_lines, "TRANSFERMARKT", size, "SUCCESS", f"Saved {rel_path} to Volume"
                )
            log_event(
                log_lines, "TRANSFERMARKT", 0, "INFO",
                f"Copied {len(files)} files from full dataset to Volume",
            )

    log_event(log_lines, "SYSTEM", 0, "INFO", "Transfermarkt acquisition process finished")
    _flush_log(log_lines, volume_logs)
    print("--- PROCESS FINISHED ---")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Użycie: python acquire_transfermarkt.py <volume_input_dest> <volume_logs>")
        sys.exit(-1)
    main(sys.argv[1], sys.argv[2])