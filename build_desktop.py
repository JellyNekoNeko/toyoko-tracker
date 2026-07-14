"""Build the native desktop bundle for the current operating system."""

from __future__ import annotations

import subprocess
import sys
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


if __name__ == "__main__":
    main()
