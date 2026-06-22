from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import platform
import shutil
import subprocess
import sys


PYTHON_DISTS = {
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "scikit-learn": "sklearn",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "openpyxl": "openpyxl",
    "statsmodels": "statsmodels",
    "jupyterlab": "jupyterlab",
    "notebook": "notebook",
    "ipykernel": "ipykernel",
    "torch": "torch",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
    "keras": "keras",
    "tensorflow": "tensorflow",
}


def dist_version(dist_name: str) -> str:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return "missing"


def module_status(module_name: str) -> str:
    return "ok" if importlib.util.find_spec(module_name) else "missing"


def r_version() -> str:
    rscript = shutil.which("Rscript")
    if not rscript:
        return "missing"
    result = subprocess.run(
        [rscript, "-e", "cat(as.character(getRversion()))"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return f"error: {result.stderr.strip()}"
    return result.stdout.strip()


def main() -> int:
    print(f"python_executable\t{sys.executable}")
    print(f"python_version\t{sys.version.replace(chr(10), ' ')}")
    print(f"platform\t{platform.platform()}")
    print()
    print("python_package\tdistribution_version\tmodule_status")
    for dist_name, module_name in PYTHON_DISTS.items():
        print(f"{dist_name}\t{dist_version(dist_name)}\t{module_status(module_name)}")
    print()
    print(f"R\t{r_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
