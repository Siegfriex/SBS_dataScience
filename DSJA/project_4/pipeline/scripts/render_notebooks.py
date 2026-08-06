from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import nbformat
import yaml


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from notebook_templates.observed import make_notebook  # noqa: E402


SPEC_PATH = PIPELINE_ROOT / "notebook_specs/observed_dev.yaml"
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"


def _serialized(notebook: nbformat.NotebookNode) -> str:
    return nbformat.writes(notebook, version=nbformat.NO_CONVERT)


def render(mode: str) -> list[Path]:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    changed: list[Path] = []
    blocked: list[Path] = []
    NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    for stage in spec["stages"]:
        target = NOTEBOOK_ROOT / f"{stage['id']}.ipynb"
        desired = _serialized(
            make_notebook(
                stage["id"],
                stage["stageId"],
                stage["title"],
                stage["note"],
                stage["inputs"],
                stage["outputs"],
                stage["schemaVersion"],
                stage["inputManifestPath"],
                stage["requiredGate"],
                stage["nextUse"],
            )
        )
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current == desired:
            continue
        changed.append(target)
        diff = difflib.unified_diff(
            current.splitlines(), desired.splitlines(), fromfile=str(target), tofile=f"{target} (rendered)", n=2
        )
        print("\n".join(diff))
        if mode == "check":
            continue
        if target.exists() and mode == "render":
            blocked.append(target)
            continue
        target.write_text(desired, encoding="utf-8")
    if mode == "check" and changed:
        raise SystemExit(1)
    if blocked:
        print("Refusing to overwrite existing changed notebooks; rerun with --force.", file=sys.stderr)
        raise SystemExit(2)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Render deterministic P4 source notebooks from the stage registry.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--render", action="store_true")
    actions.add_argument("--force", action="store_true")
    args = parser.parse_args()
    mode = "check" if args.check else "force" if args.force else "render"
    for path in render(mode):
        print(path.relative_to(PIPELINE_ROOT))


if __name__ == "__main__":
    main()
