#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

if [[ "$PYTHON_BIN" == ".venv/bin/python" && -d ".venv" ]]; then
  tf_dir="$("$PYTHON_BIN" - <<'PY'
import importlib.util
from pathlib import Path

spec = importlib.util.find_spec("tensorflow")
print(Path(spec.origin).parent if spec and spec.origin else "")
PY
)"

  if [[ -n "$tf_dir" ]]; then
    export LD_LIBRARY_PATH="/usr/lib/wsl/lib:$tf_dir:${LD_LIBRARY_PATH:-}"
  else
    export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}"
  fi
else
  export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}"
fi

exec "$PYTHON_BIN" scripts/check_gpu.py
