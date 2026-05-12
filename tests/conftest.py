"""测试夹具：把 NAS_ROOT 和 USER_DATA_DIR 隔离到 tmp_path，避免污染真实 Y:\\."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把所有路径常量重定向到 tmp_path 子目录."""
    nas = tmp_path / "nas"
    user = tmp_path / "user"
    monkeypatch.setenv("CLAUDE_BACKUP_NAS_ROOT", str(nas))
    monkeypatch.setenv("USERPROFILE", str(user))

    # 必须 reload 以重新读取环境变量
    import importlib
    import claude_backup.paths as paths_mod
    importlib.reload(paths_mod)
    import claude_backup.config as cfg_mod
    importlib.reload(cfg_mod)
    import claude_backup.registry as reg_mod
    importlib.reload(reg_mod)
    import claude_backup.logger as log_mod
    importlib.reload(log_mod)
    import claude_backup.git_ops as git_mod
    importlib.reload(git_mod)
    import claude_backup.change_detect as cd_mod
    importlib.reload(cd_mod)
    import claude_backup.core as core_mod
    importlib.reload(core_mod)

    yield


@pytest.fixture
def fresh_repo(tmp_path: Path) -> Path:
    """创建一个有 1 个 commit 的临时 git 仓库，配好 user.email/user.name."""
    repo = tmp_path / "myproj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """创建一个 git init 但无 commit 的仓库."""
    repo = tmp_path / "emptyproj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    return repo
