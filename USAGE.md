# ClaudeBackup 使用指南

面向终端用户。开发文档见 [README.md](README.md)。

---

## 一、安装

### 用安装包（推荐）

1. 从 [Releases](../../releases) 下载 `ClaudeBackup-Setup-v<版本>.exe` 双击
2. UAC 弹窗 → 允许
3. 默认装到 `D:\Program Files\ClaudeBackup\`，下一步到底
4. 完成后桌面会出现 "ClaudeBackup" 图标，开始菜单可搜到

### 或从源码部署（开发场景）

```powershell
cd <你 clone 的目录>
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Clean   # 打包 → dist\
# 双击 deploy.cmd → UAC → 自动同步 dist\ 到 %ProgramFiles%\ClaudeBackup\
```

### 前置依赖

ClaudeBackup 调 git CLI 做备份，需要先装 [Git for Windows](https://gitforwindows.org/)。

启动 ClaudeBackup 时会自动检测——没装会弹提示给下载链接，装完重启 ClaudeBackup 即可。

### 首次启动（6 步引导）

第一次双击 ClaudeBackup 图标会自动弹出引导：

1. **欢迎** — 介绍这个工具
2. **概念** — Claude 自动备份 / 每日定时 / 重要版本发布 三种模式
3. **📂 选备份位置** — **必选**。给一个文件夹存所有备份数据。建议选 D 盘下的目录（比如 `D:\ClaudeBackup-Data`）、外置硬盘、或 NAS 网络盘上的目录。**不建议放 C:\\**（占系统盘）
4. **⚙️ 系统集成** — 推荐全勾点「立即应用」一键启用：右键菜单 + 自启托盘 + 每日定时备份。不勾的也能在 ⚙️ 设置里随时开
5. **添加第一个项目** — 选你想备份的代码目录
6. **试一次备份** — 演示备份流程

走完之后才进主面板。**第 3 步不能跳**（备份位置必选）；第 4 步推荐但不强制。

### Claude Code 用户额外配置

如果你用 Claude Code 做开发，希望 Claude 写完代码后自动推备份到你的 NAS：编辑 `C:\Users\<你>\.claude\settings.json`，按 [README.md](README.md) 的"Stop hook"段落加配置。**朋友不用 Claude Code 可以忽略**。

---

## 二、卸载

### 用安装包卸载（推荐）

控制面板 → 程序和功能 → "ClaudeBackup" → 卸载，UAC 后会清干净 `D:\Program Files\ClaudeBackup\`。

### 还要清理的"周边"（安装包不会动这些）

```powershell
# 注：安装包卸载（控制面板 → 卸载）会自动跑下面 1-3 项；以下命令是给「源码部署」/
# 「装错版本要彻底清干净」场景用的手动等价物。

# 1. 取消 Task Scheduler 每日任务
& "$env:ProgramFiles\ClaudeBackup\_internal\scripts\uninstall-task-scheduler.ps1"

# 2. 取消资源管理器右键菜单
& "$env:ProgramFiles\ClaudeBackup\_internal\scripts\uninstall-context-menu.ps1"

# 3. 取消登录自启动
& "$env:ProgramFiles\ClaudeBackup\_internal\scripts\uninstall-autostart.ps1"

# 4. 清用户配置（可选，里面有日志和你选过的备份位置等偏好）
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude-backup\"

# 5. 备份位置下的数据（**不会**自动删，需要时手动）
# 你之前选的备份位置（默认 D:\ClaudeBackup-Data 或类似）下面的：
#   git-backups\        bare 镜像
#   git-bundles\        时间快照
#   snapshots\          完整目录拷贝
```

### Claude Code 侧的 Stop hook

如果不想 Claude 写完代码自动推 NAS，编辑 `%USERPROFILE%\.claude\settings.json` 把 `hooks.Stop` 那段去掉。

---

## 三、常见错误

### "git add -A 超时（项目工作树过大）"

**症状**：备份对话框显示 ⚠️，但完整目录已上传 NAS。

**原因**：项目里有 `node_modules` / `.playwright-mcp` 等海量小文件，git 索引扫不完。

**修复**：项目根加 `.gitignore`：

```
node_modules/
.next/
dist/
build/
__pycache__/
.venv/
.playwright-mcp/
```

> 注：从 v0.1.1 起，注册新项目时检测到这些目录会自动写一份。但**已注册**的旧项目需要你手动加。

---

### "项目里有 Windows 保留名文件 'NUL'"

**症状**：错误对话框点出该提示，并附删除指引。

**原因**：某个 shell 命令（如 `cmd > NUL` 在 PowerShell/Git Bash 里被当成普通文件名而非黑洞）误生成的文件。`NUL` 是 Windows 设备名，git 读它返回空 → 索引失败。

**修复**（PowerShell）：

```powershell
# 把路径换成对话框给的那个
Remove-Item -LiteralPath '\\?\<你的项目完整路径>\NUL' -Force
```

`\\?\` 长路径前缀是关键——直接 `del NUL` / `Remove-Item NUL` 都会被 Windows 解释成"操作黑洞设备"，没用。

同类保留名：`CON` / `PRN` / `AUX` / `COM1`-`COM9` / `LPT1`-`LPT9`，处理方法一样。

---

### "WinError 5 拒绝访问"删除项目时

**症状**：在 GUI 删除一个已注册的项目，报权限错误。

**原因**：NAS 上的 git bare 镜像（`<备份位置>\git-backups\<proj>.git\objects\`）里的对象文件是只读的，`shutil.rmtree` 默认不能动。

**修复**：v0.1.1 起删除流程会自动 chmod 后重试。如果你装的还是早于 v0.1.1 的版本，请重新部署一次。

---

### 备份位置不可达 / "系统找不到指定的路径"

**症状**：GUI 启动时弹错；或备份时报"找不到路径"。

**原因 + 修复**：取决于你之前选的备份位置类型。

- **本地硬盘**（如 `D:\ClaudeBackup-Data`）：硬盘没接好或盘符变了。检查"此电脑"看 D 盘是否还在
- **外置硬盘**：插上即可
- **NAS 网络盘**（映射的盘符如 `Y:\`）：

  ```powershell
  net use Y:                                                # 看是否还映射着
  net use Y: \\NAS-IP\share /user:<账号> <密码> /persistent:yes  # 不在就重新映射
  ```

GUI 启动时备份位置不可达**不会**让 GUI 崩——只是新建项目和备份会失败。修好之后无需重启 GUI。

### 如何修改备份位置 / 迁移已有数据

⚙️ 设置 → 📂 备份位置 → "修改..." 按钮

- 选了新文件夹后会问你**是否自动迁移旧数据**
- 选"自动迁移" → robocopy 整树拷过去 + 自动改所有项目的 git remote 指向新位置 + 改 registry。完成后**旧数据保留**（让你手动确认无误后再删）
- 选"取消" → 啥也不做
- 数据量大时（几个 GB）迁移可能要几分钟到几十分钟，进度对话框会显示
- 迁移失败时旧数据 / 旧配置都不动，安全

---

### "我改了定时时间但没有自动备份"

**症状**：在 ⚙️ 设置里改了 `每日定时备份` 时间，到点没动静。

**原因**：单纯改时间不会注册 Task Scheduler；需要在该开关下面**勾选启用**。

**修复**：⚙️ 设置 → 每日定时备份 → 启用。或在 PowerShell 验证：

```powershell
schtasks /Query /TN "ClaudeBackup-Daily"
```

返回 "ERROR: 系统找不到..." 说明任务没注册，回 GUI 启用即可。

---

### "改了文件但定时备份还是被跳过"

**症状**：每天定时跑完，发现没新增 bundle。

**原因**：v0.1.0 早期版本的变化检测有漏洞——只看 git HEAD 是否变化，工作树脏改动会被忽略。

**修复**：v0.1.1 起：
- 完整目录快照（`<备份位置>\snapshots\<proj>\<时间戳>\`）每次定时**无条件生成**
- git push / bundle 仅在有变化时跑

需要 v0.1.1 才会这样。如果还有这问题，重新部署一次。

---

### 部署 / 安装包失败 PowerShell parser error

**症状**：`The string is missing the terminator: "` 之类，引号闭合错误。

**原因**：PowerShell 5.1 默认按 GBK 读 `.ps1` 文件，UTF-8 中文会被解析成乱码。

**修复**：v0.1.1 起所有 `.ps1` 都带 UTF-8 BOM，PowerShell 5.1 能正确读。如果你看到这个错，说明部署的是早于 v0.1.1 的版本，重新打包部署一次即可。

---

## 四、备份数据在哪

```
<备份位置>\git-backups\
├── .registry.json              # 项目登记表
├── <项目>.git\                 # bare 镜像（git push --all 进去，可 git clone 出来）
└── ...

<备份位置>\git-bundles\
├── <项目>\
│   ├── 2026-05-09.bundle       # 当日时间快照
│   ├── 2026-05-09_143022.bundle  # 同一天多次快照按时间戳区分
│   └── releases\
│       └── v1.0.0.bundle       # 发布版本归档

<备份位置>\snapshots\                   # 完整目录拷贝（"时光机"——直接看文件、直接拷回）
└── <项目>\
    └── 2026-05-09_143022\      # 排除 .git / node_modules / __pycache__
        └── ...
```

**最容易理解的恢复路径**：直接进 `<备份位置>\snapshots\<项目>\<时间戳>\` 把文件拷回去——不需要懂 git。

如果想恢复 git 历史，从 bare 镜像 clone：

```powershell
git clone <备份位置>\git-backups\<项目>.git <恢复目标目录>
```

---

## 五、卡住时怎么办

按这个顺序自查：

1. **看错误对话框是否有具体提示**——v0.1.1 错误对话框已支持滚动 + 复制按钮，stderr 不会被截断
2. **看日志** `%USERPROFILE%\.claude-backup\logs\`（按月一文件，`hook.log` 是 Claude 自动备份的专用日志）
3. **看备份位置是否还能访问** ⚙️ 设置 → 📂 备份位置 看显示路径，进资源管理器试着打开
4. **看 Task Scheduler 任务历史** Win+R → `taskschd.msc` → `ClaudeBackup-Daily` → 历史选项卡
5. **手动跑一次** `& "$env:ProgramFiles\ClaudeBackup\cli\ClaudeBackup-cli.exe" backup <项目路径>` 看 console 输出

排查不出来时，把日志 + 错误截图发给开发者。
