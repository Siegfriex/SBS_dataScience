from __future__ import annotations

import shutil
import subprocess


COMMANDS = {
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "java": ["java", "-version"],
    "javac": ["javac", "-version"],
    "maven": ["mvn", "-version"],
    "gradle": ["gradle", "-version"],
}


def run_command(command: list[str]) -> str:
    executable = command[0]
    if shutil.which(executable) is None:
        return "missing"

    result = subprocess.run(command, check=False, text=True, capture_output=True)
    output = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0:
        return f"error: {' '.join(output)}"
    return output[0] if output else "ok"


def main() -> int:
    print("dev_tool\tstatus")
    for name, command in COMMANDS.items():
        print(f"{name}\t{run_command(command)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
