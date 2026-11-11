"""Значки и заставка для Android: сетка 3×3 «дней» (как у приложения для Windows). Только стандартный Python.

    python make_icons.py   ->  assets/icon-only.png, icon-foreground.png, icon-background.png, splash.png, splash-dark.png
"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "assets"
BG, ON, OFF = (16, 24, 32), (34, 197, 94), (45, 58, 72)
PATTERN = [1, 1, 0, 1, 1, 1, 0, 1, 1]


def png(w, h, rows, alpha):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def draw(size, bg, grid_frac, alpha=False, plate=None):
    """Сетка grid_frac от стороны по центру; plate — тёмная подложка со скруглением под сеткой."""
    px = (lambda c: bytes(c) + b"\xff") if alpha else bytes
    clear = b"\x00\x00\x00\x00" if alpha else None
    g = size * grid_frac
    cell, gap = g * 0.29, g * 0.065
    x0 = (size - g) / 2
    pad = g * 0.17
    rows = []
    for y in range(size):
        segs = []
        for x in range(size):
            c = None
            for i, v in enumerate(PATTERN):
                cx, cy = x0 + (i % 3) * (cell + gap), x0 + (i // 3) * (cell + gap)
                if cx <= x < cx + cell and cy <= y < cy + cell:
                    c = ON if v else OFF
                    break
            if c is None and plate:
                l, t, r = x0 - pad, x0 - pad, x0 + g + pad
                rad = pad * 1.4
                if l <= x < r and t <= y < r:
                    dx = max(l + rad - x, 0, x - (r - rad)); dy = max(t + rad - y, 0, y - (r - rad))
                    if dx * dx + dy * dy <= rad * rad:
                        c = plate
            segs.append(px(c) if c else (px(bg) if bg else clear))
        rows.append(b"".join(segs))
    return rows


def fast(size, bg, grid_frac, alpha=False, plate=None):
    """Большие картинки рисуем в 512 px и масштабируем по строкам (одинаковые строки считаем один раз)."""
    if size <= 1100:
        return draw(size, bg, grid_frac, alpha, plate)
    small, bpp, cache = 512, 4 if alpha else 3, {}
    srows = draw(small, bg, grid_frac, alpha, plate)
    rows = []
    for y in range(size):
        sy = y * small // size
        if sy not in cache:
            src = srows[sy]
            cache[sy] = b"".join(src[(x * small // size) * bpp:(x * small // size + 1) * bpp] for x in range(size))
        rows.append(cache[sy])
    return rows


def save(name, size, **kw):
    alpha = kw.get("alpha", False)
    (OUT / name).write_bytes(png(size, size, fast(size, **kw), alpha))
    print("готово:", name)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    save("icon-only.png", 1024, bg=BG, grid_frac=0.62)
    save("icon-foreground.png", 1024, bg=None, grid_frac=0.40, alpha=True)
    save("icon-background.png", 1024, bg=BG, grid_frac=0.0)
    save("splash.png", 2732, bg=(245, 245, 247), grid_frac=0.16, plate=BG)
    save("splash-dark.png", 2732, bg=(0, 0, 0), grid_frac=0.16, plate=BG)
