"""Draws the ConvoHub icon (a hub joining three conversations) and writes static/icon.ico + icon.png.

Pure Python (no Pillow): shapes are drawn with signed distance functions, which gives smooth edges at
every size. Run: uv run python tools/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "convohub" / "static"
TOP, BOTTOM = (0x16, 0xA3, 0x94), (0x0F, 0x6E, 0x66)  # teal gradient
WHITE = (0xFF, 0xFD, 0xF8)


def rounded_rect(x, y, half, radius):
    qx, qy = abs(x - 0.5) - half + radius, abs(y - 0.5) - half + radius
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius


def circle(x, y, cx, cy, r):
    return math.hypot(x - cx, y - cy) - r


def capsule(x, y, ax, ay, bx, by, r):
    px, py, vx, vy = x - ax, y - ay, bx - ax, by - ay
    t = max(0.0, min(1.0, (px * vx + py * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - vx * t, py - vy * t) - r


def cover(d, px):
    """Signed distance -> pixel coverage (anti-aliasing over one pixel)."""
    return max(0.0, min(1.0, 0.5 - d / px))


def render(size):
    px = 1.0 / size
    sats = [(0.5 + 0.27 * math.cos(a), 0.5 + 0.27 * math.sin(a))
            for a in (math.radians(-90), math.radians(30), math.radians(150))]
    rows = []
    for j in range(size):
        y = (j + 0.5) / size
        row = bytearray([0])  # PNG filter: none
        for i in range(size):
            x = (i + 0.5) / size
            bg = cover(rounded_rect(x, y, 0.46, 0.2), px)
            t = y
            base = [TOP[k] * (1 - t) + BOTTOM[k] * t for k in range(3)]
            mark = cover(circle(x, y, 0.5, 0.5, 0.12), px)
            for sx, sy in sats:
                mark = max(mark, cover(circle(x, y, sx, sy, 0.078), px))
                mark = max(mark, cover(capsule(x, y, 0.5, 0.5, sx, sy, 0.03), px))
            rgb = [round(base[k] * (1 - mark) + WHITE[k] * mark) for k in range(3)]
            row += bytes(rgb + [round(255 * bg)])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images):
    """ICO with PNG-compressed entries (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    return header + entries + blobs


if __name__ == "__main__":
    images = [(s, render(s)) for s in (16, 24, 32, 48, 64, 128, 256)]
    (OUT / "icon.ico").write_bytes(ico(images))
    (OUT / "icon.png").write_bytes(dict(images)[256])
    print("wrote", OUT / "icon.ico", "and", OUT / "icon.png")
