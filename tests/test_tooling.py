import importlib.util
import os
import shutil
import subprocess
import sys
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


def test_lockfile_valid_without_user_uv_configuration(tmp_path):
    for name in ("pyproject.toml", "uv.lock", "README.md", ".python-version"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "empty-config")
    env["UV_PYTHON"] = sys.executable
    for name in ("UV_CONFIG_FILE", "UV_EXCLUDE_NEWER", "UV_NO_CONFIG", "VIRTUAL_ENV"):
        env.pop(name, None)
    result = subprocess.run(
        ["uv", "lock", "--check", "--offline"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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
