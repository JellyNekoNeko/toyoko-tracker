#!/bin/zsh
set -u

cd "$(dirname "$0")"

PORT="${TOYOKO_PORT:-4170}"
URL="http://127.0.0.1:${PORT}/"
PYTHON_BIN=".venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "Starting Toyoko Chan WebUI..."
echo "Project: $(pwd)"
echo "URL: ${URL}"
echo

CURRENT_VERSION="$("${PYTHON_BIN}" -c 'import toyoko_tracker; print(toyoko_tracker.__version__)')"
INSTANCE_URL="$("${PYTHON_BIN}" -c '
import json
from toyoko_tracker.settings import INSTANCE_STATE_PATH
try:
    with open(INSTANCE_STATE_PATH, encoding="utf-8") as stream:
        state = json.load(stream)
    print(state.get("url", ""))
except (OSError, ValueError, TypeError):
    pass
')"

if [[ -n "${INSTANCE_URL}" ]]; then
  RUNNING_VERSION="$(curl -fsS --max-time 2 "${INSTANCE_URL}/health" 2>/dev/null | "${PYTHON_BIN}" -c '
import json, sys
try:
    print(json.load(sys.stdin).get("version", ""))
except (ValueError, TypeError):
    pass
' 2>/dev/null)"
  if [[ "${RUNNING_VERSION}" == "${CURRENT_VERSION}" ]]; then
    echo "Toyoko Chan v${CURRENT_VERSION} is already running."
    open "${INSTANCE_URL}" >/dev/null 2>&1 || true
    exit 0
  fi
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is occupied by another or older instance."
  echo "Starting v${CURRENT_VERSION} on another local port..."
fi

exec "${PYTHON_BIN}" -m toyoko_tracker
