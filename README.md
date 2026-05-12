# ClaudeBackup

<p align="center">
  <img src="claude_backup/gui/assets/icons/claudebackup-128.png" alt="ClaudeBackup" width="96" />
</p>

<p align="center">
  <b>Windows 桌面工具 · Git 三层备份 · 写完代码自动归档</b>
</p>

<p align="center">
  <a href="USAGE.md">使用手册</a> ·
  <a href="CHANGELOG.md">更新记录</a> ·
  <a href="CONTRIBUTING.md">贡献指南</a> ·
  <a href="SECURITY.md">安全策略</a>
</p>

---

## 它解决什么

写代码（特别是用 Claude Code 这类 AI 编程）时，你可能很快积累几十个项目，散落在各
处的本地目录。等想"回到上周三的版本"时，发现：
- git commit 历史不一定及时（写到一半的脏改动没 commit）
- 单一磁盘哪天就坏了 — 没有异地副本
- GitHub 不适合放半成品（私有仓库满了 / 不想公开）

**ClaudeBackup** 做三件事，全自动：
1. **NAS bare 镜像**：每次 push 把项目完整 git 历史推到一个备份位置（NAS / 外置盘 / 大盘都行）
2. **时间快照 bundle**：每次备份生成一个 git bundle 文件，按日期归档
3. **完整目录拷贝**：跟 git 无关的"时光机" — 直接看 / 直接拷回，零门槛恢复

可选挂载点：
- **Claude Code Stop hook**：Claude 写完代码瞬间自动备份
- **Task Scheduler 每日定时**：到点扫描所有项目，有变化才备份
- **资源管理器右键菜单**：在任意文件夹右键 → "📦 Claude Backup"

## 架构

```
Claude Code (Stop hook) ──push──┐
                                ├──> <backup-location>\git-backups\<proj>.git   (bare 镜像)
桌面 GUI / 托盘 / 右键菜单 ─────┤    <backup-location>\git-bundles\<proj>\         (时间快照)
Task Scheduler (每日扫描) ──────┘    <backup-location>\snapshots\<proj>\          (完整目录拷贝)
                                └──> GitHub (重大版本 release)
```

- **后端**：`claude_backup/` 纯 Python + stdlib + subprocess 调 git
- **GUI**：PySide6（深色 ElevenLabs 风）
- **三入口同后端**：GUI / 托盘 / 右键菜单 / CLI 共享 `core.py`
- **零网络遥测**：除用户主动点「发布到 GitHub」外，本应用不发任何外部请求

## 安装（终端用户）

最简单：从 [Releases](../../releases) 下 `ClaudeBackup-Setup-v*.exe` 双击装。
详细步骤、卸载、常见错误 → 看 **[USAGE.md](USAGE.md)**。

## 开发（贡献者）

```powershell
git clone <repo-url> ClaudeBackup
cd ClaudeBackup
pip install -e ".[dev,build]"
pytest                              # 81 tests
python -m claude_backup.cli --help

# 打包
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Clean
# 编译 Inno Setup 安装包（需先装 Inno Setup 6）
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ClaudeBackup.iss
```

## 数据位置

| 项 | 路径 | 说明 |
|---|---|---|
| 应用安装 | `%ProgramFiles%\ClaudeBackup\` | Inno Setup 装到 64-bit Program Files |
| 用户配置 | `%USERPROFILE%\.claude-backup\` | 偏好 + 日志 + 注册的项目列表 |
| 备份数据 | `<用户在 onboarding 选的位置>` | 三个子目录：git-backups / git-bundles / snapshots |

## 项目结构

```
ClaudeBackup/
├── claude_backup/          # Python 包
│   ├── core.py             # 业务逻辑（GUI / 托盘 / CLI 共用）
│   ├── git_ops.py          # git CLI 包装
│   ├── change_detect.py    # 变化检测
│   ├── health.py           # 健康检查扫描
│   ├── system_integration.py  # 调 PowerShell 注册 OS 集成
│   └── gui/                # PySide6 GUI 层
├── installer/              # Inno Setup 配置 + exe 资源元数据
├── scripts/                # PowerShell：打包 / 部署 / OS 集成 install/uninstall
├── tests/                  # pytest（81 测试，覆盖核心逻辑）
└── docs/templates/         # 可复用模板（onboarding / usage guide）
```

## 与 Anthropic 的关系

**没有关系**。"ClaudeBackup" 是描述性名称（备份 Claude Code 写的代码），
本项目**不隶属于、也未获得 Anthropic 的认可或赞助**。Claude / Claude Code 是
Anthropic, PBC 的商标。

## 协议

[MIT](LICENSE) © 2026 项目作者
