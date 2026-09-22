import importlib.util
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("staged_guard", ROOT / "scripts/check_staged.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_ruff_version_aligned_with_dependencies():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = config["tool"]["ruff"]["required-version"]
    assert f"ruff{version}" in config["dependency-groups"]["dev"]


def test_format_hook_checks_staged_content_without_modifying_it(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path)

    git("init", "-b", "main")
    (tmp_path / "pyproject.toml").write_text('[tool.ruff]\ntarget-version = "py312"\n')
    source = tmp_path / "example.py"
    source.write_text("answer=  1\n")
    git("add", ".")
    original_index = git("show", ":example.py")
    source.write_text("answer = 1\n")
    # The invalid Python formatting must fail before the frontend checker runs.
    stub = tmp_path / "node_modules/prettier/bin/prettier.cjs"
    stub.parent.mkdir(parents=True)
    stub.write_text("")
    monkeypatch.setattr(guard.shutil, "which", lambda _: "node")
    assert guard.check_staged(tmp_path) != 0
    assert git("show", ":example.py") == original_index
    assert source.read_text() == "answer = 1\n"
