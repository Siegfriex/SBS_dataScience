from __future__ import annotations

import ctypes
import shutil
import subprocess
from pathlib import Path


CUDA_ERROR_NAMES = {
    0: "CUDA_SUCCESS",
    100: "CUDA_ERROR_NO_DEVICE",
    35: "CUDA_ERROR_INSUFFICIENT_DRIVER",
    804: "CUDA_ERROR_FORWARD_COMPATIBILITY_NOT_SUPPORTED",
}


def run(command: list[str]) -> tuple[int | None, str]:
    if shutil.which(command[0]) is None:
        return None, "missing"
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    output = (result.stdout or result.stderr).strip().replace("\n", " | ")
    return result.returncode, output or "ok"


def libcuda_status(lib_name: str) -> str:
    try:
        cuda = ctypes.CDLL(lib_name)
        cu_init = cuda.cuInit
        cu_init.argtypes = [ctypes.c_uint]
        cu_init.restype = ctypes.c_int
        code = cu_init(0)
        name = CUDA_ERROR_NAMES.get(code, "UNKNOWN")
        return f"loaded; cuInit={code} ({name})"
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}"


def python_gpu_status() -> list[str]:
    lines: list[str] = []
    try:
        import torch

        lines.append(f"torch.version\t{torch.__version__}")
        lines.append(f"torch.cuda_compiled\t{torch.version.cuda}")
        lines.append(f"torch.cuda_available\t{torch.cuda.is_available()}")
        lines.append(f"torch.cuda_device_count\t{torch.cuda.device_count()}")
        if torch.cuda.is_available():
            lines.append(f"torch.cuda_device_0\t{torch.cuda.get_device_name(0)}")
    except Exception as exc:
        lines.append(f"torch\terror: {type(exc).__name__}: {exc}")

    try:
        import tensorflow as tf

        lines.append(f"tensorflow.version\t{tf.__version__}")
        lines.append(f"tensorflow.built_with_cuda\t{tf.test.is_built_with_cuda()}")
        lines.append(f"tensorflow.gpus\t{tf.config.list_physical_devices('GPU')}")
    except Exception as exc:
        lines.append(f"tensorflow\terror: {type(exc).__name__}: {exc}")

    return lines


def main() -> int:
    print("gpu_device")
    for path in ["/dev/dxg", "/dev/nvidia0", "/dev/nvidiactl"]:
        print(f"{path}\t{'present' if Path(path).exists() else 'missing'}")

    print("\ncommands")
    for name, command in {
        "nvidia-smi": ["nvidia-smi"],
        "nvcc": ["nvcc", "--version"],
    }.items():
        code, output = run(command)
        status = "missing" if code is None else f"exit={code}"
        print(f"{name}\t{status}\t{output}")

    print("\nlibcuda")
    for lib_name in ["libcuda.so.1", "/usr/lib/wsl/lib/libcuda.so.1"]:
        print(f"{lib_name}\t{libcuda_status(lib_name)}")

    print("\npython_gpu")
    for line in python_gpu_status():
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
