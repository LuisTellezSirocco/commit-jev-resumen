"""Audit built distributions and smoke-test a wheel outside the source checkout."""

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from check_publish import local_secrets, scan_blob

ROOT = Path(__file__).resolve().parents[1]
SMOKE = """
import json
import sysconfig
from pathlib import Path
import pymupdf
import jevdocs
from jevdocs.core import load_catalog, workspace_root
from jevdocs.catalog.crear_peticiones import build_requests

assert Path(jevdocs.__file__).is_relative_to(sysconfig.get_path("purelib"))
assert workspace_root() == Path.cwd()
bank, manifest = load_catalog()
assert len(bank) == 235 and len(manifest["nucleo"]) == 49
Path("data").mkdir()
Path("data/index.json").write_text(json.dumps({
    "created_at": "synthetic", "models": [], "documents": [],
    "source_dir": str(Path.cwd() / "docs"),
    "run": {"requests": 0, "input_tokens": 0, "output_tokens": 0}
}))
Path("docs").mkdir()
with pymupdf.open() as pdf:
    pdf.new_page().insert_text((72, 72), "Synthetic document for an offline package smoke test.")
    pdf.save("docs/synthetic.pdf")
"""


def audit(name, content, secrets, terms):
    path = PurePosixPath(name)
    # Build metadata embeds README and dependency declarations; scan its contents too.
    metadata = any(part.endswith(".dist-info") for part in path.parts) or name == "PKG-INFO"
    if not metadata and not (
        name.startswith("jevdocs/") or name in {"README.md", "pyproject.toml", ".gitignore"}
    ):
        raise ValueError(f"Archivo inesperado en la distribución: {name}")
    issues = scan_blob("README.md" if metadata else name, "100644", content, secrets, terms)
    if issues:
        raise ValueError(f"Distribución no publicable: {name}: {', '.join(issues)}")


def main():
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("Se requiere exactamente un wheel y un sdist en dist/. Ejecuta uv build.")
    secrets = local_secrets(ROOT)
    terms_file = ROOT / "data/publish-private-terms.txt"
    terms = terms_file.read_text().splitlines() if terms_file.exists() else []
    with zipfile.ZipFile(wheels[0]) as archive:
        for entry in archive.infolist():
            if not entry.is_dir():
                audit(entry.filename, archive.read(entry), secrets, terms)
    with tarfile.open(sdists[0]) as archive:
        for entry in archive.getmembers():
            if entry.isdir():
                continue
            if not entry.isfile():
                raise ValueError("Enlace inesperado en el sdist")
            name = str(PurePosixPath(*PurePosixPath(entry.name).parts[1:]))
            audit(name, archive.extractfile(entry).read(), secrets, terms)
    with tempfile.TemporaryDirectory(prefix="atlas-wheel-") as directory:
        root = Path(directory)
        env = dict(os.environ)
        for key in ("PYTHONPATH", "JEV_WORKSPACE", "JEV_API_KEY", "JEV_MODEL"):
            env.pop(key, None)

        def run(*args):
            subprocess.run(args, cwd=root, env=env, check=True)

        run("uv", "venv", "--python", sys.executable, str(root / "venv"))
        bin_dir = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        cli = bin_dir / ("jevdocs.exe" if os.name == "nt" else "jevdocs")
        run(
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "-r",
            str(ROOT / "requirements.txt"),
            str(wheels[0]),
        )
        run(str(python), "-I", "-c", SMOKE)
        run(str(cli), "--help")
        run(str(cli), "build")
        html = (root / "output/index.html").read_text()
        assert all(
            marker not in html for marker in ("/* APP_CSS */", "/* APP_JS */", "/* DATA_JSON */")
        )
        assert len(json.loads((root / "output/index.json").read_text())["questions"]) == 235
        run(str(cli), "classify", "--dry-run")
        run(str(python), "-I", "-m", "jevdocs.catalog.crear_peticiones", "--help")
    print("Wheel y sdist revisados; CLI, catálogo, extracción y HTML funcionan fuera del checkout.")


if __name__ == "__main__":
    main()
