import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_publish.py"
spec = importlib.util.spec_from_file_location("publish_guard", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_denies_private_paths_and_disguised_pdf():
    for path in [
        "docs/private.pdf",
        "output/index.html",
        ".env.production",
        "exports/chat.md",
        "scripts/file.pdf",
    ]:
        assert guard.scan_blob(path, "100644", b"data")
    assert guard.scan_blob("examples/renamed.txt", "100644", b"%PDF-1.7 content")
    assert guard.scan_blob("web/app.js", "120000", b"../.env")


def test_detects_local_secret_without_disclosing_value():
    secret = b"temporary-example-value-12345"
    issues = guard.scan_blob("web/app.js", "100644", secret, private_values=[secret])
    assert issues and secret.decode() not in str(issues)
    assert guard.scan_blob(
        "README.md", "100644", b"Internal project: SAMPLE_PRIVATE", private_terms=["SAMPLE_PRIVATE"]
    )
    assert not guard.scan_blob(".env.example", "100644", b"JEV_API_KEY=\nJEV_MODEL=jev-1.13.0\n")


def test_checks_index_instead_of_worktree(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    (tmp_path / "README.md").write_bytes(b"%PDF-1.7 disguised")
    git("add", "README.md")
    (tmp_path / "README.md").write_text("Clean worktree cannot conceal staged data.")
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1


def test_checks_deleted_files_in_history(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.name", "Synthetic Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "document.pdf").write_bytes(b"%PDF-1.7 synthetic")
    git("add", ".")
    git("-c", "core.hooksPath=/dev/null", "commit", "-m", "Synthetic fixture")
    git("rm", "document.pdf")
    git("-c", "core.hooksPath=/dev/null", "commit", "-m", "Remove fixture")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--history"], cwd=tmp_path, capture_output=True
    )
    assert result.returncode == 1
