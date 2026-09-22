#!/usr/bin/env python3
"""Check actual Git blobs before publishing; never print matched secret values."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    ".gitignore",
    ".env.example",
    "README.md",
    "PUBLISHING.md",
    "requirements.txt",
    "iniciar.sh",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".editorconfig",
    ".prettierrc.json",
    ".prettierignore",
    "package.json",
    "package-lock.json",
    "Makefile",
}
PUBLIC_DIRS = {
    # catalog/ and web/ remain accepted for auditing commits before the package move.
    "catalog",
    "jevdocs",
    "web",
    "scripts",
    "tests",
    "examples",
    ".githooks",
    ".github",
    ".vscode",
}
PRIVATE_DIRS = {
    "docs",
    "data",
    "output",
    "exports",
    "tmp",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
}
TEXT_SUFFIXES = {".py", ".js", ".css", ".html", ".json", ".md", ".txt", ".sh", ".yml", ".yaml"}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:sk-(?:proj-)?|jv_live_|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{20,}"),
    re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        rb'(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[=:]\s*["\x27][A-Za-z0-9_+/=-]{24,}["\x27]'
    ),
]


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.PIPE)


def scan_blob(name, mode, content, private_values=(), private_terms=()):
    path = PurePosixPath(name)
    issues = []
    public = name in ROOT_FILES or (len(path.parts) > 1 and path.parts[0] in PUBLIC_DIRS)
    if not public or any(part in PRIVATE_DIRS for part in path.parts):
        issues.append("ruta no publicable")
    if any(part.startswith(".env") for part in path.parts) and name != ".env.example":
        issues.append("archivo de entorno privado")
    if name not in ROOT_FILES and not (
        path.parts[0] == ".githooks" and path.name in {"pre-commit", "pre-push"}
    ):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            issues.append("formato no autorizado")
    if mode not in {"100644", "100755"}:
        issues.append("enlace o submódulo no autorizado")
    if len(content) > 1_000_000 or b"\x00" in content or content.startswith(b"%PDF-"):
        issues.append("binario o artefacto generado")
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        issues.append("posible credencial")
    if any(value and value in content for value in private_values):
        issues.append("coincide con una credencial local")
    text = content.decode("utf-8", errors="replace").casefold()
    if any(
        term.casefold() in text or term.casefold() in name.casefold()
        for term in private_terms
        if term
    ):
        issues.append("referencia privada local")
    if re.search(r"/(?:Users|home)/[^\s/]+/", text, re.IGNORECASE):
        issues.append("ruta personal absoluta")
    return issues


def local_secrets(root):
    values = []
    for path in root.glob(".env*"):
        if path.name == ".env.example" or not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and re.search(r"key|secret|token|password", key, re.IGNORECASE):
                value = value.strip().strip('"\x27')
                if len(value) >= 12:
                    values.append(value.encode())
    for key, value in os.environ.items():
        if re.search(r"(?:API_KEY|ACCESS_TOKEN|CLIENT_SECRET|PASSWORD)$", key) and len(value) >= 12:
            values.append(value.encode())
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        action="store_true",
        help="Revisar todos los árboles de las referencias locales",
    )
    args = parser.parse_args()
    try:
        root = Path(git("rev-parse", "--show-toplevel").decode().strip())
        entries = set()
        if args.history:
            for commit in git("rev-list", "--all", cwd=root).decode().splitlines():
                for row in git("ls-tree", "-rz", "--full-tree", commit, cwd=root).split(b"\0"):
                    if not row:
                        continue
                    info, name = row.split(b"\t", 1)
                    mode, _kind, oid = info.decode().split()
                    entries.add((name.decode(), mode, oid))
        else:
            for row in git("ls-files", "--stage", "-z", cwd=root).split(b"\0"):
                if not row:
                    continue
                info, name = row.split(b"\t", 1)
                mode, oid, stage = info.decode().split()
                if stage != "0":
                    raise ValueError("Hay conflictos en el índice de Git")
                entries.add((name.decode(), mode, oid))
        secrets = local_secrets(root)
        terms_file = root / "data/publish-private-terms.txt"
        terms = terms_file.read_text().splitlines() if terms_file.exists() else []
        failed = []
        for name, mode, oid in sorted(entries):
            content = (
                git("cat-file", "blob", oid, cwd=root)
                if mode in {"100644", "100755", "120000"}
                else b""
            )
            issues = scan_blob(name, mode, content, secrets, terms)
            if issues:
                failed.append((name, issues))
        if failed:
            print("Publicación bloqueada por el control local:")
            for name, issues in failed:
                print(f"  {name}: {', '.join(issues)}")
            return 1
        print(
            f"Control de publicación correcto: {len(entries)} archivos/versiones revisados. No se muestran secretos."
        )
        return 0
    except (subprocess.CalledProcessError, ValueError, OSError):
        print(
            "No se pudo completar el control de Git; no se autoriza la publicación.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
