#!/usr/bin/env python3
"""Lint and format-check a temporary copy of the Git index without modifying it."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_staged(root):
    root = Path(root)
    prettier = root / "node_modules/prettier/bin/prettier.cjs"
    if not prettier.is_file() or not shutil.which("node"):
        print("Falta Prettier o Node. Ejecuta make setup antes de crear un commit.")
        return 1
    rows = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    with tempfile.TemporaryDirectory(prefix="atlas-staged-") as directory:
        snapshot = Path(directory)
        for row in rows.split(b"\0"):
            if not row:
                continue
            info, raw_name = row.split(b"\t", 1)
            mode, oid, stage = info.decode().split()
            name = raw_name.decode()
            if stage != "0" or mode not in {"100644", "100755"}:
                print("El índice contiene conflictos, enlaces o submódulos; revisa git status.")
                return 1
            selected = (
                name.endswith(".py")
                or name.startswith("web/")
                or name
                in {
                    "pyproject.toml",
                    ".gitignore",
                    ".editorconfig",
                    ".prettierrc.json",
                    ".prettierignore",
                }
            )
            if selected:
                target = snapshot / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(
                    subprocess.check_output(["git", "cat-file", "blob", oid], cwd=root)
                )
        commands = [
            [sys.executable, "-m", "ruff", "check", "."],
            [sys.executable, "-m", "ruff", "format", "--check", "."],
            ["node", str(prettier), "--check", "web"],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=snapshot, check=False)
            if result.returncode:
                print("Corrige con make lint-fix / make format y vuelve a preparar los cambios.")
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(check_staged(Path(__file__).resolve().parents[1]))
