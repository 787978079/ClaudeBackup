from pathlib import Path
import subprocess

import pytest

from claude_backup import core, git_ops, registry, paths


def test_init_project_creates_mirror_and_remote(fresh_repo: Path):
    res = core.init_project(fresh_repo)
    assert res.created_mirror
    assert res.added_remote
    assert (paths.NAS_BACKUPS_DIR / f"{fresh_repo.name}.git").exists()
    assert git_ops.has_remote(fresh_repo, "nas")
    assert (paths.NAS_BUNDLES_DIR / fresh_repo.name).exists()


def test_init_project_idempotent(fresh_repo: Path):
    core.init_project(fresh_repo)
    res2 = core.init_project(fresh_repo)
    assert not res2.created_mirror
    assert not res2.added_remote


def test_init_project_with_github_url(fresh_repo: Path):
    res = core.init_project(fresh_repo, github_url="https://github.com/x/y.git")
    assert res.added_github_remote
    remotes = git_ops.list_remotes(fresh_repo)
    assert remotes.get("origin") == "https://github.com/x/y.git"


def test_init_auto_inits_non_git_dir(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "f.txt").write_text("x", encoding="utf-8")
    core.init_project(plain)
    assert git_ops.is_git_repo(plain)


def test_backup_pushes_and_creates_bundle(fresh_repo: Path):
    core.init_project(fresh_repo)
    res = core.backup_project(fresh_repo)
    assert res.pushed_to_nas
    assert res.bundle_path is not None
    assert res.bundle_path.exists()
    assert res.new_head is not None


def test_backup_creates_dir_snapshot_with_full_tree(fresh_repo: Path):
    """手动备份默认会把整个项目目录拷贝到 NAS/snapshots/."""
    (fresh_repo / "subdir").mkdir()
    (fresh_repo / "subdir" / "deep.txt").write_text("deep\n", encoding="utf-8")
    (fresh_repo / "node_modules").mkdir()
    (fresh_repo / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    core.init_project(fresh_repo)
    res = core.backup_project(fresh_repo)
    assert res.dir_snapshot_path is not None
    assert res.dir_snapshot_path.exists()
    # README 应在
    assert (res.dir_snapshot_path / "README.md").exists()
    # 子目录文件应在
    assert (res.dir_snapshot_path / "subdir" / "deep.txt").exists()
    # .git 必须排除
    assert not (res.dir_snapshot_path / ".git").exists()
    # node_modules 必须排除
    assert not (res.dir_snapshot_path / "node_modules").exists()


def test_backup_handles_empty_repo(empty_repo: Path):
    """空仓库（git init 但无 commit）手动备份也能跑通：自动 commit + push + bundle + dir."""
    (empty_repo / "hello.txt").write_text("hi\n", encoding="utf-8")
    core.init_project(empty_repo)
    res = core.backup_project(empty_repo)
    assert res.auto_committed is True
    assert res.pushed_to_nas
    assert res.bundle_path and res.bundle_path.exists()
    assert res.dir_snapshot_path and (res.dir_snapshot_path / "hello.txt").exists()


def test_backup_dirty_uses_temp_branch(fresh_repo: Path):
    """工作树脏 → 自动 commit 到临时分支，主分支 HEAD 不变."""
    core.init_project(fresh_repo)
    main_head_before = git_ops.head_hash(fresh_repo)
    (fresh_repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    res = core.backup_project(fresh_repo)
    assert res.auto_committed is True
    # 主分支 HEAD 不该变
    cur_branch = git_ops.current_branch(fresh_repo)
    assert cur_branch == "main"
    main_head_after = git_ops.head_hash(fresh_repo)
    assert main_head_after == main_head_before
    # 临时分支应存在
    branches = subprocess.run(["git", "branch", "--list", "auto/snapshot-*"],
                              cwd=fresh_repo, capture_output=True, text=True).stdout
    assert "auto/snapshot-" in branches


def test_backup_clean_tree_no_auto_commit(fresh_repo: Path):
    core.init_project(fresh_repo)
    res = core.backup_project(fresh_repo)
    assert res.auto_committed is False


def test_mirror_excludes_via_gitignore(fresh_repo: Path):
    """.gitignore 里写的目录 mirror 时应自动排除（走 git ls-files 路径）."""
    (fresh_repo / ".gitignore").write_text("secrets/\n*.log\n", encoding="utf-8")
    (fresh_repo / "secrets").mkdir()
    (fresh_repo / "secrets" / "key.txt").write_text("TOPSECRET", encoding="utf-8")
    (fresh_repo / "debug.log").write_text("noisy", encoding="utf-8")
    (fresh_repo / "src.py").write_text("print(1)", encoding="utf-8")
    core.init_project(fresh_repo)
    res = core.backup_project(fresh_repo)
    snap = res.dir_snapshot_path
    assert snap is not None and snap.exists()
    # gitignore 排除项不该在快照里
    assert not (snap / "secrets").exists(), "gitignore'd dir 不该被备份"
    assert not (snap / "debug.log").exists(), "gitignore'd file 不该被备份"
    # 普通文件应在
    assert (snap / "src.py").exists()
    assert (snap / ".gitignore").exists()


def test_retention_keep_last_n_dir_snapshots(fresh_repo: Path):
    """跑 N+M 次备份，最旧的 M 个目录快照应被自动清理."""
    from claude_backup import config as cfg_mod
    cfg = cfg_mod.load()
    cfg.retention_keep_last_dir_snapshots = 2
    cfg_mod.save(cfg)

    core.init_project(fresh_repo)
    # 跑 5 次，每次改个文件让 mtime 推进
    import time as _t
    for i in range(5):
        (fresh_repo / f"f{i}.txt").write_text(f"v{i}\n", encoding="utf-8")
        core.backup_project(fresh_repo)
        _t.sleep(1.05)  # 让目录名 / mtime 错开

    snaps = sorted((paths.NAS_SNAPSHOTS_DIR / fresh_repo.name).iterdir())
    assert len(snaps) == 2, f"应保留 2 个最新目录快照，实际 {len(snaps)}"


def test_restore_from_dir_snapshot(fresh_repo: Path):
    """目录快照 → 恢复 → 项目内容回到快照状态."""
    core.init_project(fresh_repo)
    # 第一次备份（含 README.md）
    res1 = core.backup_project(fresh_repo)
    snap_v1 = res1.dir_snapshot_path
    assert snap_v1 is not None

    # 改项目内容
    (fresh_repo / "README.md").write_text("CHANGED\n", encoding="utf-8")
    (fresh_repo / "newfile.txt").write_text("new", encoding="utf-8")

    # 恢复到 v1
    rr = core.restore_from_dir_snapshot(snap_v1, fresh_repo)
    assert rr.restored_count >= 1
    # README 应该回到 "hello"
    assert (fresh_repo / "README.md").read_text(encoding="utf-8") == "hello\n"
    # newfile 应被清掉（不在 v1 里）
    assert not (fresh_repo / "newfile.txt").exists()
    # safety backup 应在
    assert rr.safety_backup.exists()


def test_backup_skip_if_no_change(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    res = core.backup_project(fresh_repo, skip_if_no_change=True)
    # git push/bundle 跳过
    assert res.skipped
    assert "no changes" in (res.skip_reason or "")
    # 但目录快照应该已生成（每次都备份目录树是产品决策）
    assert res.dir_snapshot_path is not None
    assert res.dir_snapshot_path.exists()


def test_backup_no_bundle(fresh_repo: Path):
    core.init_project(fresh_repo)
    res = core.backup_project(fresh_repo, make_bundle=False)
    assert res.pushed_to_nas
    assert res.bundle_path is None


def test_backup_unregistered_project_raises(fresh_repo: Path):
    with pytest.raises(ValueError):
        core.backup_project(fresh_repo)


def test_list_backup_points_includes_dir_snapshot(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    res = core.list_backup_points(fresh_repo)
    kinds = {p.kind for p in res.points}
    assert "dir_snapshot" in kinds


def test_release_creates_tag_and_archive_bundle(fresh_repo: Path):
    core.init_project(fresh_repo)
    res = core.release_project(fresh_repo, "v0.1.0", description="first",
                               push_github=False)
    assert res.tag_created
    assert res.pushed_to_nas
    assert not res.pushed_to_github   # 没配 github_url 也没启用
    assert res.bundle_path and res.bundle_path.exists()
    assert "v0.1.0" in git_ops.list_tags(fresh_repo)


def test_release_idempotent_tag(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.release_project(fresh_repo, "v1", push_github=False)
    res = core.release_project(fresh_repo, "v1", push_github=False)
    assert not res.tag_created   # 已存在不重新打


def test_list_file_history_finds_versions_in_snapshots_and_commits(fresh_repo: Path):
    """单文件历史能从目录快照 + git commit 各取出版本."""
    core.init_project(fresh_repo)
    # v1: 备份当前内容（README.md）
    core.backup_project(fresh_repo)
    # v2: 改 README + commit + 再备份
    (fresh_repo / "README.md").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fresh_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=fresh_repo, check=True)
    core.backup_project(fresh_repo)

    pts = core.list_backup_points(fresh_repo, limit_commits=20).points
    versions = core.list_file_history(fresh_repo, "README.md", pts)
    kinds = [v.point.kind for v in versions]
    assert "dir_snapshot" in kinds
    assert "commit" in kinds
    # 至少找到两个版本（v1 + v2）
    assert len(versions) >= 2


def test_read_file_at_point_dir_snapshot(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    pts = core.list_backup_points(fresh_repo).points
    snap = next(p for p in pts if p.kind == "dir_snapshot")
    data = core.read_file_at_point(snap, "README.md", fresh_repo)
    # Windows git autocrlf 可能把 \n 转 \r\n；只确认有 hello 即可
    assert b"hello" in data


def test_read_file_at_point_git_ref(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    pts = core.list_backup_points(fresh_repo).points
    commit_pt = next(p for p in pts if p.kind == "commit")
    data = core.read_file_at_point(commit_pt, "README.md", fresh_repo)
    assert b"hello" in data


def test_restore_single_file_overwrites_with_safety_backup(fresh_repo: Path):
    """单文件恢复：覆写当前内容 + 把原文件存到安全备份目录."""
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    # 改 README
    (fresh_repo / "README.md").write_text("BROKEN\n", encoding="utf-8")
    # 列版本，找一个 dir_snapshot 版本
    pts = core.list_backup_points(fresh_repo).points
    snap = next(p for p in pts if p.kind == "dir_snapshot")
    res = core.restore_single_file(fresh_repo, "README.md", snap)
    assert res.bytes_written > 0
    # README 应回到 "hello"（不再含 BROKEN）
    text = (fresh_repo / "README.md").read_text(encoding="utf-8")
    assert "hello" in text and "BROKEN" not in text
    # 安全备份存在且含 "BROKEN"
    assert res.safety_path is not None and res.safety_path.exists()
    assert "BROKEN" in res.safety_path.read_text(encoding="utf-8")


def test_compare_dir_snapshots_detects_added_removed_modified(tmp_path: Path):
    """两个目录快照对比：能列出 A/D/M 文件."""
    s1 = tmp_path / "snap_old"
    s2 = tmp_path / "snap_new"
    s1.mkdir()
    s2.mkdir()
    # old: a.txt + b.txt
    (s1 / "a.txt").write_text("hello", encoding="utf-8")
    (s1 / "b.txt").write_text("same", encoding="utf-8")
    (s1 / "sub").mkdir()
    (s1 / "sub" / "deep.txt").write_text("deep-old", encoding="utf-8")
    # new: b.txt（同内容） + c.txt + sub/deep.txt（改了）
    (s2 / "b.txt").write_text("same", encoding="utf-8")
    (s2 / "c.txt").write_text("brand new", encoding="utf-8")
    (s2 / "sub").mkdir()
    (s2 / "sub" / "deep.txt").write_text("deep-NEW", encoding="utf-8")

    res = core.compare_dir_snapshots(s1, s2)
    statuses = {(s, p) for s, p in res.files}
    assert ("D", "a.txt") in statuses, "a.txt 应被标为删除"
    assert ("A", "c.txt") in statuses, "c.txt 应被标为新增"
    assert ("M", "sub/deep.txt") in statuses, "sub/deep.txt 应被标为修改"
    # b.txt 内容相同，不该出现
    assert all(p != "b.txt" for _, p in res.files)
    # summary 含数字
    assert "新增 1" in res.summary
    assert "删除 1" in res.summary
    assert "修改 1" in res.summary


def test_compare_dir_snapshots_missing_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        core.compare_dir_snapshots(tmp_path / "nope1", tmp_path / "nope2")


def test_compare_refs(fresh_repo: Path):
    core.init_project(fresh_repo)
    (fresh_repo / "another.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fresh_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add another"], cwd=fresh_repo, check=True)
    res = core.compare_refs(fresh_repo, "HEAD~1", "HEAD")
    assert any("another.txt" in fn for _, fn in res.files)


def test_list_backup_points_includes_commits_and_bundles(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    res = core.list_backup_points(fresh_repo)
    kinds = {p.kind for p in res.points}
    assert "commit" in kinds
    assert "bundle" in kinds


def test_scheduled_daily_no_git_changes_still_creates_dir_snapshot(fresh_repo: Path):
    """git 没变化时定时备份不再算 skipped — 因为仍生成了新的目录快照."""
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    snap_root = paths.NAS_SNAPSHOTS_DIR / fresh_repo.name
    before = len(list(snap_root.iterdir())) if snap_root.exists() else 0
    res = core.scheduled_daily()
    assert fresh_repo.name in res.backed_up, "无变化也应算 backed_up（dir_snapshot 生成了）"
    after = len(list(snap_root.iterdir()))
    assert after == before + 1, "应该多了 1 个目录快照"


def test_scheduled_daily_backs_up_changed(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    (fresh_repo / "change.txt").write_text("c\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fresh_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=fresh_repo, check=True)
    res = core.scheduled_daily()
    assert fresh_repo.name in res.backed_up


def test_scheduled_daily_handles_dirty_with_temp_branch(fresh_repo: Path):
    core.init_project(fresh_repo)
    core.backup_project(fresh_repo)
    # 弄脏
    (fresh_repo / "dirty.txt").write_text("d\n", encoding="utf-8")
    res = core.scheduled_daily()
    assert fresh_repo.name in res.backed_up
    # 主分支 HEAD 不该被改（dirty 进了临时分支）
    branches = subprocess.run(
        ["git", "branch", "--list"], cwd=fresh_repo, capture_output=True, text=True
    ).stdout
    assert "auto/snapshot-" in branches
    # 当前还在 main
    cur = git_ops.current_branch(fresh_repo)
    assert cur == "main"


# ---------- _diagnose_git_add_error ----------

class TestDiagnoseGitAddError:
    def test_detects_nul_file(self):
        stderr = (
            "error: short read while indexing NUL\n"
            "error: NUL: failed to insert into database\n"
            "error: unable to index file 'NUL'\n"
            "fatal: adding files failed\n"
        )
        msg = core._diagnose_git_add_error(stderr)
        assert msg is not None
        assert "Windows 保留名" in msg
        assert "NUL" in msg

    def test_detects_nested_path_with_reserved_name(self):
        stderr = "error: unable to index file 'subdir/CON.txt'\nfatal: adding files failed\n"
        msg = core._diagnose_git_add_error(stderr)
        assert msg is not None
        assert "CON" in msg

    def test_detects_short_read_fallback(self):
        # short read 但 stderr 没明确 unable to index file 'X'
        stderr = "error: short read while indexing somefile\nfatal: oops\n"
        msg = core._diagnose_git_add_error(stderr)
        assert msg is not None
        assert "Windows 保留名" in msg or "其它进程" in msg

    def test_unknown_error_returns_none(self):
        msg = core._diagnose_git_add_error("error: pathspec 'foo' did not match any files")
        assert msg is None

    def test_empty_stderr(self):
        assert core._diagnose_git_add_error("") is None
        assert core._diagnose_git_add_error(None) is None  # type: ignore[arg-type]


# ---------- _ensure_gitignore / init 自动 .gitignore ----------

class TestEnsureGitignore:
    def test_no_heavy_dirs_no_write(self, tmp_path: Path):
        wrote, heavy = core._ensure_gitignore(tmp_path)
        assert wrote is False
        assert heavy == []
        assert not (tmp_path / ".gitignore").exists()

    def test_heavy_dir_triggers_write(self, tmp_path: Path):
        (tmp_path / "node_modules").mkdir()
        wrote, heavy = core._ensure_gitignore(tmp_path)
        assert wrote is True
        assert "node_modules" in heavy
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "node_modules/" in gi
        assert "由 ClaudeBackup" in gi  # 模板标识

    def test_existing_gitignore_not_overwritten(self, tmp_path: Path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / ".gitignore").write_text("custom_user_content\n", encoding="utf-8")
        wrote, heavy = core._ensure_gitignore(tmp_path)
        assert wrote is False
        assert "node_modules" in heavy  # 仍报告检测结果
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "custom_user_content\n"

    def test_multiple_heavy_dirs_reported(self, tmp_path: Path):
        for d in ("node_modules", "dist", "__pycache__"):
            (tmp_path / d).mkdir()
        wrote, heavy = core._ensure_gitignore(tmp_path)
        assert wrote is True
        assert set(heavy) >= {"node_modules", "dist", "__pycache__"}


def test_init_writes_gitignore_when_node_modules_present(fresh_repo: Path):
    (fresh_repo / "node_modules").mkdir()
    res = core.init_project(fresh_repo)
    assert res.wrote_gitignore is True
    assert "node_modules" in res.detected_heavy_dirs
    assert (fresh_repo / ".gitignore").exists()


def test_init_no_gitignore_when_clean_project(fresh_repo: Path):
    res = core.init_project(fresh_repo)
    # fresh_repo 只有 README.md，不该被认为需要 .gitignore
    assert res.wrote_gitignore is False
    assert res.detected_heavy_dirs == []
    assert not (fresh_repo / ".gitignore").exists()


def test_init_keeps_existing_gitignore(fresh_repo: Path):
    (fresh_repo / "node_modules").mkdir()
    (fresh_repo / ".gitignore").write_text("# my own rules\n*.tmp\n", encoding="utf-8")
    res = core.init_project(fresh_repo)
    assert res.wrote_gitignore is False
    assert (fresh_repo / ".gitignore").read_text(encoding="utf-8") == "# my own rules\n*.tmp\n"


# ---------- migrate_nas_root ----------

def test_shift_path_prefix_basic():
    out = core._shift_path_prefix(
        r"C:\old\nas\git-backups\proj.git",
        Path(r"C:\old\nas"),
        Path(r"D:\new"),
    )
    assert out is not None
    # Path 拼接结果（Windows 用 \）
    assert out.lower() == r"D:\new\git-backups\proj.git".lower()


def test_shift_path_prefix_no_match():
    assert core._shift_path_prefix(
        r"C:\unrelated\path",
        Path(r"C:\old\nas"),
        Path(r"D:\new"),
    ) is None


def test_migrate_nas_root_changes_paths_and_remote(fresh_repo: Path, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch):
    """迁移：robocopy 数据 + 切 config + 改 registry + 改 git remote URL."""
    # 1. 注册一个项目（在当前 NAS_ROOT 也就是 conftest 设的 tmp_path/nas）
    res = core.init_project(fresh_repo)
    old_root = paths.NAS_ROOT
    assert (old_root / "git-backups" / f"{fresh_repo.name}.git").exists()

    # 2. 在新 root 上做迁移
    new_root = tmp_path / "new_nas"
    # env 仍指向 old_root（autouse fixture 设的），需要 monkeypatch.setenv 切到新 root
    # 否则迁移完 paths.NAS_ROOT 立刻又变 env 指的旧路径——所以要把 env 改成新 root 才模拟
    # 真实运行（无 env、走 config）。这里直接 unset env，让 paths 走 config
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.set_nas_root(old_root)  # 把当前 root 写入 config
    paths.reload_cache()

    result = core.migrate_nas_root(new_root)

    assert result.old_root == old_root
    assert result.new_root == new_root
    assert result.projects_updated == 1
    assert result.git_remotes_updated == 1
    # 3. 新位置应该有数据
    assert (new_root / "git-backups" / f"{fresh_repo.name}.git").exists()
    # 4. registry 路径已切到新根
    paths.reload_cache()
    reg = registry.load()
    e = reg.find_by_path(fresh_repo)
    assert e is not None
    assert str(new_root) in e.nas_mirror
    assert str(new_root) in e.bundle_dir
    # 5. 项目本地 git remote nas 也指向新位置
    remotes = git_ops.list_remotes(fresh_repo)
    assert str(new_root) in remotes["nas"]


def test_migrate_nas_root_rejects_same_path(fresh_repo: Path, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.set_nas_root(tmp_path / "nas")
    paths.reload_cache()
    with pytest.raises(ValueError, match="新位置和旧位置相同"):
        core.migrate_nas_root(tmp_path / "nas")
