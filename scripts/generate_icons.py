"""生成 ClaudeBackup 应用图标 — 多尺寸 PNG + ICO.

设计：方案 C — CB 字标 + 紫蓝渐变圆角方块 + 角落绿色快照点。
与 theme.DARK 的 primary_a/primary_b 配色保持一致。

用法：
    python scripts/generate_icons.py

输出：
    claude_backup/gui/assets/icons/
      ├── claudebackup.svg           # 矢量源（已存在）
      ├── claudebackup-{16,24,32,48,64,128,256}.png
      ├── claudebackup.ico           # 合成多尺寸（Windows 任务栏/Explorer 用）
      └── tray.png                   # 64x64，给 QSystemTrayIcon
"""
from __future__ import annotations
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "claude_backup" / "gui" / "assets" / "icons"

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _gradient_bg(size: int) -> Image.Image:
    """画对角紫蓝渐变（A78BFA → 8B7FFF → 5B6FFF）"""
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # 直接按像素插值生成对角渐变 — 小尺寸成本可忽略
    stops = [(0.0, (167, 139, 250)), (0.5, (139, 127, 255)), (1.0, (91, 111, 255))]

    def interp(t: float) -> tuple[int, int, int]:
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                return tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))  # type: ignore
        return stops[-1][1]

    px = base.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            r, g, b = interp(t)
            px[x, y] = (r, g, b, 255)
    return base


def _rounded_mask(size: int, radius: int) -> Image.Image:
    """圆角矩形 alpha mask."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return m


def _find_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """优先 Segoe UI Bold（Win 自带）→ Arial Bold → 默认."""
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",       # Segoe UI Bold
        r"C:\Windows\Fonts\seguisb.ttf",        # Segoe UI Semibold
        r"C:\Windows\Fonts\arialbd.ttf",        # Arial Bold
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_letters(img: Image.Image, size: int) -> None:
    """在 img 上画白色 'CB' monogram 居中."""
    d = ImageDraw.Draw(img)
    # 字号：占画布约 50%，给字标四周留呼吸空间
    font = _find_bold_font(int(size * 0.50))
    text = "CB"
    # 测量
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ox, oy = bbox[0], bbox[1]
    except AttributeError:
        tw, th = d.textsize(text, font=font)  # type: ignore[attr-defined]
        ox = oy = 0
    x = (size - tw) // 2 - ox
    # 视觉居中：基线字体偏下一点
    y = (size - th) // 2 - oy - int(size * 0.02)
    # 阴影（不在极小尺寸用）
    if size >= 32:
        shadow_color = (40, 30, 90, 100)
        d.text((x + max(1, size // 96), y + max(1, size // 96)),
               text, font=font, fill=shadow_color)
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def _draw_snapshot_dot(img: Image.Image, size: int) -> None:
    """右下角小绿点（快照标记）— 16/24 尺寸太小，跳过避免噪点."""
    if size < 32:
        return
    d = ImageDraw.Draw(img)
    cx = int(size * 0.78)
    cy = int(size * 0.78)
    r_outer = max(3, int(size * 0.085))
    r_inner = max(1, int(size * 0.04))
    d.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
              fill=(52, 211, 153, 245))
    d.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner),
              fill=(255, 255, 255, 255))


def _top_highlight(size: int) -> Image.Image:
    """上半部分柔光高亮（增加立体感）."""
    h = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(h)
    for i in range(size // 2):
        alpha = int(40 * (1 - i / (size / 2)))
        d.rectangle((0, i, size, i + 1), fill=(255, 255, 255, alpha))
    return h


def render_icon(size: int) -> Image.Image:
    """渲染一个尺寸的 RGBA 图标."""
    bg = _gradient_bg(size)
    # 顶部高亮叠加
    bg = Image.alpha_composite(bg, _top_highlight(size))
    # CB 字
    _draw_letters(bg, size)
    # 右下绿点
    _draw_snapshot_dot(bg, size)
    # 圆角裁剪
    radius = max(2, int(size * 0.22))
    mask = _rounded_mask(size, radius)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    images: dict[int, Image.Image] = {}
    for s in SIZES:
        img = render_icon(s)
        images[s] = img
        path = OUT / f"claudebackup-{s}.png"
        img.save(path, "PNG", optimize=True)
        print(f"  wrote {path}")

    # 合成 .ico — Windows 任务栏 / Explorer 用
    ico_path = OUT / "claudebackup.ico"
    # Pillow 接受同一张图传 sizes 参数生成多分辨率
    images[256].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"  wrote {ico_path}")

    # 给托盘单独一份 64px（避免读 ICO 时 Qt 取错尺寸）
    tray_path = OUT / "tray.png"
    images[64].save(tray_path, "PNG", optimize=True)
    print(f"  wrote {tray_path}")

    print("\n[OK] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
