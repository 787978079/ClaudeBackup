"""ElevenLabs 风格主题 — 深色 + 圆角卡片 + 紫蓝渐变.

实现：QSS 字符串 + Color 常量。所有颜色单点定义，方便切换浅色主题。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str          # 卡片背景
    surface_hover: str
    text: str
    text_dim: str
    primary_a: str        # 渐变起始
    primary_b: str        # 渐变结束
    accent: str
    success: str
    warn: str
    error: str
    border: str
    border_strong: str


DARK = Palette(
    bg="#0E0E10",
    surface="#1A1A1F",
    surface_hover="#22222A",
    text="#F5F5F7",
    text_dim="#A1A1AA",
    primary_a="#8B7FFF",
    primary_b="#5B6FFF",
    accent="#A78BFA",
    success="#34D399",
    warn="#FBBF24",
    error="#F87171",
    border="#2A2A30",
    border_strong="#3A3A44",
)


LIGHT = Palette(
    bg="#FAFAFA",
    surface="#FFFFFF",
    surface_hover="#F4F4F6",
    text="#0E0E10",
    text_dim="#52525B",
    primary_a="#7C6FF0",
    primary_b="#4F60E8",
    accent="#7C3AED",
    success="#059669",
    warn="#D97706",
    error="#DC2626",
    border="#E4E4E7",
    border_strong="#D4D4D8",
)


def qss(p: Palette) -> str:
    """返回完整 QSS 字符串."""
    return f"""
QWidget {{
    background-color: {p.bg};
    color: {p.text};
    font-family: 'Inter', '思源黑体', 'Microsoft YaHei UI', sans-serif;
    font-size: 14px;
}}

QMainWindow, QDialog {{
    background-color: {p.bg};
}}

/* ---------- 卡片 ---------- */
/* 不画 border：靠 surface 色和外层 bg 色的对比区分卡片边界；
   原 1px solid border 在深色主题下表现为暗灰描边，用户反馈"框感"重。 */
QFrame#Card {{
    background-color: {p.surface};
    border: none;
    border-radius: 14px;
    padding: 0px;
}}
QFrame#Card:hover {{
    background-color: {p.surface_hover};
}}

QFrame#TopBar {{
    background-color: {p.bg};
    border-bottom: 1px solid {p.border};
}}

QFrame#StatusBar {{
    background-color: {p.surface};
    border-top: 1px solid {p.border};
    color: {p.text_dim};
    padding: 6px 16px;
}}

/* ---------- 主按钮（紫蓝渐变） ---------- */
QPushButton#PrimaryBtn {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p.primary_a}, stop:1 {p.primary_b});
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-weight: 600;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p.primary_b}, stop:1 {p.primary_a});
}}
QPushButton#PrimaryBtn:pressed {{
    padding-top: 11px;
    padding-bottom: 9px;
}}
QPushButton#PrimaryBtn:disabled {{
    background-color: {p.border};
    color: {p.text_dim};
}}

/* ---------- 次按钮（透明 + 描边） ---------- */
QPushButton#SecondaryBtn {{
    background-color: transparent;
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 10px;
    padding: 9px 19px;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {p.surface_hover};
    border-color: {p.primary_a};
}}
QPushButton#SecondaryBtn:disabled {{
    color: {p.text_dim};
    border-color: {p.border};
    background-color: transparent;
}}

/* ---------- 图标按钮（顶栏紧凑） ---------- */
QPushButton#IconBtn {{
    background-color: transparent;
    color: {p.text_dim};
    border: 1px solid transparent;
    border-radius: 10px;
    font-size: 18px;
    padding: 0;
}}
QPushButton#IconBtn:hover {{
    background-color: {p.surface_hover};
    color: {p.text};
    border-color: {p.border_strong};
}}
QPushButton#IconBtn:pressed {{
    background-color: {p.surface};
}}

/* ---------- 危险按钮 ---------- */
QPushButton#DangerBtn {{
    background-color: transparent;
    color: {p.error};
    border: 1px solid {p.error};
    border-radius: 10px;
    padding: 9px 19px;
}}
QPushButton#DangerBtn:hover {{
    background-color: {p.error};
    color: white;
}}

/* ---------- 大动作卡片按钮 ---------- */
/* 默认 border: none，hover 时才显紫色描边作为悬停反馈；
   原 1px 暗灰描边在静止状态形成肉眼可见的"框感"。 */
QPushButton#ActionCard {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 18px 20px;
    text-align: left;
}}
QPushButton#ActionCard:hover {{
    background-color: {p.surface_hover};
    border-color: {p.primary_a};
}}
QPushButton#ActionCard:pressed {{
    background-color: {p.surface};
}}
QPushButton#ActionCard:disabled {{
    color: {p.text_dim};
    background-color: transparent;
    border-color: transparent;
}}
QPushButton#ActionCard:disabled QLabel {{
    color: {p.text_dim};
}}

/* ---------- 项目卡片（左侧） ---------- */
QPushButton#ProjectCard {{
    background-color: transparent;
    color: {p.text};
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: left;
    font-size: 14px;
}}
QPushButton#ProjectCard:hover {{
    background-color: {p.surface_hover};
}}
QPushButton#ProjectCard:checked {{
    background-color: {p.surface_hover};
    border-color: {p.primary_a};
}}

/* ---------- 复选框 ---------- */
QCheckBox {{
    color: {p.text};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {p.border_strong};
    border-radius: 4px;
    background: transparent;
}}
QCheckBox::indicator:hover {{
    border-color: {p.primary_a};
}}
QCheckBox::indicator:checked {{
    background-color: {p.primary_b};
    border-color: {p.primary_a};
    image: none;
}}
QCheckBox::indicator:disabled {{
    border-color: {p.border};
}}

/* ---------- 输入框 ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {p.primary_b};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border-color: {p.primary_a};
}}
QLineEdit[placeholderText], QTextEdit[placeholderText] {{
    color: {p.text};
}}
QLineEdit, QTextEdit {{
    placeholder-text-color: {p.text_dim};
}}

/* ---------- 标签 ---------- */
QLabel#H1 {{ font-size: 28px; font-weight: 700; color: {p.text}; }}
QLabel#H2 {{ font-size: 20px; font-weight: 600; color: {p.text}; }}
QLabel#H3 {{ font-size: 16px; font-weight: 600; color: {p.text}; }}
QLabel#Body {{ font-size: 14px; color: {p.text}; }}
QLabel#Dim  {{ font-size: 13px; color: {p.text_dim}; }}
QLabel#Mini {{ font-size: 12px; color: {p.text_dim}; }}

QLabel#StatusDotHealthy {{ color: {p.success}; font-size: 16px; }}
QLabel#StatusDotChanges {{ color: {p.warn}; font-size: 16px; }}
QLabel#StatusDotMissing {{ color: {p.error}; font-size: 16px; }}
QLabel#StatusDotNever {{ color: {p.text_dim}; font-size: 16px; }}

/* StatRow 紧凑数字（4 种配色） */
QLabel#StatNumPrimary {{ font-size: 22px; font-weight: 700; color: {p.primary_a}; }}
QLabel#StatNumSuccess {{ font-size: 22px; font-weight: 700; color: {p.success}; }}
QLabel#StatNumAccent  {{ font-size: 22px; font-weight: 700; color: {p.accent}; }}
QLabel#StatNumWarn    {{ font-size: 22px; font-weight: 700; color: {p.warn}; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.text_dim};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- 表格 / 列表 ---------- */
/* 列表本身不画 border：列表通常嵌在 Card 内，再加 1px 描边会形成"卡中卡"的双层框感。
   靠 surface 色和外层背景的差异区分边界。 */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {p.surface};
    border: none;
    border-radius: 10px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {p.primary_b};
    color: white;
}}

/* TimelineRow 整行 + 内部 QLabel 全部透明，避免行内 col-spacing 间隙漏出 surface 形成"线框"
   （彩色 bar、徽章因自带 setStyleSheet 优先级更高，不受此规则影响） */
QWidget#TimelineRow,
QWidget#TimelineRow QLabel {{
    background: transparent;
}}

/* ---------- 菜单 ---------- */
QMenu {{
    background-color: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 16px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {p.primary_b};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {p.border};
    margin: 4px 8px;
}}

/* ---------- 工具提示 ---------- */
QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 6px 10px;
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background-color: {p.surface};
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 8px;
}}
QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p.primary_a}, stop:1 {p.primary_b});
    border-radius: 4px;
}}

/* ---------- 分隔线 ---------- */
QFrame#Separator {{
    background-color: {p.border};
    max-height: 1px;
    min-height: 1px;
}}
"""


def current_palette(theme: str) -> Palette:
    return LIGHT if theme == "light" else DARK


def stylesheet(theme: str = "dark") -> str:
    return qss(current_palette(theme))
