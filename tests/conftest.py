"""Test process isolation for persistent per-user application state."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile


_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="toyoko-tracker-tests-")
os.environ.setdefault("TOYOKO_TRACKER_CONFIG_DIR", _TEST_CONFIG_DIR)
atexit.register(shutil.rmtree, _TEST_CONFIG_DIR, True)
