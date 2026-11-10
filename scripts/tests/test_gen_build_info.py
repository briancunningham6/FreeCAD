import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "gen-build-info.py"
_spec = importlib.util.spec_from_file_location("gen_build_info", SCRIPT)
gbi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gbi)


def git(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True, env=env,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "checkout", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("one\n")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_clean_repo_facts(repo):
    f = gbi.git_facts(str(repo))
    assert re.fullmatch(r"[0-9a-f]{40}", f["git"])
    assert f["dirty"] is False
    assert f["dirty_paths"] == []
    assert f["branch"] == "main"
    assert f["describe"]


def test_dirty_repo_lists_modified_tracked_files(repo):
    (repo / "a.txt").write_text("two\n")
    (repo / "new.txt").write_text("untracked\n")
    f = gbi.git_facts(str(repo))
    assert f["dirty"] is True
    assert f["dirty_paths"] == ["a.txt"]


def test_dirty_paths_capped_at_50(repo):
    for i in range(60):
        (repo / f"f{i}.txt").write_text("x\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "many")
    for i in range(60):
        (repo / f"f{i}.txt").write_text("y\n")
    f = gbi.git_facts(str(repo))
    assert f["dirty"] is True
    assert len(f["dirty_paths"]) == 50


def test_detached_head_branch_is_none(repo):
    git(repo, "checkout", "-q", "--detach")
    assert gbi.git_facts(str(repo))["branch"] is None


def test_no_git_dir_yields_null_git_facts(tmp_path):
    f = gbi.git_facts(str(tmp_path))
    assert set(f) == {"git", "describe", "branch", "dirty", "dirty_paths"}
    for k in ("git", "describe", "branch", "dirty"):
        assert f[k] is None
    assert f["dirty_paths"] == []


def _make_upstream_merge(repo):
    git(repo, "checkout", "-q", "--orphan", "U")
    git(repo, "rm", "-rq", "--cached", ".")
    (repo / "u.txt").write_text("upstream\n")
    git(repo, "add", "u.txt")
    git(repo, "commit", "-q", "-m", "upstream commit")
    u = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-f", "main")
    git(repo, "merge", "-q", "--allow-unrelated-histories", "-m",
        f"Merge upstream FreeCAD main {u[:10]}", "U")
    (repo / "b.txt").write_text("after\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "after merge")
    return u


def test_upstream_base_from_sync_merge(repo):
    u = _make_upstream_merge(repo)
    r = gbi.upstream_base(str(repo))
    assert r["base"] == u
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["base_date"])


def test_upstream_base_none_without_sync_merge(repo):
    assert gbi.upstream_base(str(repo)) == {"base": None, "base_date": None}


def test_build_manifest_shape(repo):
    facts = {"versions": {"qt": "6"}, "toolchain": {"sdk": None}, "options": {"flags": {}}}
    now = datetime(2026, 11, 10, 16, 6, 7, tzinfo=timezone.utc)
    m = gbi.build_manifest(facts, str(repo), now)
    assert m["schema"] == 1
    assert m["built_at"] == "2026-11-10T16:06:07Z"
    assert m["versions"] == {"qt": "6"}
    assert m["fork"]["branch"] == "main"
    assert m["upstream"] == {"base": None, "base_date": None}


def test_write_if_changed_ignores_built_at(tmp_path):
    p = tmp_path / "BUILD-INFO.json"
    m = {"schema": 1, "built_at": "2026-01-01T00:00:00Z", "versions": {"qt": "6.11.1"}}
    assert gbi.write_if_changed(m, str(p)) is True
    assert p.read_text() == json.dumps(m, indent=2, sort_keys=True) + "\n"
    os.utime(p, (1000, 1000))
    m2 = dict(m, built_at="2027-01-01T00:00:00Z")
    assert gbi.write_if_changed(m2, str(p)) is False
    assert p.stat().st_mtime == 1000
    m3 = dict(m2, versions={"qt": "6.12.0"})
    assert gbi.write_if_changed(m3, str(p)) is True


def test_cli_always_exits_zero(tmp_path):
    out = tmp_path / "out.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--srcdir", str(tmp_path),
         "--facts", str(tmp_path / "missing.json"), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    data = json.loads(out.read_text())
    assert "error" in data and data["schema"] == 1
    assert r.stdout.strip() == "BUILD-INFO.json: updated"
