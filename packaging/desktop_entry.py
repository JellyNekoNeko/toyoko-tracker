from __future__ import annotations

import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from toyoko_tracker.desktop import main


def _write_startup_error() -> None:
    try:
        from toyoko_tracker.settings import CONFIG_DIR

        directory = Path(CONFIG_DIR)
    except Exception:
        directory = Path(tempfile.gettempdir()) / "toyoko-tracker"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "desktop-startup-error.log").open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n")
            traceback.print_exc(file=stream)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _write_startup_error()
        raise
