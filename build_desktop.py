"""Build the native desktop bundle for the current operating system."""

from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(ROOT / "packaging" / "toyoko-tracker.spec"),
        ],
        cwd=ROOT,
        check=True,
    )
    if sys.platform.startswith("linux"):
        output = ROOT / "dist" / "ToyokoTracker"
        shutil.copy2(ROOT / "packaging" / "icons" / "toyoko-tracker.png", output)
        shutil.copy2(ROOT / "packaging" / "ToyokoTracker.desktop", output)


if __name__ == "__main__":
    main()
