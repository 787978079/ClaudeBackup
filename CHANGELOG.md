# Changelog

## v0.2.4 — 2026-05-13

UI 大改：emoji 全面替换为矢量图标 + timeline 文字间距修复。

### 🎨 全局 emoji → qtawesome 矢量图标（参考 Prompt help 设计哲学）

用户反馈 emoji 当 UI 图标"太丑"。参考 `Prompt help` 项目用 `qtawesome` (Font Awesome 6 Solid) 完全替代 emoji 图标。

- **新增** `claude_backup/gui/icons.py` — 50+ semantic key 映射到 fa6s/fa6b 矢量图标，统一封装 qtawesome 调用
- **新依赖** `qtawesome>=1.4`（已加 `pyproject.toml`）
- **替换覆盖整个 GUI**：
  - 顶栏 4 个 IconButton：🩺ⓘ❓⚙ → fa6s heart-pulse/info/question/gear
  - 右侧 4 个 ActionCard：📸🚀🔍⏱ → fa6s camera/rocket/code-compare/clock-rotate-left
  - 主面板按钮：📄📁📂🗑➕⚙️ → 矢量
  - 备份点列表（CompareDialog / FileHistoryDialog）：🔵🟢📁⭐ → fa6s code-commit/box-archive/folder-tree/star
  - 托盘菜单：📊📂📁 → 矢量；项目状态点 🟢🟡🔴⚪ → fa6s circle 不同颜色
  - 设置/onboarding/timeline/health_dialog：🧪🚀⏰🤖📁🩺 → 矢量 / 纯文字
- **保留** 状态文字的 unicode 几何符号（✓⏳●⚠ 在 STATUS_HEALTHY 等），跟 Prompt help 的 ✓ 已完成 标记同模式
- **PyInstaller spec** 加 `--collect-all qtawesome` 确保字体打进 bundle

### 🐛 timeline 文字挤兑修复

v0.2.3 把 `QListWidget` 背景改 transparent 后，原本 surface 色块的"上下 padding 视觉缓冲"消失了。加上 Qt 经典坑 `QListWidget::item { padding }` 在 `setItemWidget` 模式下被忽略 → 每行 timestamp/hash 紧贴 detail，相邻 row 也紧贴成一坨。

- `TimelineRow` `lay.setContentsMargins` 上下 6 → 12（row 自身上下 padding 撑开）
- `col.setSpacing` 2 → 6（timestamp 行 和 detail 行之间留白）

### 兼容性

- 纯视觉改动 + 1 个新依赖（qtawesome 已打进 setup.exe）。配置/registry/备份数据完全兼容 v0.2.x。

---

## v0.2.3 — 2026-05-13

根治"卡片矩形蒙版"视觉问题。

### 🎨 视觉（接 v0.2.2 未完成的扁平化）

v0.2.2 删了 1px 暗色 border 但卡片仍用 `surface (#1A1A1F)` 填充浮在 page `bg (#0E0E10)` 上，肉眼能看出"透明度更低的矩形蒙版"（用户精确诊断）。light 主题下 `surface=#FFFFFF` vs `bg=#FAFAFA` 同样有微差。

- **卡片填充全部改 `transparent`**：`QFrame#Card` / `QPushButton#ActionCard` / `QListWidget/Tree/Table` 的 `background-color` 从 `surface` → `transparent`。卡片彻底融进 page bg，靠间距和 H1/H3 标题区分层次。
- **全局 `QLabel { background: transparent }`**：默认 `QWidget {{ bg }}` 通配规则会染所有 QLabel 成 page bg 色，嵌在 hover 卡片等有 bg 填充的容器里时会显出"QLabel 内部矩形蒙版"（用户图 #11 直接观察到）。强制 transparent 让 QLabel 只画文字。
- **ActionCard hover 反馈保留**：hover 时仍显 `surface_hover` 填充作为悬停反馈 — hover 是临时主动状态，不形成静态框感。

### 兼容性

- 纯视觉改动。配置/registry/备份数据完全兼容 v0.2.x。

---

## v0.2.2 — 2026-05-13

UI 视觉扁平化：删除装饰性 1px 暗描边。

### 🎨 视觉

- **删 4 处装饰性 border**（全局 grep 30+ 处后分类）：
  - `QFrame#Card` — 详情卡描边 → 靠 surface 色与 page bg 对比区分
  - `QPushButton#ActionCard` — 右侧"立即备份/发布版本/对比版本/时间机器"卡，原本右下能看到 L 形暗线
  - `QListWidget/Tree/Table` — 嵌在 Card 内不需要双层框感
  - `TimelineRow` badge — 行内"提交/时间快照/目录快照/发布版本"徽章不再有暗描边切割
- **保留功能性 border**：TopBar/StatusBar 分隔线、按钮 hover 反馈、输入框定位、QCheckBox indicator、QMenu/QToolTip。
- **徽章背景填充加浓**（alpha 60 → 100），删 border 后靠纯色块承担类型识别。

### 兼容性

- 纯视觉改动，配置/registry/备份数据完全兼容 v0.2.1。

---

## v0.2.1 — 2026-05-13

P0 BUG 修复 + 多项体验改善 + 死代码清理。

### 🐛 P0 BUG 修复

- **`schedule_paused` 终于真的暂停**：GUI 状态栏显示"(已暂停)"但 Task Scheduler 仍到点跑备份 — `core.scheduled_daily` 完全不读该字段。`cmd_scheduled_daily` 起手读 `cfg.schedule_paused` 直接返回 0 + 写 hook 日志。
- **`_auto_refresh_tick` 不再静默吞异常**：之前 `except Exception: pass` 让磁盘掉线/项目目录被删等场景永远显示 stale 数据。改 `log.warning` + 状态栏标红"⚠️ 刷新失败"。
- **托盘 `_backup_cwd` / `_backup_all` 走 `run_async`**：之前同步串行备份 N 个项目，分钟级阻塞整个托盘菜单导致右键无响应。

### 🎨 视觉

- **时间线"线框"消除**：每行 `col.setSpacing(2)` 漏出更亮的 QListWidget surface，形成贯穿整行的横向亮条。改 `TimelineRow` 自身和内部 QLabel 都透明，彩色 bar 和徽章不受影响。

### 🛠 体验改进

- **全局"NAS"文案 → "备份位置/备份盘"**：用户实际可能选 D:\ 或外置硬盘，原文案让非 NAS 用户困惑。代码内部标识符 `NAS_REMOTE_NAME / nas_mirror` 等保留不变。
- **备份位置占用计算加 120s 超时 + 失败态 + 重入保护**，避免大库一直停在"计算中…"。
- **`restore_from_dir_snapshot` 完成后刷新 `last_backup_at`**：之前刚 restore 完会被误标"有未备份的修改"。
- **删项目清空数据二次确认默认按钮显式指向"保留数据"**，避免 Enter 误删。
- **onboarding 移除 `Y:\\` 推荐硬编码**（早期作者机器遗留）。

### 🗑 死代码清理

- 删 `BrowseBackupsDialog`（`dialogs.py`，~150 行，已被 `TimelineDialog` + `FileHistoryDialog` 替代）。
- 删 `cmd_hook_push`（`cli.py`，Stop hook 实际由 PowerShell 直接调 `git push`，此 Python 入口从未启用）。

### 兼容性

- 配置文件、registry、备份数据完全向后兼容 v0.2.x，升级无需操作。

---

## v0.2.0 — 2026-05-11

第一次系统化的体验打磨。重点在视觉品牌、Onboarding 修复、健康度可见性。

### 🐛 关键 BUG 修复

- **Onboarding 黑屏**：layout 构建被错误嵌套在 git 检测方法里，当 git 已安装（绝大多数用户）时早返回导致引导窗口空白。修复后所有用户都能正常看到 7 步引导。
- **托盘"打开 NAS"用静态路径**：模块级 `paths.NAS_ROOT` 是首次导入快照，用户改备份位置后菜单仍指向旧路径。改为运行时读取当前配置。
- **删项目时勾"清空 NAS"** 现在会弹**红色二次警告**，明确告知会删除哪些目录，默认选项"只移除登记，保留 NAS 数据"避免误操作。
- **Qt stylesheet 8 位 hex 颜色**：徽章 / 状态条用 `#RRGGBBAA` 形式 Qt 不识别，导致警告徽章变红色。改用 `rgba()` 显式 alpha。

### 🎨 视觉品牌

- **全新应用图标**：CB monogram + 紫蓝渐变（A78BFA → 5B6FFF），与 ElevenLabs 风格主题一致。
  - 多尺寸 PNG（16/24/32/48/64/128/256）+ 合成 .ico
  - 主窗口标题栏、Onboarding、空状态、托盘统一替换原 📦 emoji
- **顶栏紧凑化**：❓⚙️ 文字按钮 → 方形 IconButton，加入 🩺 健康检查入口
- **项目卡左侧 4px 色条**替代 ● 状态点，节省横向空间让长项目名能显示全
- **备份时间线卡片化**：左侧类型色条（commit=灰 / bundle=绿 / dir_snapshot=紫 / release=橙）+ 时间 + 类型徽章 + 详情副文字，可读性大幅提升

### ✨ 新功能

- **🩺 健康检查面板**（顶栏 / 托盘菜单可入口）
  - 扫描备份位置可达性、可写性、剩余空间
  - 检查每个项目：路径是否存在、git 仓库完整性、是否需要 .gitignore、是否长期未备份、nas remote 是否配好
  - 按严重度（严重 / 警告 / 提示）排序展示，每条问题附修复建议
- **🧪 备份位置测试按钮**（设置 → 备份位置）
  - 一键诊断路径可读 / 可写 / 可删 + 显示总容量/可用空间
- **🔍 项目搜索框**：左栏顶部实时过滤，按项目名或路径模糊匹配
- **📊 托盘菜单项目状态摘要**：右键菜单展开后看到每个项目的状态点（🟢🟡🔴⚪）+ 最近备份时间，不用打开主窗口

### 🛠 体验改进

- **主题切换实时生效**（dark ↔ light），无需重启 GUI
- **NAS 占用计算节流**：从每 15 秒 → 每 5 分钟（独立 timer），备份 / 恢复完成后主动刷一次。在大型备份库上 IO 大幅降低
- **进度对话框**成功 + 短摘要时 **2 秒自动关闭**；失败 / 长摘要保留窗口让用户读细节
- **错误对话框分级**：error / warn / info 视觉区分，长信息可折叠到 "Show Details"，加 "复制错误信息" 按钮
- 顶栏 IconButton hover 反馈一致，体积比文字按钮小约 50%

### 📦 构建

- `build.ps1` 加 `--icon` 参数（GUI + CLI 都带图标）
- `ClaudeBackup.iss` 加 `SetupIconFile`，安装程序自身也有图标
- 新增 `scripts/generate_icons.py`：用 Pillow 程序化生成全套图标，无外部 SVG 渲染依赖

### 兼容性

- 配置文件、registry、备份数据完全向后兼容 v0.1.x，升级无需操作
- 老用户从硬编码 `Y:\` 时代升级的自动恢复逻辑（v0.1.1 引入）保留不变

---

## v0.1.x 之前

参见 git log。
