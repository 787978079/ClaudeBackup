"""文案中心化 — 用大白话替换 git 术语。任何 UI 字符串都从这里取。"""
from __future__ import annotations


# ---------- 术语翻译 ----------

TERM = {
    "commit": "保存版本",
    "push": "上传",
    "push_nas": "上传到 NAS",
    "push_github": "上传到 GitHub",
    "pull": "下载更新",
    "remote": "远程仓库",
    "bare_repo": "镜像备份",
    "bundle": "时间快照",
    "tag": "发布版本",
    "release": "发布版本",
    "diff": "版本对比",
    "working_tree": "当前修改",
    "stash": "临时保存",
    "head": "最新版本",
    "branch": "分支",
}


# ---------- 主窗口文案 ----------

APP_NAME = "ClaudeBackup"
APP_TAGLINE = "把代码自动备份到 NAS 和 GitHub，再也不用担心丢失"

# 顶部栏
TOPBAR_HELP = "❓ 帮助"
TOPBAR_SETTINGS = "⚙️ 设置"

# 左侧
LEFT_ADD_PROJECT = "➕ 添加项目"
LEFT_NO_PROJECTS = "还没有项目"
LEFT_NO_PROJECTS_HINT = "点下方按钮添加你的第一个项目"

# 项目卡片状态
STATUS_HEALTHY = "✓ 已是最新备份"
STATUS_NEVER_BACKED_UP = "⏳ 还没备份过"
STATUS_HAS_CHANGES = "● 有未备份的修改"
STATUS_PATH_MISSING = "⚠ 项目目录已丢失"

# 中间详情
DETAIL_PATH = "本地路径"
DETAIL_LAST_BACKUP = "最近备份"
DETAIL_NAS_COUNT = "提交版本"
DETAIL_BUNDLE_COUNT = "时间快照"
DETAIL_DIR_SNAPSHOT_COUNT = "目录快照"
DETAIL_RELEASE_COUNT = "已发布版本"
DETAIL_TIMELINE = "备份时间线"

# 右侧操作
ACTION_BACKUP_NOW = "📸 立即备份"
ACTION_BACKUP_NOW_DESC = "把整个项目完整备份一份（含未保存的修改）"
ACTION_RELEASE = "🚀 发布版本"
ACTION_RELEASE_DESC = "把这个版本上传到 GitHub，作为重要发布"
ACTION_COMPARE = "🔍 对比版本"
ACTION_COMPARE_DESC = "看看两个备份之间改了什么"
ACTION_LIST = "⏱ 时间机器"
ACTION_LIST_DESC = "拖滑块回到任意时刻 — 看那时的内容 / 一键恢复"

# 底部状态栏
STATUS_NEXT_DAILY = "下一次每日备份"
STATUS_LAST_AUTO = "最近一次备份"
STATUS_TOTAL_SIZE = "NAS 总占用"

# 通知
NOTIFY_BACKUP_OK = "✅ 已备份 {name} — 时间快照已保存"
NOTIFY_BACKUP_FAIL = "⚠️ {name} 备份失败 — 点击查看原因"
NOTIFY_RELEASE_OK = "🚀 已发布 {name} {version}"

# 对话框
DIALOG_REGISTER_TITLE = "添加项目"
DIALOG_REGISTER_PROMPT = "选一个项目文件夹，我来帮你建好备份"
DIALOG_REGISTER_GITHUB = "GitHub 远程地址（可选）"

DIALOG_RELEASE_TITLE = "发布版本"
DIALOG_RELEASE_VERSION = "版本号（例如 v1.0.0）"
DIALOG_RELEASE_DESC = "这个版本做了什么？（可选）"
DIALOG_RELEASE_CONFIRM = "是的，发布这个版本"
DIALOG_RELEASE_CANCEL = "我再想想"

DIALOG_COMPARE_TITLE = "对比两个备份"
DIALOG_COMPARE_REF1 = "起点版本"
DIALOG_COMPARE_REF2 = "终点版本"

# 按钮
BTN_OK = "好的"
BTN_CANCEL = "取消"
BTN_CONFIRM = "确认"
BTN_RETRY = "再试一次"
BTN_OPEN_LOG = "查看日志"


# ---------- 托盘菜单 ----------

TRAY_OPEN = "打开主面板"
TRAY_BACKUP_HERE = "📸 备份当前文件夹"
TRAY_BACKUP_ALL = "📸 备份所有项目"
TRAY_OPEN_NAS = "📂 打开 NAS 备份目录"
TRAY_PAUSE_DAILY = "暂停每日自动备份"
TRAY_RESUME_DAILY = "恢复每日自动备份"
TRAY_VIEW_LOGS = "📁 打开日志文件夹"
TRAY_ABOUT = f"关于 {APP_NAME}"
TRAY_QUIT = "退出"
TRAY_TOOLTIP = APP_NAME


# ---------- Onboarding ----------

ONBOARD_WELCOME_TITLE = f"欢迎使用 {APP_NAME}"
ONBOARD_WELCOME_BODY = (
    f"{APP_TAGLINE}\n\n"
    "整个过程不到 1 分钟，跟着步骤走就行。"
)

ONBOARD_CONCEPT_TITLE = "三种备份各司其职"
ONBOARD_CONCEPT_AUTO = "AI 助手改完代码后自动备到 NAS（你不用管）"
ONBOARD_CONCEPT_DAILY = "每天定时自动备份（你不用管）"
ONBOARD_CONCEPT_RELEASE = "重要版本一键发布到 GitHub（你来点）"

ONBOARD_PICK_TITLE = "添加你的第一个项目"
ONBOARD_PICK_BODY = "选一个你正在开发的项目文件夹，我会帮你把备份配好。"
ONBOARD_PICK_BTN = "📁 选一个项目文件夹"

ONBOARD_TRY_TITLE = "做一次试试看"
ONBOARD_TRY_BODY = "点这个按钮，我现在就给你做一次完整备份（含目录拷贝 + git 历史）。"
ONBOARD_TRY_BTN = "📸 现在试一次备份"

ONBOARD_DONE_TITLE = "🎉 一切就绪"
ONBOARD_DONE_BODY = (
    "以后你只需要在重要节点点一下 \"发布版本\"，其它的我都会帮你做好。\n\n"
    "三个常用入口：\n"
    "  • 右下角托盘图标 — 随时备份当前文件夹\n"
    "  • 资源管理器右键 — 在项目文件夹上能看到 ClaudeBackup 菜单\n"
    "  • 主面板 — 你现在看到的这个窗口"
)

ONBOARD_SKIP = "跳过引导"
ONBOARD_NEXT = "下一步"
ONBOARD_PREV = "上一步"
ONBOARD_FINISH = "完成"


def t(key: str) -> str:
    """快捷取值（找不到返回 key 本身）."""
    return globals().get(key, key)
