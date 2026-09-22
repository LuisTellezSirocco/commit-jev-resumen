import os

from jevdocs.core import JevClient, workspace_root


def test_runtime_files_follow_current_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.delenv("JEV_WORKSPACE", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("JEV_API_KEY=synthetic-test-key\n")
    assert workspace_root() == tmp_path
    client = JevClient()
    try:
        assert client.cache_dir == tmp_path / "data/cache"
        assert client.key == "synthetic-test-key"
    finally:
        client.close()


def test_workspace_override(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_WORKSPACE", str(tmp_path / "collection"))
    assert workspace_root() == tmp_path / "collection"


def test_importing_catalog_generators_does_not_write(tmp_path, monkeypatch):
    import importlib

    monkeypatch.chdir(tmp_path)
    for module in ("build_catalogue", "build_support"):
        importlib.reload(importlib.import_module(f"jevdocs.catalog.{module}"))
    assert not list(tmp_path.iterdir())
