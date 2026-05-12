from pathlib import Path
import subprocess

import pytest

from claude_backup import git_ops


def test_is_git_repo(fresh_repo: Path, tmp_path: Path):
    assert git_ops.is_git_repo(fresh_repo)
    assert not git_ops.is_git_repo(tmp_path)


def test_head_hash_and_branch(fresh_repo: Path):
    h = git_ops.head_hash(fresh_repo)
    assert len(h) == 40
    assert git_ops.current_branch(fresh_repo) == "main"


def test_dirty_detection(fresh_repo: Path):
    assert not git_ops.is_working_tree_dirty(fresh_repo)
    (fresh_repo / "x.txt").write_text("dirty\n", encoding="utf-8")
    assert git_ops.is_working_tree_dirty(fresh_repo)


def test_remote_add_list(fresh_repo: Path, tmp_path: Path):
    bare = tmp_path / "mirror.git"
    git_ops.init_bare(bare)
    git_ops.add_remote(fresh_repo, "nas", str(bare))
    remotes = git_ops.list_remotes(fresh_repo)
    assert "nas" in remotes
    assert git_ops.has_remote(fresh_repo, "nas")
    assert not git_ops.has_remote(fresh_repo, "origin")


def test_push_to_bare(fresh_repo: Path, tmp_path: Path):
    bare = tmp_path / "mirror.git"
    git_ops.init_bare(bare)
    git_ops.add_remote(fresh_repo, "nas", str(bare))
    git_ops.push_all(fresh_repo, "nas")
    # bare 上应当能看到 main 分支
    refs = (bare / "refs" / "heads").iterdir()
    assert any(r.name == "main" for r in refs)


def test_tag_and_list(fresh_repo: Path):
    git_ops.tag(fresh_repo, "v0.0.1", message="first")
    tags = git_ops.list_tags(fresh_repo)
    assert "v0.0.1" in tags


def test_bundle_create_and_inspect(fresh_repo: Path, tmp_path: Path):
    dest = tmp_path / "out.bundle"
    git_ops.bundle_create(fresh_repo, dest)
    assert dest.exists() and dest.stat().st_size > 0
    heads = git_ops.bundle_list_heads(dest)
    assert any(name.endswith("main") for _, name in heads)


def test_log_oneline(fresh_repo: Path):
    entries = git_ops.log_oneline(fresh_repo, limit=10)
    assert len(entries) == 1
    assert entries[0][1] == "init"


def test_diff_summary(fresh_repo: Path):
    (fresh_repo / "new.txt").write_text("added\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fresh_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add new.txt"], cwd=fresh_repo, check=True)
    summary = git_ops.diff_summary(fresh_repo, "HEAD~1", "HEAD")
    assert "new.txt" in summary


def test_has_any_commit(fresh_repo: Path, empty_repo: Path):
    assert git_ops.has_any_commit(fresh_repo)
    assert not git_ops.has_any_commit(empty_repo)


def test_git_error_raises(fresh_repo: Path):
    with pytest.raises(git_ops.GitError):
        git_ops.run(["push", "no-such-remote"], cwd=fresh_repo)
