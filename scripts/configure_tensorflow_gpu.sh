#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "missing virtual environment: $VENV_DIR" >&2
  exit 1
fi

tf_dir="$("$PYTHON_BIN" - <<'PY'
import importlib.util
from pathlib import Path

spec = importlib.util.find_spec("tensorflow")
if spec is None or spec.origin is None:
    raise SystemExit("tensorflow is not installed")
print(Path(spec.origin).parent)
PY
)"

site_packages="$("$PYTHON_BIN" - <<'PY'
import sysconfig

print(sysconfig.get_paths()["purelib"])
PY
)"

libdirs=(
  cublas
  cuda_cupti
  cuda_nvrtc
  cuda_runtime
  cudnn
  cufft
  curand
  cusolver
  cusparse
  nccl
  nvjitlink
)

(
  cd "$tf_dir"
  for libdir in "${libdirs[@]}"; do
    if [[ -d "../nvidia/$libdir/lib" ]]; then
      ln -sf ../nvidia/"$libdir"/lib/*.so* .
    fi
  done
)

ptxas_path="$site_packages/nvidia/cuda_nvcc/bin/ptxas"
if [[ -x "$ptxas_path" ]]; then
  ln -sf "$ptxas_path" "$VENV_DIR/bin/ptxas"
fi

echo "configured TensorFlow GPU shared-library links in $tf_dir"
