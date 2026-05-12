# Contributing to ClaudeBackup

感谢你愿意贡献。先读完这份再开 PR。

## 怎么报 bug

1. 先在 [issues](../../issues) 里搜一下，看是不是已经被报过
2. 没有 → 新开 issue，标题用「[bug] 一句话症状」格式
3. 必须带：
   - Windows 版本（如 Win 11 24H2）
   - ClaudeBackup 版本（顶栏 `ⓘ` 关于对话框可见，或 `ClaudeBackup-cli.exe --version`）
   - 复现步骤
   - 错误对话框的"复制错误信息"输出（如果有）
   - `~/.claude-backup/logs/<月份>.log` 末尾 100 行

## 怎么提需求

issues 里开「[feature] 一句话描述」。说清楚：
- 你用 ClaudeBackup 想解决的具体问题
- 当前是怎么绕过的 / 为什么绕不过
- 期望的最终体验

不接受「应该加 X」这种没问题描述的提议。

## 怎么贡献代码

### 本地开发环境

```powershell
git clone https://github.com/787978079/ClaudeBackup
cd ClaudeBackup
pip install -e ".[dev,build]"
pytest                       # 81 tests
python -m claude_backup.cli --help
```

### 改之前

- 大改（>5 文件 / 新模块）先开 issue 讨论，避免做了又不被采纳
- 小改（bug fix / 拼写 / 单点优化）直接发 PR

### 提 PR

- **一个 PR 一件事**。不要把 bug fix + 新功能 + 重构混一起
- 标题用一句话说改了什么（约定式 commit 不强制但欢迎）
- 描述里写：
  - 解决了什么问题 / 加了什么能力
  - 为什么这样做（如果有多个方案选项）
  - 怎么验证（命令 / 截图 / 测试名）
- **必须**附 `pytest` 全绿截图或日志末尾几行
- UI 改动**必须**附前后对比截图（可用 `.visual-smoke/_smoke.py` 出图）

### 代码风格

- Python 3.11+，type hint 该有的地方都有
- 字符串外部接口用中文，内部 log / 异常 message 可英文
- 注释解释 **why**，不解释 **what**（代码自身能说清的不要重复）
- 禁止给函数 / 类加多段 docstring，1-2 句足够；复杂逻辑必要时分函数

### 测试

- 新增业务逻辑 → 必须配 pytest
- bug fix → 加一个能复现该 bug 的 test
- GUI 改动可以不上 pytest（手测 + 视觉验证），但要在 PR 描述里写**怎么手测**
- 测试**不能依赖**真实 NAS / 真实 GitHub / 真实 git commits 历史 — 用 `tests/conftest.py` 里的 `fresh_repo` fixture

### 不要做的事

- 不要改备份数据格式（git-backups / bundles / snapshots 结构）— 升级会破坏老用户
- 不要在 `core.py` 加 GUI 依赖（`from PySide6 ...` 一律放 `gui/` 下）
- 不要硬编码本机路径（用 `paths.py` 的动态解析）
- 不要往 `claude_backup/gui/assets/` 之外放二进制资源
- 不要碰 `installer/ClaudeBackup.iss` 的 `AppId` GUID — 改了 = 升级被识别成新应用

## 发版流程（仅维护者）

1. PR 全部 merge 到 main
2. 升 `claude_backup/__init__.py` + `pyproject.toml` + `installer/ClaudeBackup.iss` + `installer/version_info.txt` 四处版本号
3. 写 `CHANGELOG.md` 新版本节
4. `git commit -m "Release vX.Y.Z" && git tag -a vX.Y.Z -m "<topline>"`
5. `powershell scripts/build.ps1 -Clean` 打包
6. `ISCC.exe installer/ClaudeBackup.iss` 出 setup.exe
7. `git push origin main --tags && gh release create vX.Y.Z -F CHANGELOG.md <安装包>`

## 行为准则

对人尊重，对代码挑剔。任何形式的歧视 / 人身攻击 / 骚扰 → 项目维护者会直接拒绝你的贡献并锁 issue。
