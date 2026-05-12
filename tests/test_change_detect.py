from pathlib import Path
import subprocess

from claude_backup import change_detect, git_ops, registry


def _register(repo: Path, name: str = "myproj") -> registry.ProjectEntry:
    e = registry.ProjectEntry(
        name=name,
        path=str(repo),
        nas_mirror=str(repo) + ".git",
        bundle_dir=str(repo) + "_b",
    )
    registry.upsert(e)
    return e


def test_never_backed_up_means_changes(fresh_repo: Path):
    _register(fresh_repo)
    s = change_detect.detect(fresh_repo)
    assert s.has_changes
    assert "never" in s.reason


def test_no_changes_when_head_matches(fresh_repo: Path):
    _register(fresh_repo)
    head = git_ops.head_hash(fresh_repo)
    registry.update_last_backup(fresh_repo, head)
    s = change_detect.detect(fresh_repo)
    assert not s.has_changes
    assert "no changes" in s.reason


def test_dirty_tree_means_changes(fresh_repo: Path):
    _register(fresh_repo)
    head = git_ops.head_hash(fresh_repo)
    registry.update_last_backup(fresh_repo, head)
    (fresh_repo / "scratch.txt").write_text("x", encoding="utf-8")
    s = change_detect.detect(fresh_repo)
    assert s.has_changes
    assert s.dirty


def test_new_commit_detected(fresh_repo: Path):
    _register(fresh_repo)
    old = git_ops.head_hash(fresh_repo)
    registry.update_last_backup(fresh_repo, old)
    (fresh_repo / "more.txt").write_text("more\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fresh_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "more"], cwd=fresh_repo, check=True)
    s = change_detect.detect(fresh_repo)
    assert s.has_changes
    assert "new commits" in s.reason
